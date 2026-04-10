"""
Topical Authority Mapper - Main orchestrator.

Usage:
    python -m src.main --input urls.txt [--brand-voice brand.pdf] [--debug]
"""

import argparse
import logging
import os
import sys

import pandas as pd

from src.brand_voice import generate_content_recommendation, load_or_create_brand_profile
from src.clustering import assign_url_clusters, cluster_embeddings, extract_cluster_keywords, reduce_dimensions
from src.config import CACHE_DIR, DEBUG_URL_LIMIT, OUTPUT_DIR
from src.embedding import build_faiss_index, compute_embeddings
from src.ingestion import ingest_urls, parse_sitemap
from src.output import detect_cannibalization, export_all


def setup_logging(debug: bool = False):
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def load_urls(filepath: str) -> list[str]:
    """Load URLs from a text file (one per line)."""
    with open(filepath, "r") as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    return urls


def run(
    input_file: str | None = None,
    sitemap_url: str | None = None,
    brand_voice_pdf: str | None = None,
    debug: bool = False,
):
    """Main pipeline."""
    setup_logging(debug)
    logger = logging.getLogger("main")

    if debug:
        logger.info("=== DEBUG MODE: processing max %d URLs, skipping FAISS ===", DEBUG_URL_LIMIT)

    # --- 1. Load URLs ---
    if sitemap_url:
        logger.info("Parsing sitemap: %s", sitemap_url)
        urls = parse_sitemap(sitemap_url)
    elif input_file:
        logger.info("Loading URLs from %s", input_file)
        urls = load_urls(input_file)
    else:
        logger.error("Provide either --input or --sitemap. Exiting.")
        sys.exit(1)

    if debug:
        urls = urls[:DEBUG_URL_LIMIT]
    logger.info("Loaded %d URLs", len(urls))

    if not urls:
        logger.error("No URLs to process. Exiting.")
        sys.exit(1)

    # --- 2. Ingest content ---
    logger.info("Step 1/6: Ingesting content...")
    chunks_df, skipped = ingest_urls(urls)

    if chunks_df.empty:
        logger.error("No content extracted from any URL. Exiting.")
        sys.exit(1)

    logger.info("Extracted %d chunks from %d pages", len(chunks_df), chunks_df["url"].nunique())

    # --- 3. Generate embeddings ---
    logger.info("Step 2/6: Generating embeddings...")
    cache_path = os.path.join(CACHE_DIR, "embeddings.pkl")
    embeddings = compute_embeddings(
        texts=chunks_df["chunk_text"].tolist(),
        cache_path=cache_path if not debug else None,
    )

    # --- 4. Cluster ---
    logger.info("Step 3/6: Clustering...")
    reduced = reduce_dimensions(embeddings)
    labels = cluster_embeddings(reduced)
    chunks_df["cluster_id"] = labels

    # --- 5. Extract keywords & name clusters ---
    logger.info("Step 4/6: Extracting cluster keywords...")
    cluster_info = extract_cluster_keywords(chunks_df)

    if cluster_info.empty:
        logger.warning("No clusters found. All points classified as noise.")
        cluster_info = pd.DataFrame(columns=["cluster_id", "cluster_name", "keywords"])

    # --- 6. URL-level mapping ---
    logger.info("Step 5/6: Mapping clusters to URLs...")
    url_mapping = assign_url_clusters(chunks_df)

    # Merge cluster names into url_mapping for readability
    url_mapping = url_mapping.merge(
        cluster_info[["cluster_id", "cluster_name"]].rename(columns={"cluster_id": "main_cluster"}),
        on="main_cluster",
        how="left",
    )

    # --- 7. Cannibalization detection ---
    cannibalization = detect_cannibalization(url_mapping, cluster_info)

    # --- 8. Brand voice recommendations ---
    recommendations = None
    brand_profile = load_or_create_brand_profile(pdf_path=brand_voice_pdf)

    if brand_profile.get("tone") or brand_voice_pdf:
        logger.info("Step 6/6: Generating content recommendations...")
        recs = []
        for _, row in cluster_info.iterrows():
            kw_list = [k.strip() for k in row["keywords"].split(",")]
            rec = generate_content_recommendation(row["cluster_name"], kw_list, brand_profile)
            rec["cluster_id"] = row["cluster_id"]
            rec["cluster_name"] = row["cluster_name"]
            recs.append(rec)
        recommendations = pd.DataFrame(recs)
        # Reorder columns
        recommendations = recommendations[["cluster_id", "cluster_name", "content_type", "tone", "angle", "cta_style"]]
    else:
        logger.info("Step 6/6: Skipping recommendations (no brand profile)")

    # --- 9. FAISS index ---
    if not debug:
        logger.info("Building FAISS index...")
        faiss_path = os.path.join(CACHE_DIR, "embeddings.faiss")
        build_faiss_index(embeddings, save_path=faiss_path)
    else:
        logger.info("Skipping FAISS index (debug mode)")

    # --- 10. Export ---
    logger.info("Exporting results...")
    export_all(cluster_info, url_mapping, cannibalization, skipped, recommendations)

    # --- Summary ---
    print("\n" + "=" * 60)
    print("TOPICAL AUTHORITY MAPPER - COMPLETE")
    print("=" * 60)
    print(f"  URLs processed:  {chunks_df['url'].nunique()}")
    print(f"  URLs skipped:    {len(skipped)}")
    print(f"  Total chunks:    {len(chunks_df)}")
    print(f"  Clusters found:  {len(cluster_info)}")
    print(f"  Cannibalization: {len(cannibalization)} clusters flagged")
    print(f"  Output dir:      {OUTPUT_DIR}/")
    print("=" * 60)

    if not cluster_info.empty:
        print("\nCluster Summary:")
        for _, row in cluster_info.iterrows():
            print(f"  [{row['cluster_id']}] {row['cluster_name']}")
            print(f"      Keywords: {row['keywords']}")

    if not cannibalization.empty:
        print("\nCannibalization Alerts:")
        for _, row in cannibalization.iterrows():
            print(f"  Cluster {row['cluster_id']} ({row['cluster_name']}): {row['url_count']} URLs")
            print(f"    -> {row['recommendation']}")


def main():
    parser = argparse.ArgumentParser(description="Topical Authority Mapper")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input", "-i", help="Path to file with URLs (one per line)")
    group.add_argument("--sitemap", "-s", help="URL to XML sitemap (parses all URLs from it)")
    parser.add_argument("--brand-voice", "-b", help="Path to brand voice PDF (optional)")
    parser.add_argument("--debug", "-d", action="store_true", help="Debug mode: 10 URLs, skip FAISS, verbose")
    args = parser.parse_args()

    run(input_file=args.input, sitemap_url=args.sitemap, brand_voice_pdf=args.brand_voice, debug=args.debug)


if __name__ == "__main__":
    main()
