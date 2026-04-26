"""Generate ready-to-hand-off content briefs from competitor gap analysis.

For each topic competitors cover that the target site doesn't, produce a brief with:
title, intent, content type, target keywords, key questions to answer, suggested word
count, and a priority score based on how many competitors validate the topic.

Rule-based by default (no LLM cost). Templates can be extended via the
SiteConfig.industry hint.

Usage (programmatic):
    from src.content_ideas import generate_content_ideas
    df = generate_content_ideas()  # writes output/content_ideas.csv

Or run standalone after the main pipeline:
    python -m src.content_ideas
"""

import logging
import os
import re
from collections import defaultdict
from typing import Optional

import pandas as pd

from src.config import SiteConfig, load_site_config, output_dir

logger = logging.getLogger(__name__)


# (label, regex patterns to match in topic, suggested content type)
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

# Common acronyms / brand-cased words that should never be title-cased letter-by-letter.
_ACRONYMS = {
    "icp", "jtbd", "b2b", "b2c", "saas", "kpi", "roi", "cms", "crm", "gtm", "abm",
    "seo", "geo", "aeo", "ai", "ml", "api", "ux", "ui", "qa", "sla", "sso", "ssr",
    "cdn", "cmo", "cto", "ceo", "cfo", "vp", "url", "html", "css", "js", "ssl",
    "tls", "iot", "nlp", "llm", "rag", "ssg", "cms", "iam", "rbac", "soc", "gdpr",
    "ccpa", "pii", "ppc", "cpc", "cpa", "cac", "ltv", "mrr", "arr", "nps", "csat",
    "p1", "p2", "p3",
}
_BRAND_CASED = {"saas": "SaaS"}


def _classify_intent(topic: str) -> tuple[str, str]:
    t = topic.lower()
    for label, patterns, ctype in _INTENT_RULES:
        if any(re.search(p, t) for p in patterns):
            return label, ctype
    return _DEFAULT_INTENT, _DEFAULT_CONTENT_TYPE


def _titlecase(topic: str) -> str:
    """Smart title-case: keep acronyms uppercase, lowercase short connectors."""
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
            out.append(w)  # already-uppercase short token, likely acronym
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


# Prefix / suffix strippers — remove the intent-marker words from the raw topic so the
# templated title doesn't end up with "How to How to ..." or "X Framework Framework".
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
    """Remove the intent-marker words so title templates don't double them up."""
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
    stripped = _strip_for_title(topic, intent)  # core noun phrase without intent words
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
    # De-dup while keeping order, drop empties
    seen, out = set(), []
    for k in kws:
        k = re.sub(r"\s+", " ", k).strip()
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out[:5]


def _suggest_questions(topic: str, intent: str, audience: str) -> list[str]:
    base = _strip_for_title(topic, intent)
    if intent == "comparison":
        return [
            f"Who are the top alternatives for {base}?",
            "How do they differ on pricing, features, and ideal use case?",
            f"Which option fits {audience.lower()} of different sizes (small / mid-market / enterprise)?",
        ]
    if intent == "howto":
        return [
            f"What's the step-by-step process for {base}?",
            "What are common mistakes to avoid and signs you're doing it wrong?",
            "What templates, tools, or examples make this easier?",
        ]
    if intent == "definition":
        return [
            f"What does '{base}' actually mean (and what isn't it)?",
            f"Why does it matter for {audience.lower()}?",
            "How do leading teams use it in practice?",
        ]
    if intent == "framework":
        return [
            f"What is the {base} framework and where did it come from?",
            "When should a team apply it? When should they avoid it?",
            "What are the steps + the outputs at each stage?",
        ]
    if intent == "examples":
        return [
            f"What are real, vetted examples of {base}?",
            "What patterns and anti-patterns emerge across them?",
            "What can a reader copy or adapt today?",
        ]
    if intent == "metrics":
        return [
            f"What are the current benchmarks for {base}?",
            "How do top-quartile teams compare to median?",
            "What variables drive the gap?",
        ]
    if intent == "checklist":
        return [
            f"What are the must-do items for {base}?",
            "What are the common skips that break it?",
            "How do you score yourself against the list?",
        ]
    return [
        f"What is {base} and why does it matter now?",
        "What are the most common approaches teams take?",
        "What does best-in-class look like?",
    ]


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
    # Slight boost for the highest-converting / most evergreen formats
    if intent in ("comparison", "howto", "framework"):
        score += 1
    if score >= 3:
        return "P1"
    if score >= 2:
        return "P2"
    return "P3"


def _discover_gap_files() -> list[tuple[str, pd.DataFrame]]:
    out = output_dir()
    if not os.path.isdir(out):
        return []
    results = []
    for fname in sorted(os.listdir(out)):
        if fname.startswith("competitor_gap_") and fname.endswith(".csv"):
            stem = fname[len("competitor_gap_"):-len(".csv")]
            display = stem.replace("_", " ").title()
            try:
                df = pd.read_csv(os.path.join(out, fname))
            except pd.errors.EmptyDataError:
                continue
            if not df.empty:
                results.append((display, df))
    return results


def generate_content_ideas(
    site_config: Optional[SiteConfig] = None,
    max_ideas: int = 50,
) -> pd.DataFrame:
    """Generate ranked content briefs from competitor gap data.

    Pulls every competitor_gap_*.csv from the output dir, finds rows whose status
    contains 'GAP' (i.e., competitor covers, target doesn't), and synthesizes a brief
    per unique topic. Topics are de-duplicated across competitors so a topic covered
    by multiple competitors gets ONE brief with priority boosted by validation.

    Writes to output/content_ideas.csv and returns the dataframe.
    """
    if site_config is None:
        site_config = load_site_config() or SiteConfig(name="Site", domain="")

    audience = _audience_label(site_config.industry)

    gap_dfs = _discover_gap_files()
    if not gap_dfs:
        logger.warning("No competitor gap files found — run the pipeline with --competitor first")
        return pd.DataFrame()

    # topic (lowercased) -> set of competitor display names that cover it
    topic_to_comps: dict[str, set] = defaultdict(set)
    for comp_name, df in gap_dfs:
        if "status" not in df.columns or "keyword" not in df.columns:
            continue
        gap_rows = df[df["status"].str.contains("GAP", case=False, na=False)]
        for _, row in gap_rows.iterrows():
            topic = str(row.get("keyword", "")).strip().lower()
            if topic:
                topic_to_comps[topic].add(comp_name)

    if not topic_to_comps:
        logger.info("No content gaps detected across competitors")
        return pd.DataFrame()

    ideas = []
    for topic, comps in topic_to_comps.items():
        intent, ctype = _classify_intent(topic)
        title = _suggest_title(topic, intent, audience)
        ideas.append({
            "priority": _calculate_priority(len(comps), intent),
            "title": title,
            "gap_topic": topic,
            "content_type": ctype,
            "intent": intent,
            "target_audience": audience,
            "suggested_keywords": " | ".join(_suggest_keywords(topic, intent)),
            "key_questions": " | ".join(_suggest_questions(topic, intent, audience)),
            "est_word_count": _suggest_word_count(intent),
            "covered_by": ", ".join(sorted(comps)),
            "num_competitors": len(comps),
        })

    df = pd.DataFrame(ideas)
    priority_order = {"P1": 0, "P2": 1, "P3": 2}
    df["_p"] = df["priority"].map(priority_order)
    df = df.sort_values(["_p", "num_competitors", "gap_topic"], ascending=[True, False, True])
    df = df.drop(columns=["_p"]).reset_index(drop=True)
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
            print(f"      type: {row['content_type']} | ~{row['est_word_count']}w | covered by: {row['covered_by']}")
        print(f"\nFull list: {os.path.join(output_dir(), 'content_ideas.csv')}")
