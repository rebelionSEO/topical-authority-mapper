"""
Enhancements module: similarity scoring, intent classification, internal linking,
cluster merge detection, content freshness, brand voice scoring, and page type classification.
"""

import json
import logging
import os
import re
from collections import Counter, defaultdict

import faiss
import numpy as np
import pandas as pd

from src.config import cache_dir, extra_listing_patterns, output_dir


# ---------------------------------------------------------------------------
# Page type classification
# ---------------------------------------------------------------------------

# Listing/archive pages that are INTENTIONALLY thin — exclude from thin content flagging
LISTING_PAGE_PATTERNS = [
    r"^https?://[^/]+/blog/?$",
    r"^https?://[^/]+/webinars/?$",
    r"^https?://[^/]+/case-studies/?$",
    r"^https?://[^/]+/podcasts?/?$",
    r"^https?://[^/]+/featured-podcasts/?$",
    r"^https?://[^/]+/careers/?$",
    r"^https?://[^/]+/about-us/?$",
    r"^https?://[^/]+/contact-us/?$",
    r"^https?://[^/]+/partner-with-us/?$",
    r"^https?://[^/]+/referral-program/?$",
    r"^https?://[^/]+/guides/[^/]+/?$",
    r"^https?://[^/]+/ai-tools/?$",
    r"^https?://[^/]+/geo-tools/?$",
    r"^https?://[^/]+/calculators/?$",
    r"^https?://[^/]+/industries/[^/]+/?$",  # industry hub pages
]


def classify_page_type(url: str) -> str:
    """Classify a URL into a page type based on URL patterns."""
    u = url.lower().rstrip("/")

    # Service pages (money pages)
    if "/services/" in u or u.endswith("/services"):
        return "service"

    # Industry pages
    if "/industries/" in u:
        depth = u.replace("https://", "").count("/")
        if depth <= 3:
            return "industry-hub"
        return "industry"

    # Case studies
    if "/case-stud" in u:
        if u.endswith("/case-studies"):
            return "listing"
        return "case-study"

    # Tools/resources
    if "/content-marketing-tools/" in u or "/marketing-tools/" in u:
        return "tool-review"
    if "/ai-tools/" in u and u.count("/") > 3:
        return "tool-review"

    # Local landing pages
    if any(p in u for p in ["/seo-services-for-", "/digital-marketing-for-", "/digital-marketing-services-for-",
                             "/web-design-services-"]):
        return "local-landing"

    # Webinar pages
    if "/webinar" in u:
        return "webinar"

    # Listing/archive pages
    for pattern in LISTING_PAGE_PATTERNS:
        if re.match(pattern, url, re.IGNORECASE):
            return "listing"

    # Homepage
    if re.match(r"^https?://[^/]+/?$", u):
        return "homepage"

    # Default: blog/article content
    return "blog"


def is_intentionally_thin(url: str) -> bool:
    """Check if a page is expected to be thin (listing, hub, archive, etc.).

    Combines built-in patterns + page-type classifier + per-site custom regexes from
    SiteConfig.listing_patterns.
    """
    for pattern in extra_listing_patterns():
        try:
            if re.match(pattern, url, re.IGNORECASE):
                return True
        except re.error:
            continue
    ptype = classify_page_type(url)
    return ptype in ("listing", "industry-hub", "homepage")

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# #1 — Similarity scoring between URLs in the same cluster
# ---------------------------------------------------------------------------

def compute_similarity_scores(chunks_df: pd.DataFrame, embeddings: np.ndarray) -> pd.DataFrame:
    """
    Compute pairwise cosine similarity between URLs within the same cluster.
    Returns a DataFrame of URL pairs with similarity scores, sorted by similarity desc.
    """
    logger.info("Computing intra-cluster similarity scores...")

    # Average embeddings per URL
    url_embeddings = {}
    for url, group in chunks_df.groupby("url"):
        indices = group.index.tolist()
        valid = [i for i in indices if i < len(embeddings)]
        if valid:
            url_embeddings[url] = np.mean(embeddings[valid], axis=0)

    # Build FAISS index per cluster
    results = []
    for cluster_id, group in chunks_df[chunks_df["cluster_id"] != -1].groupby("cluster_id"):
        cluster_urls = list(set(group["url"].tolist()))
        if len(cluster_urls) < 2:
            continue

        # Get embeddings for URLs in this cluster
        vecs = []
        valid_urls = []
        for u in cluster_urls:
            if u in url_embeddings:
                vecs.append(url_embeddings[u])
                valid_urls.append(u)

        if len(valid_urls) < 2:
            continue

        vecs = np.array(vecs, dtype=np.float32)
        # Normalize for cosine similarity
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1
        vecs_normed = vecs / norms

        # Pairwise cosine similarity
        sim_matrix = np.dot(vecs_normed, vecs_normed.T)

        for i in range(len(valid_urls)):
            for j in range(i + 1, len(valid_urls)):
                score = float(sim_matrix[i][j])
                type_a = classify_page_type(valid_urls[i])
                type_b = classify_page_type(valid_urls[j])
                action = _similarity_action(score, type_a, type_b)

                # Determine severity
                money_pages = {"service", "industry", "local-landing", "homepage"}
                info_pages = {"blog", "tool-review", "webinar"}
                types = {type_a, type_b}
                is_conversion_risk = bool(types & money_pages) and bool(types & info_pages)

                results.append({
                    "cluster_id": cluster_id,
                    "url_a": valid_urls[i],
                    "url_b": valid_urls[j],
                    "type_a": type_a,
                    "type_b": type_b,
                    "similarity": round(score, 4),
                    "conversion_risk": is_conversion_risk,
                    "action": action,
                })

    df = pd.DataFrame(results)
    if not df.empty:
        # Sort: conversion risks first, then by similarity
        df = df.sort_values(["conversion_risk", "similarity"], ascending=[False, False])

    # Save
    out_path = os.path.join(output_dir(), "similarity_scores.csv")
    df.to_csv(out_path, index=False)
    logger.info("Saved %d similarity pairs to %s", len(df), out_path)
    return df


def _similarity_action(score: float, type_a: str = "", type_b: str = "") -> str:
    # Check for blog-vs-service cannibalization (conversion risk)
    money_pages = {"service", "industry", "local-landing", "homepage"}
    info_pages = {"blog", "tool-review", "webinar"}
    types = {type_a, type_b}
    is_conversion_risk = bool(types & money_pages) and bool(types & info_pages)

    if is_conversion_risk:
        money = type_a if type_a in money_pages else type_b
        info = type_a if type_a in info_pages else type_b
        return f"CRITICAL: {info} page may outrank {money} page — cannibalizing conversions"

    if score >= 0.92:
        return "MERGE: near-duplicate content — consolidate into one page"
    if score >= 0.80:
        return "REVIEW: very similar — differentiate angles or merge"
    if score >= 0.65:
        return "DIFFERENTIATE: overlap exists — ensure unique intent per page"
    return "OK: sufficiently different content"


# ---------------------------------------------------------------------------
# #2 — Search intent classification per chunk/URL
# ---------------------------------------------------------------------------

INTENT_PATTERNS = {
    "transactional": [
        r"\b(buy|purchase|order|pricing|price|cost|free trial|sign up|subscribe|get started|demo|quote)\b",
        r"\b(coupon|discount|deal|sale|checkout|add to cart)\b",
        r"\b(agency|service|hire|consultation|contact us)\b",
    ],
    "commercial": [
        r"\b(best|top|review|compare|comparison|vs|versus|alternative)\b",
        r"\b(recommended|rated|pros and cons|benchmark)\b",
        r"\b(tools|software|platform|solution|provider)\b",
    ],
    "informational": [
        r"\b(what is|how to|how do|guide|tutorial|learn|understand|explain)\b",
        r"\b(definition|meaning|example|tips|strategies|techniques)\b",
        r"\b(benefits|advantages|why|when|overview)\b",
    ],
    "navigational": [
        r"\b(login|sign in|account|dashboard|support|contact)\b",
        r"\b(about us|our team|careers|blog)\b",
    ],
}


def classify_search_intent(chunks_df: pd.DataFrame) -> pd.DataFrame:
    """Classify search intent for each URL based on content analysis."""
    logger.info("Classifying search intent for %d URLs...", chunks_df["url"].nunique())

    url_intents = []
    for url, group in chunks_df.groupby("url"):
        text = " ".join(group["chunk_text"].tolist()).lower()
        scores = {}

        for intent, patterns in INTENT_PATTERNS.items():
            count = 0
            for pattern in patterns:
                count += len(re.findall(pattern, text))
            scores[intent] = count

        total = sum(scores.values())
        if total == 0:
            primary = "informational"
            confidence = 0.5
        else:
            primary = max(scores, key=scores.get)
            confidence = round(scores[primary] / total, 2)

        # Secondary intent
        sorted_intents = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        secondary = sorted_intents[1][0] if len(sorted_intents) > 1 and sorted_intents[1][1] > 0 else ""

        url_intents.append({
            "url": url,
            "primary_intent": primary,
            "secondary_intent": secondary,
            "confidence": confidence,
            "transactional_signals": scores.get("transactional", 0),
            "commercial_signals": scores.get("commercial", 0),
            "informational_signals": scores.get("informational", 0),
            "navigational_signals": scores.get("navigational", 0),
        })

    df = pd.DataFrame(url_intents)

    out_path = os.path.join(output_dir(), "search_intent.csv")
    df.to_csv(out_path, index=False)
    logger.info("Saved search intent for %d URLs to %s", len(df), out_path)
    return df


# ---------------------------------------------------------------------------
# #4 — Internal linking analysis (from SF crawl data)
# ---------------------------------------------------------------------------

def analyze_internal_links(internal_csv_path: str, url_map: pd.DataFrame, clusters: pd.DataFrame) -> pd.DataFrame:
    """
    Analyze internal linking from Screaming Frog export.
    Merges inlink counts with cluster assignments.
    """
    logger.info("Analyzing internal links from %s", internal_csv_path)

    sf = pd.read_csv(internal_csv_path, low_memory=False)

    # Filter to HTML pages only
    sf_html = sf[sf["Content Type"].str.contains("text/html", na=False)].copy()

    # Select relevant columns
    link_data = sf_html[["Address", "Inlinks", "Unique Inlinks", "Outlinks", "Unique Outlinks", "Crawl Depth"]].copy()
    link_data.columns = ["url", "inlinks", "unique_inlinks", "outlinks", "unique_outlinks", "crawl_depth"]

    # Merge with cluster data
    merged = link_data.merge(url_map[["url", "main_cluster"]], on="url", how="left")
    merged = merged.merge(clusters[["cluster_id", "cluster_name"]], left_on="main_cluster", right_on="cluster_id", how="left")

    # Flag under-linked pages
    median_inlinks = merged["unique_inlinks"].median()
    merged["linking_status"] = merged["unique_inlinks"].apply(
        lambda x: "orphan" if x <= 1 else "under-linked" if x < median_inlinks * 0.5 else "well-linked"
    )

    # Cluster-level link health
    cluster_link_health = merged.groupby("cluster_name").agg(
        avg_inlinks=("unique_inlinks", "mean"),
        min_inlinks=("unique_inlinks", "min"),
        orphan_count=("linking_status", lambda x: (x == "orphan").sum()),
        page_count=("url", "count"),
    ).round(1).sort_values("avg_inlinks", ascending=True)

    # Save
    out_path = os.path.join(output_dir(), "internal_linking.csv")
    merged.to_csv(out_path, index=False)

    cluster_link_path = os.path.join(output_dir(), "cluster_link_health.csv")
    cluster_link_health.to_csv(cluster_link_path)

    logger.info("Saved internal linking data to %s", out_path)
    logger.info("Saved cluster link health to %s", cluster_link_path)
    return merged


# ---------------------------------------------------------------------------
# #6 — Cluster merge detection (near-duplicate clusters)
# ---------------------------------------------------------------------------

def detect_cluster_merges(clusters: pd.DataFrame, chunks_df: pd.DataFrame, embeddings: np.ndarray) -> pd.DataFrame:
    """
    Detect clusters that should potentially be merged based on
    centroid similarity between clusters.
    """
    logger.info("Detecting potential cluster merges...")

    # Compute cluster centroids
    centroids = {}
    for cid, group in chunks_df[chunks_df["cluster_id"] != -1].groupby("cluster_id"):
        indices = group.index.tolist()
        valid = [i for i in indices if i < len(embeddings)]
        if valid:
            centroid = np.mean(embeddings[valid], axis=0)
            centroids[cid] = centroid / (np.linalg.norm(centroid) + 1e-10)

    cluster_ids = list(centroids.keys())
    if len(cluster_ids) < 2:
        return pd.DataFrame()

    vecs = np.array([centroids[cid] for cid in cluster_ids], dtype=np.float32)
    sim_matrix = np.dot(vecs, vecs.T)

    # Find similar cluster pairs
    results = []
    cluster_names = dict(zip(clusters["cluster_id"], clusters["cluster_name"]))

    for i in range(len(cluster_ids)):
        for j in range(i + 1, len(cluster_ids)):
            score = float(sim_matrix[i][j])
            if score >= 0.70:  # threshold for merge suggestion
                cid_a, cid_b = cluster_ids[i], cluster_ids[j]
                results.append({
                    "cluster_a_id": cid_a,
                    "cluster_a_name": cluster_names.get(cid_a, ""),
                    "cluster_b_id": cid_b,
                    "cluster_b_name": cluster_names.get(cid_b, ""),
                    "similarity": round(score, 4),
                    "recommendation": "MERGE" if score >= 0.85 else "REVIEW for merge",
                })

    df = pd.DataFrame(results).sort_values("similarity", ascending=False) if results else pd.DataFrame()

    out_path = os.path.join(output_dir(), "cluster_merge_suggestions.csv")
    df.to_csv(out_path, index=False)
    logger.info("Found %d potential cluster merges", len(df))
    return df


# ---------------------------------------------------------------------------
# #7 — Content freshness scoring
# ---------------------------------------------------------------------------

def score_content_freshness(sitemap_urls: list[str] | None = None) -> pd.DataFrame:
    """
    Extract lastmod from sitemap(s) and score freshness.

    sitemap_urls: explicit list of sitemap URLs to crawl. If omitted, falls back
    to the sitemaps recorded in the cached SiteConfig (cache/site_config.json).
    """
    import xml.etree.ElementTree as ET
    import requests

    from src.config import load_site_config

    logger.info("Scoring content freshness from sitemaps...")

    if not sitemap_urls:
        site = load_site_config()
        sitemap_urls = list(site.sitemaps) if site else []

    if not sitemap_urls:
        logger.warning("No sitemap URLs provided and none in SiteConfig — skipping freshness scoring")
        return pd.DataFrame()

    url_dates = {}
    for sm_url in sitemap_urls:
        try:
            resp = requests.get(sm_url, timeout=15)
            root = ET.fromstring(resp.content)
            ns = ""
            if root.tag.startswith("{"):
                ns = root.tag.split("}")[0] + "}"

            for entry in root.findall(f"{ns}url"):
                loc = entry.find(f"{ns}loc")
                lastmod = entry.find(f"{ns}lastmod")
                if loc is not None and loc.text and lastmod is not None and lastmod.text:
                    url_dates[loc.text.strip()] = lastmod.text.strip()[:10]
        except Exception as e:
            logger.warning("Failed to parse sitemap %s: %s", sm_url, e)

    if not url_dates:
        logger.warning("No lastmod data found in sitemaps")
        return pd.DataFrame()

    from datetime import datetime, timedelta
    today = datetime.now()

    results = []
    for url, date_str in url_dates.items():
        try:
            lastmod = datetime.strptime(date_str, "%Y-%m-%d")
            age_days = (today - lastmod).days
            freshness = _freshness_label(age_days)
            results.append({
                "url": url,
                "lastmod": date_str,
                "age_days": age_days,
                "freshness": freshness,
            })
        except ValueError:
            continue

    df = pd.DataFrame(results).sort_values("age_days", ascending=False)

    out_path = os.path.join(output_dir(), "content_freshness.csv")
    df.to_csv(out_path, index=False)
    logger.info("Scored freshness for %d URLs", len(df))
    return df


def _freshness_label(age_days: int) -> str:
    if age_days <= 30:
        return "Fresh (< 1 month)"
    if age_days <= 90:
        return "Recent (1-3 months)"
    if age_days <= 180:
        return "Aging (3-6 months)"
    if age_days <= 365:
        return "Stale (6-12 months)"
    return "Decaying (12+ months)"


# ---------------------------------------------------------------------------
# #8 — Brand voice scoring per URL
# ---------------------------------------------------------------------------

def score_brand_voice(chunks_df: pd.DataFrame) -> pd.DataFrame:
    """
    Score each URL's content against the brand voice profile.
    Checks tone alignment, do/don't adherence, and writing style match.
    """
    profile_path = os.path.join(cache_dir(), "brand_profile.json")
    if not os.path.exists(profile_path):
        logger.warning("No brand profile found at %s — skipping brand voice scoring", profile_path)
        return pd.DataFrame()

    with open(profile_path, "r") as f:
        profile = json.load(f)

    logger.info("Scoring brand voice alignment for %d URLs...", chunks_df["url"].nunique())

    tone_words = [t.lower() for t in profile.get("tone", [])]
    do_phrases = [d.lower() for d in profile.get("do", [])]
    dont_phrases = [d.lower() for d in profile.get("dont", [])]
    example_phrases = [e.lower() for e in profile.get("example_phrases", [])]

    # Tone-word lexicon. Generic, industry-agnostic defaults that the brand profile can
    # override or extend by adding a "tone_lexicon" dict to brand_profile.json.
    tone_lexicon = _resolve_tone_lexicon(profile)

    results = []
    for url, group in chunks_df.groupby("url"):
        text = " ".join(group["chunk_text"].tolist()).lower()
        words = text.split()
        word_count = len(words)
        if word_count == 0:
            continue

        # Tone alignment score (0-100)
        tone_score = 0
        tone_matches = []
        for tone in tone_words:
            lexicon = tone_lexicon.get(tone, [tone])
            matches = sum(1 for w in lexicon if w in text)
            if matches > 0:
                tone_score += 1
                tone_matches.append(tone)
        tone_pct = round((tone_score / max(len(tone_words), 1)) * 100)

        # Writing style check
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 5]
        avg_sentence_len = np.mean([len(s.split()) for s in sentences]) if sentences else 0

        target_style = profile.get("writing_style", {})
        target_len = target_style.get("sentence_length", "short")
        style_match = False
        if target_len == "short" and avg_sentence_len <= 15:
            style_match = True
        elif target_len == "medium" and 12 <= avg_sentence_len <= 22:
            style_match = True
        elif target_len == "long" and avg_sentence_len >= 18:
            style_match = True

        # Don't violations
        violations = []
        if "avoid fluff" in " ".join(dont_phrases) and any(w in text for w in ["very", "really", "extremely", "absolutely", "incredible"]):
            violations.append("fluff words detected")
        if "avoid jargon" in " ".join(dont_phrases) and any(w in text for w in ["synergy", "leverage", "paradigm", "holistic"]):
            violations.append("jargon detected")
        if "passive voice" in " ".join(dont_phrases) and text.count(" is being ") + text.count(" was being ") + text.count(" are being ") > 2:
            violations.append("excessive passive voice")

        # Overall score (0-100)
        overall = tone_pct * 0.5 + (30 if style_match else 0) + (20 if not violations else 0)

        results.append({
            "url": url,
            "brand_score": round(min(overall, 100)),
            "tone_alignment": f"{tone_pct}%",
            "tone_matches": ", ".join(tone_matches) if tone_matches else "none",
            "style_match": "Yes" if style_match else "No",
            "avg_sentence_length": round(avg_sentence_len, 1),
            "violations": "; ".join(violations) if violations else "none",
            "rating": _brand_rating(overall),
        })

    df = pd.DataFrame(results).sort_values("brand_score", ascending=True)

    out_path = os.path.join(output_dir(), "brand_voice_scores.csv")
    df.to_csv(out_path, index=False)
    logger.info("Saved brand voice scores to %s", out_path)
    return df


DEFAULT_TONE_LEXICON = {
    # Generic, industry-agnostic tone words. Anything more specific (e.g. growth metrics
    # like CAC/ROAS/LTV) should be added to the brand profile's tone_lexicon override.
    "professional": ["expertise", "experience", "industry", "best practices", "standards"],
    "casual": ["honestly", "kind of", "yeah", "stuff", "just"],
    "technical": ["specification", "architecture", "implementation", "system", "process"],
    "friendly": ["welcome", "happy", "love", "enjoy", "appreciate"],
    "authoritative": ["proven", "established", "leading", "definitive", "comprehensive"],
    "playful": ["fun", "exciting", "amazing", "cool", "delightful"],
    "concise": ["clear", "simple", "direct", "straightforward", "essential"],
    "data-driven": ["data", "metrics", "research", "study", "measure", "evidence"],
    "innovative": ["new", "novel", "breakthrough", "innovative", "pioneering"],
    "trustworthy": ["transparent", "honest", "reliable", "trusted", "accountable"],
    "strategic": ["strategy", "framework", "roadmap", "approach", "plan"],
    "decisive": ["clear", "focused", "confident", "definitive"],
    "confident": ["deliver", "drive", "results", "performance"],
    "direct": ["straight", "actionable", "no fluff", "to the point"],
    "experimental": ["test", "experiment", "iterate", "launch", "sprint"],
    "warm": ["thoughtful", "caring", "support", "together", "human"],
    "bold": ["challenge", "rethink", "disrupt", "bold", "unflinching"],
}


def _resolve_tone_lexicon(profile: dict) -> dict:
    """Merge the brand-profile-provided lexicon (if any) on top of the generic defaults."""
    lex = {k: list(v) for k, v in DEFAULT_TONE_LEXICON.items()}
    override = profile.get("tone_lexicon") or {}
    if isinstance(override, dict):
        for tone, words in override.items():
            if isinstance(words, list):
                lex[tone.lower()] = [str(w).lower() for w in words]
    return lex


def _brand_rating(score: float) -> str:
    if score >= 75:
        return "On-brand"
    if score >= 50:
        return "Partially aligned"
    if score >= 25:
        return "Needs work"
    return "Off-brand"


# ---------------------------------------------------------------------------
# #5 — Competitor gap analysis
# ---------------------------------------------------------------------------

GENERIC_STOPWORDS = {
    "marketing", "content", "seo", "ads", "ai", "digital", "data", "strategy",
    "guide", "tips", "tools", "best", "online", "business", "growth", "brand",
    "page", "search", "social", "media", "web", "agency", "services", "campaign",
    "advertising", "management", "platform", "software", "email", "video",
    "google", "facebook", "2024", "2025", "2026", "free", "new", "top", "how",
}


def competitor_gap_analysis(
    target_clusters: pd.DataFrame,
    competitor_clusters: pd.DataFrame,
    competitor_name: str,
    target_name: str | None = None,
) -> pd.DataFrame:
    """
    Compare cluster topics between the target site and a competitor.
    Filters out single-word generic terms. Only keeps multi-word, intent-bearing topics.

    target_name: display label for the target site in the status column. If omitted,
    falls back to the cached SiteConfig name, then to "TARGET".
    """
    if target_name is None:
        from src.config import load_site_config

        site = load_site_config()
        target_name = site.name if site else "TARGET"

    logger.info("Running competitor gap analysis: %s vs %s", target_name, competitor_name)

    def _extract_topics(clusters_df):
        """Extract meaningful multi-word keyphrases from cluster keywords."""
        topics = set()
        for _, row in clusters_df.iterrows():
            # Add cluster name (already specific)
            name = row["cluster_name"].strip().lower()
            if len(name.split()) >= 2:
                topics.add(name)

            # Add multi-word keywords only (2+ words, not generic)
            kws = [k.strip().lower() for k in row["keywords"].split(",")]
            for kw in kws:
                words = kw.split()
                if len(words) < 2:
                    continue
                # Skip if all words are generic stopwords
                if all(w in GENERIC_STOPWORDS for w in words):
                    continue
                # Skip if it's just "X marketing" or "marketing X" with a generic word
                if len(words) == 2 and words[0] in GENERIC_STOPWORDS and words[1] in GENERIC_STOPWORDS:
                    continue
                topics.add(kw)
        return topics

    target_topics = _extract_topics(target_clusters)
    comp_topics = _extract_topics(competitor_clusters)

    # Fuzzy matching: consider topics as matching if one contains the other
    target_matched = set()
    comp_matched = set()
    shared_pairs = []

    for tt in target_topics:
        for ct in comp_topics:
            if tt == ct or (len(tt) > 5 and tt in ct) or (len(ct) > 5 and ct in tt):
                target_matched.add(tt)
                comp_matched.add(ct)
                if tt == ct:
                    shared_pairs.append(tt)
                else:
                    shared_pairs.append(f"{tt} / {ct}")

    target_only = target_topics - target_matched
    comp_only = comp_topics - comp_matched
    shared = set(shared_pairs)

    results = []
    for kw in sorted(comp_only):
        results.append({"keyword": kw, "status": "GAP: competitor covers, you don't", "competitor": competitor_name})
    for kw in sorted(target_only):
        results.append({"keyword": kw, "status": "ADVANTAGE: you cover, competitor doesn't", "competitor": competitor_name})
    for kw in sorted(shared):
        results.append({"keyword": kw, "status": "SHARED: both cover", "competitor": competitor_name})

    df = pd.DataFrame(results)

    out_path = os.path.join(output_dir(), f"competitor_gap_{competitor_name.lower().replace(' ', '_')}.csv")
    df.to_csv(out_path, index=False)
    logger.info("Gap analysis: %d gaps, %d advantages, %d shared topics (filtered to multi-word intent-bearing terms)",
                len(comp_only), len(target_only), len(shared))
    return df
