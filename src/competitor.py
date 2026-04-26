"""Competitor auto-crawl: ingest a competitor site's sitemap, cluster it, run gap analysis.

Triggered by the --competitor flag in src.main, or callable directly:

    from src.competitor import run_competitor_analyses
    run_competitor_analyses(["sparktoro.com", "maze.co"], target_clusters_df, "Acme")
"""

import logging
import os
import re
from typing import Optional
from urllib.parse import urlparse

import pandas as pd
import requests

from src.clustering import cluster_embeddings, extract_cluster_keywords, reduce_dimensions
from src.config import output_dir
from src.embedding import compute_embeddings
from src.enhancements import competitor_gap_analysis
from src.ingestion import ingest_urls, parse_sitemap

logger = logging.getLogger(__name__)


SITEMAP_CANDIDATES = (
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap-index.xml",
    "/post-sitemap.xml",
)


def _normalize_input(competitor: str) -> tuple[str, str]:
    """Return (display_name, sitemap_url_or_domain).

    Accepts: 'acme.com', 'https://acme.com', 'https://acme.com/sitemap.xml'.
    """
    raw = competitor.strip()
    if raw.endswith(".xml"):
        parsed = urlparse(raw)
        domain = parsed.netloc or raw
    else:
        domain = raw.replace("https://", "").replace("http://", "").rstrip("/")
        parsed = None

    bare = domain.replace("www.", "")
    name = bare.split(".")[0].title() if bare else domain
    return name, raw if raw.endswith(".xml") else domain


def _resolve_sitemap(domain_or_url: str) -> Optional[str]:
    """Return a working sitemap URL, or None if none of the candidates respond."""
    if domain_or_url.endswith(".xml"):
        return domain_or_url

    domain = domain_or_url
    bare = domain.replace("www.", "")
    candidates = []
    for host in [domain, f"www.{bare}", bare]:
        for path in SITEMAP_CANDIDATES:
            candidates.append(f"https://{host}{path}")

    seen = set()
    for url in candidates:
        if url in seen:
            continue
        seen.add(url)
        try:
            resp = requests.get(url, timeout=10, allow_redirects=True)
            if resp.status_code == 200 and (b"<urlset" in resp.content or b"<sitemapindex" in resp.content):
                logger.info("Resolved sitemap for %s -> %s", domain_or_url, url)
                return url
        except requests.RequestException:
            continue

    logger.warning("Could not auto-discover sitemap for %s (tried %d URLs)", domain_or_url, len(candidates))
    return None


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "competitor"


def crawl_and_cluster_competitor(
    competitor: str,
    target_clusters: pd.DataFrame,
    target_name: str,
    max_urls: int = 100,
) -> Optional[tuple[str, pd.DataFrame]]:
    """Run the mini-pipeline on one competitor and write its cluster + gap CSVs.

    Returns (display_name, gap_dataframe) on success, None on failure.
    """
    display_name, sitemap_or_domain = _normalize_input(competitor)
    logger.info("=== Competitor: %s (input: %s) ===", display_name, competitor)

    sitemap_url = _resolve_sitemap(sitemap_or_domain)
    if not sitemap_url:
        logger.error("Skipping competitor %s — no sitemap found", display_name)
        return None

    urls = parse_sitemap(sitemap_url)
    if not urls:
        logger.error("Empty sitemap for competitor %s (%s)", display_name, sitemap_url)
        return None

    if len(urls) > max_urls:
        logger.info("Competitor %s has %d URLs — limiting to %d", display_name, len(urls), max_urls)
        urls = urls[:max_urls]

    chunks_df, _skipped = ingest_urls(urls)
    if chunks_df.empty:
        logger.error("No content extracted from competitor %s", display_name)
        return None

    embeddings = compute_embeddings(texts=chunks_df["chunk_text"].tolist(), cache_path=None)

    reduced = reduce_dimensions(embeddings)
    labels = cluster_embeddings(reduced)
    chunks_df["cluster_id"] = labels

    cluster_info = extract_cluster_keywords(chunks_df)
    if cluster_info.empty:
        logger.warning("No clusters formed for competitor %s — skipping gap analysis", display_name)
        return None

    out = output_dir()
    os.makedirs(out, exist_ok=True)
    safe = _slugify(display_name)
    cluster_csv = os.path.join(out, f"competitor_{safe}_clusters.csv")
    cluster_info.to_csv(cluster_csv, index=False)
    logger.info("Saved competitor clusters: %s", cluster_csv)

    gap_df = competitor_gap_analysis(target_clusters, cluster_info, display_name, target_name=target_name)
    return display_name, gap_df


def run_competitor_analyses(
    competitors: list[str],
    target_clusters: pd.DataFrame,
    target_name: str,
    max_urls_per_competitor: int = 100,
) -> list[str]:
    """Run gap analysis for every competitor. Returns the names that succeeded."""
    succeeded = []
    for c in competitors:
        try:
            result = crawl_and_cluster_competitor(
                c, target_clusters, target_name, max_urls=max_urls_per_competitor
            )
            if result:
                succeeded.append(result[0])
        except Exception:
            logger.exception("Failed to process competitor %r", c)
    return succeeded
