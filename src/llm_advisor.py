"""LLM-powered analysis layered on top of the rule-based pipeline.

Adds judgment to the analyses that previously relied on regex + heuristics:
  - Cannibalization: is this cluster ACTUALLY a cannibalization issue, or did the
    clustering algorithm group different page types together? Which URL is the
    real winner if cannibalization is real? What action per URL?
  - Thin content: is this URL genuinely thin content needing expansion, or is it a
    page-type that's intentionally short (lander, demo, conversion flow, gated asset)?
  - Audience: who is the real audience for a piece of content (more specific than
    a hand-coded regex)?
  - Brand voice: distill a brand voice profile from sampled site content (no PDF
    required).

All calls are OPT-IN. Disabled by default. Enable with TAM_LLM_PROVIDER=anthropic +
ANTHROPIC_API_KEY env var, OR pass --use-llm to the CLI.

Cost note: a typical mid-size audit (~30 cannib clusters + ~50 thin URLs +
~50 content ideas + 1 brand profile) costs roughly $0.05-0.15 with Claude Haiku 4.5.
The module is structured to batch where possible.

Usage:
    from src.llm_advisor import is_enabled, advise_cannibalization
    if is_enabled():
        result = advise_cannibalization(cluster_name, urls)
"""

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provider plumbing
# ---------------------------------------------------------------------------

DEFAULT_MODEL = os.environ.get("TAM_LLM_MODEL", "claude-haiku-4-5-20251001")
DEFAULT_PROVIDER = os.environ.get("TAM_LLM_PROVIDER", "").lower()

_CLIENT_CACHE: Optional[Any] = None


def is_enabled() -> bool:
    """Return True if LLM analysis should run (provider configured + key present)."""
    if DEFAULT_PROVIDER not in ("anthropic", "claude"):
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def enable_for_session() -> bool:
    """Force-enable for this Python process (sets the env var). Returns True if successful."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        logger.warning("Cannot enable LLM: ANTHROPIC_API_KEY not set")
        return False
    os.environ["TAM_LLM_PROVIDER"] = "anthropic"
    global DEFAULT_PROVIDER
    DEFAULT_PROVIDER = "anthropic"
    return True


def _client():
    global _CLIENT_CACHE
    if _CLIENT_CACHE is None:
        try:
            from anthropic import Anthropic
            _CLIENT_CACHE = Anthropic()
        except ImportError:
            logger.warning("anthropic SDK not installed; LLM disabled")
            _CLIENT_CACHE = False
        except Exception as e:
            logger.warning("Could not init Anthropic client: %s", e)
            _CLIENT_CACHE = False
    return _CLIENT_CACHE if _CLIENT_CACHE is not False else None


def _call(system: str, prompt: str, max_tokens: int = 1500) -> Optional[str]:
    """Single Claude call. Returns text or None on failure."""
    if not is_enabled():
        return None
    client = _client()
    if not client:
        return None
    try:
        msg = client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        # Extract text from the response
        parts = []
        for block in msg.content:
            if hasattr(block, "text"):
                parts.append(block.text)
        return "".join(parts).strip()
    except Exception as e:
        logger.warning("LLM call failed: %s", e)
        return None


def raw_completion(system: str, user: str, max_tokens: int = 1500) -> Optional[str]:
    """Public passthrough for one-off Claude calls (used by site_chat RAG Q&A)."""
    return _call(system, user, max_tokens=max_tokens)


def _parse_json(text: str) -> Optional[dict]:
    """Try to parse JSON from a model reply. Tolerates markdown code fences."""
    if not text:
        return None
    t = text.strip()
    # Strip ```json ... ``` fences
    if t.startswith("```"):
        t = t.strip("`")
        if t.startswith("json"):
            t = t[4:]
        t = t.strip()
        if "```" in t:
            t = t.split("```")[0].strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        # Try to find a JSON object inside the text
        import re
        m = re.search(r"\{.*\}", t, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return None


# ---------------------------------------------------------------------------
# Cannibalization analyzer
# ---------------------------------------------------------------------------

_CANNIB_SYSTEM = """You are a senior technical SEO auditor analyzing whether a group of URLs
on the same site is actually competing for the same search intent (cannibalization),
or whether the clustering algorithm grouped them incorrectly.

Real cannibalization REQUIRES:
- Multiple URLs targeting the same primary search intent (informational, commercial, etc.)
- Multiple URLs targeting overlapping head keywords or buyer journey stage
- The user gets the same kind of answer if they land on any of them

Things that LOOK like cannibalization but AREN'T:
- An author/team page mixed with blog posts (different page types entirely)
- A blog category/listing page mixed with the posts it lists (parent vs children)
- A pricing/demo/conversion page mixed with informational content (different funnel stage)
- A FAQ page mixed with topic pillars
- Pages with the same theme but clearly different audience or intent

You must produce STRICT JSON only. No prose."""


_CANNIB_PROMPT = """Cluster: {cluster_name}
Cluster keywords: {keywords}

URLs in this cluster ({n_urls}):
{url_list}

Analyze:
1. Is this REAL cannibalization (multiple URLs competing for same search intent)?
2. If yes, which is the WINNER (the URL that should rank, the others consolidate into it)?
3. For each URL, recommend: WINNER | MERGE | DIFFERENTIATE | EXCLUDE (page type doesn't belong in this cluster)

Output STRICT JSON only:
{{
  "is_cannibalization": true|false,
  "verdict_summary": "one sentence — what's actually happening here",
  "winner_url": "/the/winning/url" | null,
  "winner_reasoning": "why this URL wins (or null if no real cannibalization)",
  "per_url": [
    {{"url": "/some/url", "verdict": "WINNER|MERGE|DIFFERENTIATE|EXCLUDE", "action": "specific action sentence"}}
  ]
}}

Rules:
- If a URL is EXCLUDE, explain in `action` why it doesn't belong (e.g., "Author page — not competing for the same intent. Re-classify outside this cluster.")
- Action sentences should be specific (mention the winner URL by path when MERGE)
- If `is_cannibalization` is false, set winner_url to null and mark all URLs EXCLUDE with reasoning"""


def advise_cannibalization(
    cluster_name: str,
    keywords: list[str],
    urls: list[dict],
    chunks_by_url: Optional[dict] = None,
) -> Optional[dict]:
    """Ask the LLM whether a cluster is real cannibalization + per-URL action.

    urls: list of dicts with at least {url, slug, type, intent_primary?}.
    chunks_by_url: OPTIONAL dict {url: "first 500-800 chars of representative chunk"}.
                   When provided, the advisor sees actual page CONTENT and can make
                   a much sharper judgment than from URL patterns alone. This is the
                   RAG-enhanced path.

    Returns dict with keys is_cannibalization, verdict_summary, winner_url,
    winner_reasoning, per_url. Returns None if LLM disabled or call failed.
    """
    if not is_enabled() or not urls:
        return None

    lines = []
    for u in urls[:25]:
        slug = u.get("slug") or u.get("url")
        ptype = u.get("type", "unknown")
        intent = u.get("intent_primary") or "unknown"
        line = f"  - {slug} | type: {ptype} | intent: {intent}"
        if chunks_by_url:
            sample = chunks_by_url.get(u.get("url")) or chunks_by_url.get(slug)
            if sample:
                # Indent the content sample under the URL bullet
                sample_short = sample.strip().replace("\n", " ")[:500]
                line += f"\n      content: {sample_short}"
        lines.append(line)
    url_list = "\n".join(lines)

    prompt = _CANNIB_PROMPT.format(
        cluster_name=cluster_name,
        keywords=", ".join(keywords[:10]) if keywords else "(none)",
        n_urls=len(urls),
        url_list=url_list,
    )
    # When RAG content is included the prompt is meaningfully larger — bump the limit
    max_t = 3000 if chunks_by_url else 2000
    raw = _call(_CANNIB_SYSTEM, prompt, max_tokens=max_t)
    return _parse_json(raw) if raw else None


# ---------------------------------------------------------------------------
# Cluster naming (RAG-enhanced — replaces TF-IDF top-phrase names)
# ---------------------------------------------------------------------------

_CLUSTER_NAME_SYSTEM = """You are a senior SEO content strategist naming a topic cluster
from sample content excerpts. The current name was auto-generated by TF-IDF and is often
noisy ('make sure', 'according cox', 'octopus deploy'). Replace it with a clean, human-readable
2-4 word topic name that a writer would intuitively recognize.

Output STRICT JSON only."""


_CLUSTER_NAME_PROMPT = """Current cluster name (TF-IDF guess): "{current_name}"
Top keywords: {keywords}

Sample content from pages in this cluster ({n_samples} excerpts):
{samples}

Provide a clean 2-4 word topic name that captures what these pages are actually about.
Avoid generic words like "Guide" or "Best Practices". Use real topic vocabulary.

Output STRICT JSON:
{{
  "cluster_name": "Clean Topic Name",
  "reasoning": "one short sentence on why this name fits"
}}"""


def suggest_cluster_name(
    current_name: str,
    keywords: list[str],
    sample_chunks: list[str],
) -> Optional[dict]:
    """Ask the LLM to rename a noisy TF-IDF cluster from sample content.

    Returns {cluster_name, reasoning} or None if LLM disabled / call failed.
    """
    if not is_enabled() or not sample_chunks:
        return None
    samples = "\n\n".join(
        f"--- excerpt {i+1} ---\n{(c or '').strip()[:600]}"
        for i, c in enumerate(sample_chunks[:5])
    )
    prompt = _CLUSTER_NAME_PROMPT.format(
        current_name=current_name,
        keywords=", ".join(keywords[:8]) if keywords else "(none)",
        n_samples=len(sample_chunks[:5]),
        samples=samples,
    )
    raw = _call(_CLUSTER_NAME_SYSTEM, prompt, max_tokens=400)
    return _parse_json(raw) if raw else None


# ---------------------------------------------------------------------------
# Thin content judgment
# ---------------------------------------------------------------------------

_THIN_SYSTEM = """You are a senior technical SEO auditor reviewing a list of URLs flagged as
'thin content' by an automated word-count check. Many of these pages are NOT
genuinely thin content — they're intentionally focused single-feature landers,
conversion pages, demo pages, gated assets, etc. that don't NEED long-form text.

Your job: per URL, decide whether it's REAL thin content (a blog/article/service page
that should have been substantive but isn't) OR a false positive (intentionally focused
non-content page that should be excluded from the thin-content alert).

Output STRICT JSON only."""


_THIN_PROMPT = """Site: {site_name} ({site_domain})
Industry: {industry}

URLs flagged as thin (under 300 words):
{url_list}

For each URL, classify:
- "expand"   = real content page that's too short, the team SHOULD expand it
- "exclude"  = intentionally short page (lander, demo, conversion, asset gate, etc.) — should NOT be in the thin-content list
- "ambiguous" = unclear from the URL alone, manual review needed

Output STRICT JSON:
{{
  "judgments": [
    {{"url": "/url-1", "verdict": "expand|exclude|ambiguous", "reason": "one sentence"}}
  ]
}}"""


def advise_thin_content(site_name: str, site_domain: str, industry: Optional[str], urls: list[str]) -> Optional[dict]:
    """Per-URL judgment of which thin pages are real and which are false positives."""
    if not is_enabled() or not urls:
        return None
    url_list = "\n".join(f"  - {u}" for u in urls[:50])
    prompt = _THIN_PROMPT.format(
        site_name=site_name, site_domain=site_domain, industry=industry or "unknown",
        url_list=url_list,
    )
    raw = _call(_THIN_SYSTEM, prompt, max_tokens=3000)
    return _parse_json(raw) if raw else None


# ---------------------------------------------------------------------------
# Audience inference per topic
# ---------------------------------------------------------------------------

_AUDIENCE_SYSTEM = """You are an expert B2B content strategist. For each gap topic, identify
the SPECIFIC audience role/team that should care about this content. Be precise — avoid
generic labels like 'B2B teams' or 'marketing teams' if a more specific role fits.

Examples of GOOD audience labels:
- "Product marketers at PLG SaaS companies"
- "Founders + GTM leads at series A B2B SaaS"
- "ABM strategists running enterprise pilots"
- "Customer research operations leads"

Output STRICT JSON only."""


_AUDIENCE_PROMPT = """Site: {site_name} (industry: {industry})

For each topic below, identify the most specific audience that would search for this
and consume it. The audience should be the role or team that benefits most.

Topics:
{topic_list}

Output STRICT JSON:
{{
  "audiences": [
    {{"topic": "topic-1", "audience": "specific role/team label"}}
  ]
}}"""


def advise_audiences(site_name: str, industry: Optional[str], topics: list[str]) -> Optional[dict]:
    """Batch infer audience labels for a list of gap topics."""
    if not is_enabled() or not topics:
        return None
    topic_list = "\n".join(f"  - {t}" for t in topics[:60])
    prompt = _AUDIENCE_PROMPT.format(
        site_name=site_name, industry=industry or "unknown",
        topic_list=topic_list,
    )
    raw = _call(_AUDIENCE_SYSTEM, prompt, max_tokens=3000)
    return _parse_json(raw) if raw else None


# ---------------------------------------------------------------------------
# Brand voice profile from sampled site content
# ---------------------------------------------------------------------------

_BRAND_SYSTEM = """You are a brand strategist analyzing the writing voice of a website
based on sampled page content. Distill the brand voice into a structured profile that
the team can use as a style guide for new content.

Output STRICT JSON only."""


_BRAND_PROMPT = """Site: {site_name} ({site_domain})
Industry: {industry}

Below are 5-10 representative samples of the site's content (first 500 chars of each):

{samples}

Distill a brand voice profile. Output STRICT JSON:
{{
  "brand_name": "{site_name}",
  "tone": ["3-5 tone descriptors that match how they write"],
  "writing_style": {{
    "sentence_length": "short|medium|long",
    "complexity": "basic|intermediate|advanced",
    "person": "first|second|third"
  }},
  "audience": "who they appear to be writing for, in 1 sentence",
  "do": ["4-6 things their writing consistently does well"],
  "dont": ["4-6 things they avoid or that would feel off-brand"],
  "example_phrases": ["3-5 short phrases pulled from the samples that exemplify the voice"],
  "tone_lexicon": {{
    "tone1": ["5-8 words that signal this tone in their writing"],
    "tone2": ["..."]
  }}
}}"""


def generate_brand_profile(site_name: str, site_domain: str, industry: Optional[str], samples: list[str]) -> Optional[dict]:
    """Generate a brand voice profile from sampled page content."""
    if not is_enabled() or not samples:
        return None
    sample_block = "\n\n---\n\n".join(s[:500] for s in samples[:10])
    prompt = _BRAND_PROMPT.format(
        site_name=site_name, site_domain=site_domain, industry=industry or "unknown",
        samples=sample_block,
    )
    raw = _call(_BRAND_SYSTEM, prompt, max_tokens=2500)
    return _parse_json(raw) if raw else None


# ---------------------------------------------------------------------------
# Refine competitor gap topics into specific actionable themes
# ---------------------------------------------------------------------------

_COMPETITOR_TOPICS_SYSTEM = """You are a senior B2B content strategist. You're given a list of
broad / noisy gap topics extracted from competitor sites via TF-IDF clustering. Your job is to
turn these into SPECIFIC, ACTIONABLE content themes that a writer could brief.

Drop noise (sentence fragments, person names, product feature names from a single competitor,
overly broad terms like 'best practices'). Group related raw topics under a single specific theme.

Output STRICT JSON only."""


_COMPETITOR_TOPICS_PROMPT = """Site: {site_name} (industry: {industry})

Raw gap topics extracted from competitors:
{topic_list}

Refine into 10-25 SPECIFIC, ACTIONABLE content themes. For each theme:
- title: a clear, narrow content theme (NOT a broad category)
- raw_sources: which raw topics from above this theme covers
- why_specific: 1 sentence on why this is actionable vs the original raw topic

Output STRICT JSON:
{{
  "themes": [
    {{"title": "specific theme title", "raw_sources": ["raw-topic-1"], "why_specific": "..."}}
  ]
}}"""


def refine_competitor_topics(site_name: str, industry: Optional[str], raw_topics: list[str]) -> Optional[dict]:
    """Take noisy raw gap topics, return specific actionable themes via LLM judgment."""
    if not is_enabled() or not raw_topics:
        return None
    topic_list = "\n".join(f"  - {t}" for t in raw_topics[:80])
    prompt = _COMPETITOR_TOPICS_PROMPT.format(
        site_name=site_name, industry=industry or "unknown",
        topic_list=topic_list,
    )
    raw = _call(_COMPETITOR_TOPICS_SYSTEM, prompt, max_tokens=3000)
    return _parse_json(raw) if raw else None


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    enable_for_session()
    if not is_enabled():
        print("LLM not enabled. Set ANTHROPIC_API_KEY + TAM_LLM_PROVIDER=anthropic.")
    else:
        print("Testing cannibalization analyzer with a synthetic example...")
        result = advise_cannibalization(
            "Marketing Leaders",
            ["brand awareness", "marketing leaders", "brand measurement"],
            [
                {"slug": "/author/kate-meda", "type": "author", "intent_primary": "navigational"},
                {"slug": "/blog", "type": "listing", "intent_primary": "navigational"},
                {"slug": "/blog-category/buyer-intelligence", "type": "listing", "intent_primary": "navigational"},
                {"slug": "/post/8-lessons-learned-pricing", "type": "blog", "intent_primary": "informational"},
                {"slug": "/post/b2b-messaging", "type": "blog", "intent_primary": "informational"},
                {"slug": "/instant-demo", "type": "service", "intent_primary": "transactional"},
            ],
        )
        print(json.dumps(result, indent=2) if result else "(no result)")
