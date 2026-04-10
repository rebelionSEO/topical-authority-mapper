"""Output generation: CSV exports and cannibalization detection."""

import logging
import os

import pandas as pd

from src.config import CANNIBALIZATION_URL_THRESHOLD, OUTPUT_DIR

logger = logging.getLogger(__name__)


def detect_cannibalization(url_mapping: pd.DataFrame, cluster_info: pd.DataFrame) -> pd.DataFrame:
    """
    Identify clusters where multiple URLs compete for the same topic.

    Flags clusters with more URLs than CANNIBALIZATION_URL_THRESHOLD.
    """
    cluster_url_counts = url_mapping.groupby("main_cluster")["url"].apply(list).reset_index()
    cluster_url_counts.columns = ["cluster_id", "urls"]

    # Filter to clusters with potential cannibalization
    cannib = cluster_url_counts[
        cluster_url_counts["urls"].apply(len) > CANNIBALIZATION_URL_THRESHOLD
    ].copy()

    if cannib.empty:
        logger.info("No cannibalization detected.")
        return pd.DataFrame(columns=["cluster_id", "cluster_name", "url_count", "urls", "recommendation"])

    # Merge cluster names
    cannib = cannib.merge(
        cluster_info[["cluster_id", "cluster_name"]],
        on="cluster_id",
        how="left",
    )

    cannib["url_count"] = cannib["urls"].apply(len)
    cannib["recommendation"] = cannib["url_count"].apply(_recommend_action)
    cannib["urls"] = cannib["urls"].apply(lambda x: " | ".join(x))

    return cannib[["cluster_id", "cluster_name", "url_count", "urls", "recommendation"]]


def _recommend_action(url_count: int) -> str:
    """Generate recommendation based on cannibalization severity."""
    if url_count <= 3:
        return "Review: differentiate content angles or consolidate into single authoritative page"
    if url_count <= 5:
        return "High priority: merge weaker pages into strongest performer, redirect others"
    return "Critical: significant topic overlap — consolidate aggressively, keep 1-2 pages max"


def export_all(
    cluster_info: pd.DataFrame,
    url_mapping: pd.DataFrame,
    cannibalization: pd.DataFrame,
    skipped_urls: list[str],
    recommendations: pd.DataFrame | None = None,
):
    """Export all output CSVs."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 1. clusters.csv
    cluster_path = os.path.join(OUTPUT_DIR, "clusters.csv")
    cluster_info.to_csv(cluster_path, index=False)
    logger.info("Exported clusters to %s", cluster_path)

    # 2. url_mapping.csv
    url_path = os.path.join(OUTPUT_DIR, "url_mapping.csv")
    url_mapping.to_csv(url_path, index=False)
    logger.info("Exported URL mapping to %s", url_path)

    # 3. cannibalization.csv
    cannib_path = os.path.join(OUTPUT_DIR, "cannibalization.csv")
    cannibalization.to_csv(cannib_path, index=False)
    logger.info("Exported cannibalization report to %s", cannib_path)

    # 4. recommendations.csv (if brand voice is available)
    if recommendations is not None and not recommendations.empty:
        rec_path = os.path.join(OUTPUT_DIR, "recommendations.csv")
        recommendations.to_csv(rec_path, index=False)
        logger.info("Exported content recommendations to %s", rec_path)

    # 5. skipped_urls.csv
    if skipped_urls:
        skipped_path = os.path.join(OUTPUT_DIR, "skipped_urls.csv")
        skipped_df = pd.DataFrame(skipped_urls, columns=["details"])
        parts = skipped_df["details"].str.split(" \\| ", n=1, expand=True)
        skipped_df["url"] = parts[0].str.strip()
        skipped_df["reason"] = parts[1].str.strip() if 1 in parts.columns else ""
        skipped_df.drop(columns=["details"], inplace=True)
        skipped_df.to_csv(skipped_path, index=False)
        logger.info("Exported skipped URLs to %s", skipped_path)

    logger.info("All outputs exported to %s/", OUTPUT_DIR)
