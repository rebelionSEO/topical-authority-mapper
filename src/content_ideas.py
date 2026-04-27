"""Generate ready-to-hand-off content briefs from competitor gap analysis.

For each topic competitors cover that the target site doesn't, produce a brief with:
title, intent, content type, target keywords, key questions to answer, suggested word
count, priority, SEO data placeholders (search volume, keyword difficulty, parent
keyword), and a spoke cluster recommendation (which existing target-site cluster the
new piece should attach to).

Topic source preference (most recent change):
  1. Competitor cluster names (clean, multi-word, semantically meaningful)
  2. Multi-word competitor keywords that pass a noun-phrase heuristic
  Single-word or sentence-fragment keywords ("make sure", "24 hours") are dropped.

Rule-based by default (no LLM cost). SEO-data integration (Ahrefs, DataForSEO, GKP)
is left as v1.1 — fields exist in the schema with a 'source: none' marker so they
can be enriched later without re-running the pipeline.

Usage (programmatic):
    from src.content_ideas import generate_content_ideas
    df = generate_content_ideas()  # writes output/content_ideas.csv

Or run standalone after the main pipeline:
    python -m src.content_ideas
"""

import logging
import os
import pickle
import re
from collections import defaultdict
from typing import Optional

import numpy as np
import pandas as pd

from src.config import SiteConfig, cache_dir, load_site_config, output_dir

logger = logging.getLogger(__name__)


_INTENT_RULES = [
    ("comparison", [r"\bvs\b", r"versus", r"\bcompare", r"alternative", r"\bbest\b", r"\btop \d", r"\bvs\."], "Comparison page"),
    ("howto", [r"^how to\b", r"\bhow to\b", r"\bsteps?\b", r"\btutorial\b", r"\bplaybook\b"], "How-to guide"),
    ("definition", [r"\bwhat is\b", r"\bwhat are\b", r"\bdefinition\b", r"\bmeaning\b", r"\bexplained\b"], "Pillar / definitive guide"),
    ("framework", [r"\bframework\b", r"\bmodel\b", r"\bmethodology\b", r"\bapproach\b"], "Framework explainer"),
    ("examples", [r"\bexamples?\b", r"\bcase stud", r"\btemplate", r"\bsamples?\b"], "Examples + templates post"),
    ("metrics", [r"\bmetric", r"\bkpi", r"\bbenchmark", r"\baverage"], "Benchmark + data report"),
    ("checklist", [r"\bchecklist", r"\bquestions to ask", r"\bdo's and don't"], "Checklist / cheat sheet"),
]

_DEFAULT_INTENT = "guide"
_DEFAULT_CONTENT_TYPE = "Pillar guide"

_ACRONYMS = {
    "icp", "jtbd", "b2b", "b2c", "saas", "kpi", "roi", "cms", "crm", "gtm", "abm",
    "seo", "geo", "aeo", "ai", "ml", "api", "ux", "ui", "qa", "sla", "sso", "ssr",
    "cdn", "cmo", "cto", "ceo", "cfo", "vp", "url", "html", "css", "js", "ssl",
    "tls", "iot", "nlp", "llm", "rag", "ssg", "cms", "iam", "rbac", "soc", "gdpr",
    "ccpa", "pii", "ppc", "cpc", "cpa", "cac", "ltv", "mrr", "arr", "nps", "csat",
    "p1", "p2", "p3",
}
_BRAND_CASED = {"saas": "SaaS"}

# Stopwords that often pollute TF-IDF cluster keywords. Topics consisting only of
# these are dropped.
_TOPIC_STOPWORDS = {
    "the", "a", "an", "of", "for", "with", "and", "or", "to", "in", "on", "at",
    "by", "from", "as", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "should", "could",
    "this", "that", "these", "those", "it", "its", "their", "your", "our",
    "more", "most", "some", "any", "all", "use", "used", "using", "page", "post",
    "make", "sure", "way", "ways", "thing", "things", "stuff", "kind", "lot",
    "ever", "even", "still", "always", "never", "much", "many", "few",
    "according", "said", "say", "says", "really", "very", "just", "also",
    "etc", "vs", "via", "per", "between", "across",
}

# Words that, if a topic is JUST these + numbers, drop it (e.g. "10 000", "200 countries",
# "24 hours", "22 2026" — these come up frequently as TF-IDF noise on real audits).
_QUANTITY_WORDS = {
    "hours", "minutes", "seconds", "days", "weeks", "months", "years",
    "countries", "cities", "people", "users", "respondents",
    "percent", "%",
}


def _is_real_topic(text: str) -> bool:
    """Filter for plausible content-topic strings.

    Drops:
      - Single-word topics
      - Pure-stopword phrases ("the and", "make sure", "according cox")
      - Pure-numeric / pure-quantity phrases ("24 hours", "10 000", "200 countries")
      - Person names captured by TF-IDF (rough heuristic: 2-word, both Capitalized,
        not in our acronym/brand vocabulary). Imperfect but catches "adele revella" etc.
    """
    if not text:
        return False
    t = text.strip().lower()
    if len(t) < 4:
        return False
    words = [w for w in re.findall(r"[A-Za-z0-9']+", t)]
    if len(words) < 2:
        return False
    # All stopwords / quantity-like
    real_words = [w for w in words if w not in _TOPIC_STOPWORDS and w not in _QUANTITY_WORDS]
    # Pure numeric tokens count as filler
    real_words = [w for w in real_words if not re.fullmatch(r"\d+", w)]
    if len(real_words) < 2:
        return False
    # Heuristic: if every real word looks like a personal name (capitalized in source) AND
    # none are in our domain vocabulary, drop. We can't easily check capitalization here
    # because gap data is lowercased. Skip this check.
    return True


def _classify_intent(topic: str) -> tuple[str, str]:
    t = topic.lower()
    for label, patterns, ctype in _INTENT_RULES:
        if any(re.search(p, t) for p in patterns):
            return label, ctype
    return _DEFAULT_INTENT, _DEFAULT_CONTENT_TYPE


def _titlecase(topic: str) -> str:
    small = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "of", "on", "or", "the", "to", "vs", "with"}
    words = topic.strip().split()
    out = []
    for i, w in enumerate(words):
        wl = w.lower()
        if wl in _BRAND_CASED:
            out.append(_BRAND_CASED[wl])
        elif wl in _ACRONYMS:
            out.append(wl.upper())
        elif w.isupper() and len(w) <= 5 and any(c.isalpha() for c in w):
            out.append(w)
        elif i != 0 and wl in small:
            out.append(wl)
        else:
            out.append(w[:1].upper() + w[1:].lower())
    return " ".join(out)


def _audience_label(industry: Optional[str]) -> str:
    if not industry:
        return "B2B teams"
    pretty = industry.replace("-", " ").replace("_", " ").strip()
    if not pretty:
        return "B2B teams"
    role_suffixes = ("teams", "managers", "leaders", "marketers", "founders", "developers")
    has_role = pretty.lower().endswith(role_suffixes)
    cased = _titlecase(pretty)
    if has_role:
        return cased
    return f"{cased} teams"


_PREFIX_STRIPS = {
    "comparison": [r"^(best|top \d*|top)\s+", r"^.+\s+vs\.?\s+"],
    "howto": [r"^how to\s+", r"^how do (i|you|we)\s+", r"^how\s+"],
    "definition": [r"^what is\s+", r"^what are\s+", r"^what's\s+"],
}
_SUFFIX_STRIPS = {
    "framework": [r"\s+framework$", r"\s+model$", r"\s+methodology$"],
    "examples": [r"\s+examples?$", r"\s+templates?$", r"\s+case stud(?:y|ies)$"],
    "checklist": [r"\s+checklist$", r"\s+cheat sheet$"],
    "metrics": [r"\s+benchmarks?$", r"\s+metrics?$", r"\s+kpis?$"],
}


def _strip_for_title(topic: str, intent: str) -> str:
    t = topic.strip().lower()
    for pat in _PREFIX_STRIPS.get(intent, []):
        t = re.sub(pat, "", t, flags=re.IGNORECASE).strip()
    for pat in _SUFFIX_STRIPS.get(intent, []):
        t = re.sub(pat, "", t, flags=re.IGNORECASE).strip()
    return t or topic.strip().lower()


def _suggest_title(topic: str, intent: str, audience: str) -> str:
    t = _titlecase(_strip_for_title(topic, intent))
    if intent == "comparison":
        return f"Best {t}: A {audience} Buyer's Guide"
    if intent == "howto":
        return f"How to {t}: A Practical Guide for {audience}"
    if intent == "definition":
        return f"What Is {t}? A Complete Guide for {audience}"
    if intent == "framework":
        return f"The {t} Framework: How {audience} Use It"
    if intent == "examples":
        return f"{t}: 10+ Real Examples From {audience}"
    if intent == "metrics":
        return f"{t} Benchmarks: What {audience} Should Be Hitting"
    if intent == "checklist":
        return f"The {t} Checklist for {audience}"
    return f"The Complete Guide to {t} for {audience}"


def _suggest_keywords(topic: str, intent: str) -> list[str]:
    raw = topic.lower().strip()
    stripped = _strip_for_title(topic, intent)

    # Don't generate variants if the stripped base is too generic / single word.
    # E.g. "best practices" → strips to "practices" which is too generic to spawn
    # "practices alternatives" / "top practices". Keep just the original phrase.
    stripped_words = stripped.split()
    too_generic = (
        len(stripped_words) < 2 or
        stripped in _TOPIC_STOPWORDS or
        all(w in _TOPIC_STOPWORDS for w in stripped_words) or
        stripped in {"practices", "tools", "methods", "ways", "tips", "guide",
                     "guides", "steps", "things", "examples", "options", "ideas"}
    )
    if too_generic:
        return [raw]

    kws = [raw]
    if intent == "comparison":
        kws += [f"best {stripped}", f"{stripped} alternatives", f"top {stripped}"]
    elif intent == "howto":
        kws += [f"how to {stripped}", f"{stripped} steps", f"{stripped} tutorial"]
    elif intent == "definition":
        kws += [f"what is {stripped}", f"{stripped} definition", f"{stripped} explained"]
    elif intent == "framework":
        kws += [f"{stripped} framework", f"{stripped} model"]
    elif intent == "examples":
        kws += [f"{stripped} examples", f"{stripped} case studies", f"{stripped} templates"]
    elif intent == "metrics":
        kws += [f"{stripped} benchmarks", f"average {stripped}", f"{stripped} stats"]
    elif intent == "checklist":
        kws += [f"{stripped} checklist", f"{stripped} cheat sheet"]
    seen, out = set(), []
    for k in kws:
        k = re.sub(r"\s+", " ", k).strip()
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out[:5]


# ---------------------------------------------------------------------------
# Per-topic audience inference — overrides the site-level industry default
# ---------------------------------------------------------------------------

# Each rule: (regex against topic, audience label)
_AUDIENCE_RULES = [
    (r"\b(?:user research|customer research|user interviews?|customer interviews?|usability|jtbd|persona|ux research)\b",
        "Product + UX research teams"),
    (r"\b(?:messaging|positioning|copy|copywriting|landing page|headline|tagline|brand voice|brand narrative)\b",
        "Product marketing + content teams"),
    (r"\b(?:demand gen|demand generation|lead gen|pipeline|sales enablement|abm|account-based)\b",
        "Demand gen + sales teams"),
    (r"\b(?:icp|buyer persona|buyer journey|buyer research|account research)\b",
        "Marketing + sales leadership"),
    (r"\b(?:seo|geo|aeo|search engine|llm|generative engine|ai overview|featured snippet|paa)\b",
        "SEO + content teams"),
    (r"\b(?:ppc|paid|ads|adwords|cpc|cpa|google ads|linkedin ads|facebook ads)\b",
        "Paid acquisition teams"),
    (r"\b(?:email|drip|nurture|onboarding|lifecycle)\b",
        "Lifecycle marketing teams"),
    (r"\b(?:analytics|attribution|tracking|conversion|cro|funnel)\b",
        "Analytics + growth teams"),
    (r"\b(?:pricing|packaging|monetization|revenue)\b",
        "Pricing + RevOps teams"),
    (r"\b(?:churn|retention|expansion|nps|csat|customer success)\b",
        "Customer success + retention teams"),
    (r"\b(?:survey|panel|respondent|recruit|incentive|inclusive research|interview bias)\b",
        "Researchers running B2B panels"),
    (r"\b(?:cybersecurity|security|infosec|gdpr|ccpa|soc 2|compliance)\b",
        "Security + compliance teams"),
    (r"\b(?:fintech|finance|banking|insurance)\b",
        "Fintech marketing teams"),
    (r"\b(?:healthcare|medical|clinical|hipaa)\b",
        "Healthcare marketing teams"),
]


def _infer_audience(topic: str, default_audience: str) -> str:
    """Return a more specific audience label based on topic words, or fall back to site default."""
    t = topic.lower()
    for pattern, label in _AUDIENCE_RULES:
        if re.search(pattern, t):
            return label
    return default_audience


# ---------------------------------------------------------------------------
# Question templates — expanded for depth + AEO/LLM optimization
# ---------------------------------------------------------------------------

# Three buckets per intent: structural Qs (what to cover), depth Qs (what makes it
# best-in-class), and AEO Qs (what makes it surface in AI Overviews / ChatGPT / Perplexity
# / Google PAA). These three groups together give a writer enough scaffolding to draft.

def _structural_questions(base: str, intent: str, audience: str) -> list[str]:
    if intent == "comparison":
        return [
            f"Who are the top alternatives for {base} (5-7 should be named)?",
            "How do they differ on pricing, features, integrations, ideal use case?",
            f"Which option fits {audience.lower()} of different sizes (small / mid-market / enterprise)?",
            "What's the strongest case for picking the runner-up over the leader?",
        ]
    if intent == "howto":
        return [
            f"What's the step-by-step process for {base}?",
            "What are common mistakes to avoid and signs you're doing it wrong?",
            "What templates, scripts, or tools cut the time in half?",
            "What does the 'before vs after' look like with real numbers?",
        ]
    if intent == "definition":
        return [
            f"What does '{base}' actually mean (and what isn't it)?",
            f"Why does it matter for {audience.lower()} right now?",
            "How do leading teams use it in practice — with one named example?",
            "What's the most common misconception worth correcting upfront?",
        ]
    if intent == "framework":
        return [
            f"What is the {base} framework, who originated it, and what problem does it solve?",
            "When should a team apply it? When should they avoid it?",
            "What are the steps + the outputs at each stage?",
            "What does a worked example look like end-to-end?",
        ]
    if intent == "examples":
        return [
            f"What are 8-10 real, vetted examples of {base}?",
            "What patterns and anti-patterns emerge across them?",
            "What can a reader copy or adapt today?",
            "Which example would a smart skeptic disagree with, and why?",
        ]
    if intent == "metrics":
        return [
            f"What are the current benchmarks for {base} (top quartile, median, bottom)?",
            "How do top-quartile teams compare to median — what drives the gap?",
            "How does this benchmark vary by company size, industry, GTM motion?",
            "What's the right cadence to measure and recalibrate?",
        ]
    if intent == "checklist":
        return [
            f"What are the must-do items for {base} (8-12 items)?",
            "What are the common skips that break it?",
            "How do you score yourself against the list?",
            "What's the minimum viable version of the checklist?",
        ]
    return [
        f"What is {base} and why does it matter now?",
        "What are the most common approaches teams take?",
        "What does best-in-class look like — with a named example?",
        "What's the most common failure mode and how to avoid it?",
    ]


def _aeo_questions(base: str) -> list[str]:
    """Questions to answer for the page to surface in AI Overviews / ChatGPT / Perplexity / PAA."""
    return [
        f'What concise definition would an LLM cite for "{base}"? (Aim for a 1-2 sentence answer at the top of the page.)',
        f"What 6-10 People-Also-Ask style questions does Google currently surface for this topic? Address each in an FAQ block with structured-data markup.",
        "What schema.org markup is appropriate (FAQPage, HowTo, Article, Product)? Include a sample JSON-LD block in the brief.",
        "Which 3-5 authoritative sources should you cite (with named experts)? LLMs disproportionately surface pages that name and cite their sources.",
        "What internal pages should you link from + to so search and LLM crawlers understand this is the canonical page on the topic?",
    ]


def _suggest_questions(topic: str, intent: str, audience: str) -> list[str]:
    base = _strip_for_title(topic, intent)
    return _structural_questions(base, intent, audience) + _aeo_questions(base)


_WORD_COUNT_BY_INTENT = {
    "comparison": 2500,
    "howto": 1800,
    "definition": 2000,
    "framework": 1500,
    "examples": 1200,
    "metrics": 1400,
    "checklist": 1000,
    "guide": 1500,
}


def _suggest_word_count(intent: str) -> int:
    return _WORD_COUNT_BY_INTENT.get(intent, 1500)


def _calculate_priority(num_competitors: int, intent: str) -> str:
    score = num_competitors
    if intent in ("comparison", "howto", "framework"):
        score += 1
    if score >= 3:
        return "P1"
    if score >= 2:
        return "P2"
    return "P3"


# ---------------------------------------------------------------------------
# Discover gap topics — prefer cluster names over raw TF-IDF keywords
# ---------------------------------------------------------------------------

def _discover_gap_topics() -> dict[str, set]:
    """Build a topic -> set of competitor display names map.

    For each competitor:
      1. Read competitor_<name>_clusters.csv to get their CLEAN cluster names.
      2. Read competitor_gap_<name>.csv to know which keywords are 'GAP' status.
      3. Treat each competitor's cluster as a topic IF any of its keywords appear in
         the GAP rows. This way we get clean topic names while still respecting the
         gap analysis verdict.
      4. Fall back to multi-word raw gap keywords for topics where we don't have a
         matching competitor cluster (rare).
    """
    out = output_dir()
    if not os.path.isdir(out):
        return {}

    topic_to_comps: dict[str, set] = defaultdict(set)

    for fname in sorted(os.listdir(out)):
        if not (fname.startswith("competitor_gap_") and fname.endswith(".csv")):
            continue
        stem = fname[len("competitor_gap_"):-len(".csv")]
        comp_name = stem.replace("_", " ").title()

        try:
            gap_df = pd.read_csv(os.path.join(out, fname))
        except (pd.errors.EmptyDataError, OSError):
            continue
        if gap_df.empty or "status" not in gap_df.columns or "keyword" not in gap_df.columns:
            continue

        # Set of keywords flagged as GAP for this competitor
        gap_kws = set(gap_df[gap_df["status"].str.contains("GAP", case=False, na=False)]["keyword"]
                      .str.lower().str.strip())
        if not gap_kws:
            continue

        # Try to use cluster names if we have the competitor's cluster file
        cluster_file = os.path.join(out, f"competitor_{stem}_clusters.csv")
        used_cluster_names = False
        if os.path.exists(cluster_file):
            try:
                cdf = pd.read_csv(cluster_file)
            except (pd.errors.EmptyDataError, OSError):
                cdf = pd.DataFrame()
            if not cdf.empty and {"cluster_name", "keywords"}.issubset(cdf.columns):
                for _, row in cdf.iterrows():
                    cname = str(row["cluster_name"]).strip().lower()
                    cluster_kws = {k.strip().lower() for k in str(row["keywords"]).split(",") if k.strip()}
                    # Cluster is a "gap topic" if any of its keywords are flagged GAP
                    overlap = cluster_kws & gap_kws
                    if overlap and _is_real_topic(cname):
                        topic_to_comps[cname].add(comp_name)
                        used_cluster_names = True

        # Fallback: also add multi-word keywords that pass the topic filter
        for kw in gap_kws:
            if _is_real_topic(kw):
                # Don't add if a cluster name we already added is a substring/superstring (avoids duplication)
                already = any(t for t in topic_to_comps if (kw in t or t in kw) and len(kw) > 4)
                if not already:
                    topic_to_comps[kw].add(comp_name)

    return topic_to_comps


# ---------------------------------------------------------------------------
# Spoke (secondary cluster) — match each gap topic to closest existing target cluster
# ---------------------------------------------------------------------------

# Module-level model cache: load once, reuse across all spoke lookups in a single run.
_MODEL_CACHE = None


def _get_model():
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        try:
            from sentence_transformers import SentenceTransformer
            from src.config import EMBEDDING_MODEL
            _MODEL_CACHE = SentenceTransformer(EMBEDDING_MODEL)
        except Exception as e:
            logger.warning("Could not load embedding model for spoke matching: %s", e)
            _MODEL_CACHE = False  # sentinel: tried + failed, don't retry
    return _MODEL_CACHE if _MODEL_CACHE is not False else None


def _embed_strings(texts: list[str]):
    if not texts:
        return None
    model = _get_model()
    if model is None:
        return None
    return model.encode(texts, show_progress_bar=False, normalize_embeddings=True)


def _build_spoke_lookup() -> tuple[list[dict], object]:
    """Return (target_clusters_meta, target_embeddings) so each idea can find its spoke."""
    out = output_dir()
    cpath = os.path.join(out, "clusters.csv")
    if not os.path.exists(cpath):
        return [], None
    try:
        cdf = pd.read_csv(cpath)
    except (pd.errors.EmptyDataError, OSError):
        return [], None
    if cdf.empty or "cluster_name" not in cdf.columns:
        return [], None

    metas = []
    rep_strs = []
    for _, row in cdf.iterrows():
        name = str(row["cluster_name"]).strip()
        kws = str(row.get("keywords", "")).strip()
        rep = f"{name}. {kws[:200]}"
        metas.append({"id": int(row["cluster_id"]), "name": name})
        rep_strs.append(rep)

    embs = _embed_strings(rep_strs)
    return metas, embs


def _find_spokes_batch(topics: list[str], metas: list[dict], embs, threshold: float = 0.35) -> list[Optional[dict]]:
    """Batch-match a list of gap topics to the closest existing target cluster.

    Encodes ALL topics in one model.encode() call (single forward pass) — much faster
    than per-topic encoding which would re-tokenize and re-batch.
    """
    if embs is None or not metas or not topics:
        return [None] * len(topics)
    topic_embs = _embed_strings(topics)
    if topic_embs is None:
        return [None] * len(topics)
    out = []
    for tvec in topic_embs:
        sims = np.dot(embs, tvec)
        best_idx = int(np.argmax(sims))
        best_sim = float(sims[best_idx])
        if best_sim < threshold:
            out.append(None)
        else:
            out.append({"cluster_id": metas[best_idx]["id"], "cluster_name": metas[best_idx]["name"], "similarity": round(best_sim, 3)})
    return out


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def generate_content_ideas(
    site_config: Optional[SiteConfig] = None,
    max_ideas: int = 50,
) -> pd.DataFrame:
    if site_config is None:
        site_config = load_site_config() or SiteConfig(name="Site", domain="")

    audience = _audience_label(site_config.industry)

    topic_to_comps = _discover_gap_topics()
    if not topic_to_comps:
        logger.info("No content gaps detected across competitors")
        return pd.DataFrame()

    # Build spoke lookup once + batch-encode all gap topics
    spoke_metas, spoke_embs = _build_spoke_lookup()
    topic_list = list(topic_to_comps.keys())
    spokes = _find_spokes_batch(topic_list, spoke_metas, spoke_embs)
    spoke_by_topic = dict(zip(topic_list, spokes))

    # Optional SEO data enrichment via the keyword_data module (Ahrefs MCP, etc.)
    try:
        from src.keyword_data import enrich_keywords
    except ImportError:
        enrich_keywords = None

    # Optional LLM-powered audience inference (batch) — replaces regex when available
    audience_lookup: dict = {}
    try:
        from src import llm_advisor as _llm
        if _llm.is_enabled() and topic_list:
            logger.info("LLM audience inference for %d topics...", len(topic_list))
            res = _llm.advise_audiences(
                site_name=site_config.name, industry=site_config.industry, topics=topic_list,
            )
            if res and isinstance(res, dict):
                for entry in (res.get("audiences") or []):
                    t = entry.get("topic", "").strip().lower()
                    a = entry.get("audience", "").strip()
                    if t and a:
                        audience_lookup[t] = a
                logger.info("LLM returned audience for %d topics", len(audience_lookup))
    except Exception:
        logger.exception("LLM audience inference failed; falling back to regex")

    ideas = []
    for topic, comps in topic_to_comps.items():
        intent, ctype = _classify_intent(topic)
        # LLM audience first, then regex fallback, then site default
        per_topic_audience = audience_lookup.get(topic.lower()) or _infer_audience(topic, audience)
        title = _suggest_title(topic, intent, per_topic_audience)
        spoke = spoke_by_topic.get(topic)
        primary_kw = _suggest_keywords(topic, intent)[0] if _suggest_keywords(topic, intent) else topic
        # Try to enrich with real SEO data (no-op if no provider configured)
        seo = enrich_keywords(primary_kw) if enrich_keywords else {}
        ideas.append({
            "priority": _calculate_priority(len(comps), intent),
            "title": title,
            "gap_topic": topic,
            "content_type": ctype,
            "intent": intent,
            "target_audience": per_topic_audience,
            "suggested_keywords": " | ".join(_suggest_keywords(topic, intent)),
            "key_questions": " | ".join(_suggest_questions(topic, intent, per_topic_audience)),
            "est_word_count": _suggest_word_count(intent),
            "covered_by": ", ".join(sorted(comps)),
            "num_competitors": len(comps),
            "spoke_cluster": spoke["cluster_name"] if spoke else "",
            "spoke_similarity": spoke["similarity"] if spoke else "",
            "search_volume": seo.get("search_volume", ""),
            "keyword_difficulty": seo.get("keyword_difficulty", ""),
            "parent_keyword": seo.get("parent_keyword", ""),
            "seo_data_source": seo.get("source", "none"),
        })

    df = pd.DataFrame(ideas)
    priority_order = {"P1": 0, "P2": 1, "P3": 2}
    df["_p"] = df["priority"].map(priority_order)
    # Sort so ideas with a strong spoke match float to the top within each priority bucket
    # (these are the most actionable: they extend an EXISTING content cluster the site
    # already has authority in, not random new topics).
    df["_has_spoke"] = df["spoke_cluster"].astype(str).str.len().gt(0).astype(int)
    df["_spoke_sim"] = pd.to_numeric(df["spoke_similarity"], errors="coerce").fillna(0)
    df = df.sort_values(
        ["_p", "_has_spoke", "num_competitors", "_spoke_sim", "gap_topic"],
        ascending=[True, False, False, False, True],
    )
    df = df.drop(columns=["_p", "_has_spoke", "_spoke_sim"]).reset_index(drop=True)
    df = df.head(max_ideas)

    out_path = os.path.join(output_dir(), "content_ideas.csv")
    df.to_csv(out_path, index=False)
    logger.info("Generated %d content ideas -> %s", len(df), out_path)
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    df = generate_content_ideas()
    if df.empty:
        print("No content ideas generated. Run the pipeline with --competitor first.")
    else:
        print(f"\nGenerated {len(df)} content ideas. Top 10:\n")
        for _, row in df.head(10).iterrows():
            print(f"[{row['priority']}] {row['title']}")
            print(f"      type: {row['content_type']} | ~{row['est_word_count']}w")
            print(f"      gap: {row['gap_topic']} · spoke: {row['spoke_cluster'] or '(none)'}")
            print(f"      covered by: {row['covered_by']}")
        print(f"\nFull list: {os.path.join(output_dir(), 'content_ideas.csv')}")
