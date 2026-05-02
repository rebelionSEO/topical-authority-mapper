"""
Topical Authority Mapper - Main orchestrator.

Quick start:
    python -m src.main --sitemap https://example.com/sitemap.xml --site-name "Example Inc"

With a config file (recommended for repeatable runs):
    python -m src.main --config examples/site.yaml

With competitors (auto-discovers each competitor's sitemap and runs gap analysis):
    python -m src.main --sitemap https://example.com/sitemap.xml --site-name "Example" \\
      --competitor competitor1.com --competitor competitor2.com

CLI args always override values loaded from --config.
"""

import argparse
import logging
import os
import sys
import time
from typing import Optional

import pandas as pd

from src.brand_voice import generate_content_recommendation, load_or_create_brand_profile
from src.clustering import assign_url_clusters, cluster_embeddings, extract_cluster_keywords, reduce_dimensions
from src.config import (
    DEBUG_URL_LIMIT,
    SiteConfig,
    cache_dir,
    domain_from_url,
    output_dir,
    save_site_config,
    set_runtime_cache_dir,
)
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
    """Load URLs from a text file (one per line). Lines starting with # are comments."""
    with open(filepath, "r") as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    return urls


def _derive_domain(urls: list[str], explicit_domain: Optional[str]) -> str:
    """Pick the most common host from the URL list, unless explicitly given."""
    if explicit_domain:
        return explicit_domain.replace("https://", "").replace("http://", "").rstrip("/")
    if not urls:
        return "unknown"
    from collections import Counter
    hosts = [domain_from_url(u) for u in urls if u]
    counts = Counter(h for h in hosts if h)
    return counts.most_common(1)[0][0] if counts else "unknown"


def _load_yaml_config(path: str) -> dict:
    """Load a YAML config file. Returns flat dict ready to merge with CLI args."""
    try:
        import yaml
    except ImportError:
        print("ERROR: --config requires PyYAML. Install with: pip install pyyaml", file=sys.stderr)
        sys.exit(2)

    with open(path) as f:
        data = yaml.safe_load(f) or {}

    # YAML schema (all sections optional):
    #   site:       name, domain, industry
    #   input:      sitemap, urls_file, additional_sitemaps[]
    #   output:     output_dir, cache_dir, brand_voice
    #   competitors: [list]
    #   skip_patterns: [list]
    #   listing_patterns: [list]
    site = data.get("site", {}) or {}
    inp = data.get("input", {}) or {}
    out = data.get("output", {}) or {}

    return {
        "site_name": site.get("name"),
        "site_domain": site.get("domain"),
        "industry": site.get("industry"),
        "sitemap": inp.get("sitemap"),
        "input": inp.get("urls_file"),
        "additional_sitemaps": list(inp.get("additional_sitemaps", []) or []),
        "output_dir": out.get("output_dir"),
        "cache_dir": out.get("cache_dir"),
        "brand_voice": out.get("brand_voice"),
        "competitors": list(data.get("competitors", []) or []),
        "skip_patterns": list(data.get("skip_patterns", []) or []),
        "listing_patterns": list(data.get("listing_patterns", []) or []),
        "max_urls_per_competitor": int(data.get("max_urls_per_competitor", 100)),
    }


def run(
    input_file: Optional[str] = None,
    sitemap_url: Optional[str] = None,
    brand_voice_pdf: Optional[str] = None,
    site_name: Optional[str] = None,
    site_domain: Optional[str] = None,
    sitemaps: Optional[list[str]] = None,
    industry: Optional[str] = None,
    output_dir_arg: Optional[str] = None,
    skip_patterns: Optional[list[str]] = None,
    listing_patterns: Optional[list[str]] = None,
    competitors: Optional[list[str]] = None,
    max_urls_per_competitor: int = 100,
    runs_root: Optional[str] = None,
    skip_history: bool = False,
    debug: bool = False,
):
    """Main pipeline."""
    setup_logging(debug)
    logger = logging.getLogger("main")
    run_started_at = time.time()

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
        logger.error("Provide either --input or --sitemap (or use --config). Exiting.")
        sys.exit(1)

    if debug:
        urls = urls[:DEBUG_URL_LIMIT]
    logger.info("Loaded %d URLs", len(urls))

    if not urls:
        logger.error("No URLs to process. Exiting.")
        sys.exit(1)

    # --- 1b. Establish + persist site config (so other modules pick it up) ---
    domain = _derive_domain(urls, site_domain)
    name = site_name or domain
    sitemap_list = list(sitemaps) if sitemaps else ([sitemap_url] if sitemap_url else [])
    resolved_output_dir = os.path.abspath(output_dir_arg) if output_dir_arg else None

    site_config = SiteConfig(
        name=name,
        domain=domain,
        sitemaps=sitemap_list,
        output_dir=resolved_output_dir,
        industry=industry,
        skip_patterns=list(skip_patterns or []),
        listing_patterns=list(listing_patterns or []),
    )
    save_site_config(site_config)
    logger.info(
        "Site: name=%r domain=%r industry=%r sitemaps=%d output=%s",
        name, domain, industry, len(sitemap_list), resolved_output_dir or "(default)",
    )

    OUT = output_dir()
    os.makedirs(OUT, exist_ok=True)

    # --- 2. Ingest content ---
    logger.info("Step 1/6: Ingesting content...")
    chunks_df, skipped = ingest_urls(urls)

    if chunks_df.empty:
        logger.error("No content extracted from any URL. Exiting.")
        sys.exit(1)

    logger.info("Extracted %d chunks from %d pages", len(chunks_df), chunks_df["url"].nunique())

    # --- 3. Generate embeddings ---
    logger.info("Step 2/6: Generating embeddings...")
    cache_path = os.path.join(cache_dir(), "embeddings.pkl")
    embeddings = compute_embeddings(
        texts=chunks_df["chunk_text"].tolist(),
        cache_path=cache_path if not debug else None,
    )

    # --- 4. Cluster ---
    logger.info("Step 3/6: Clustering...")
    reduced = reduce_dimensions(embeddings)
    labels = cluster_embeddings(reduced)
    chunks_df["cluster_id"] = labels

    # Persist chunks_df + the embedding row index so the RAG retrieval layer can
    # look up actual chunk text for any URL or cluster. The chunks_df row order
    # matches the embeddings array row order — we save that ordering explicitly.
    try:
        chunks_df.reset_index(drop=True).to_pickle(os.path.join(cache_dir(), "chunks_df.pkl"))
        logger.info("Persisted chunks_df.pkl for RAG retrieval (%d chunks)", len(chunks_df))
    except Exception:
        logger.exception("Could not persist chunks_df (RAG features may degrade)")

    # --- 5. Extract keywords & name clusters ---
    logger.info("Step 4/6: Extracting cluster keywords...")
    cluster_info = extract_cluster_keywords(chunks_df)

    if cluster_info.empty:
        logger.warning("No clusters found. All points classified as noise.")
        cluster_info = pd.DataFrame(columns=["cluster_id", "cluster_name", "keywords"])

    # --- 5b. RAG-enhanced cluster naming — replaces TF-IDF top-phrase noise ---
    # ("make sure", "according cox", "octopus deploy") with clean human-readable names.
    try:
        from src import llm_advisor as _llm
        if _llm.is_enabled() and not cluster_info.empty:
            from src.retrieval import RetrievalIndex
            # Build a lightweight in-memory retrieval object directly from current chunks/embeddings
            # (we already have them in scope — no need to round-trip through cache).
            tmp_idx = RetrievalIndex(chunks_df=chunks_df, embeddings=embeddings, faiss_index=None)
            renamed = 0
            for i, row in cluster_info.iterrows():
                cid = int(row["cluster_id"])
                if cid < 0:
                    continue
                samples = tmp_idx.search_by_cluster(cid, k=4)
                if not samples:
                    continue
                kw_list = [k.strip() for k in str(row.get("keywords", "")).split(",")][:8]
                suggestion = _llm.suggest_cluster_name(
                    current_name=str(row["cluster_name"]),
                    keywords=kw_list,
                    sample_chunks=[s.text for s in samples],
                )
                if suggestion and suggestion.get("cluster_name"):
                    new_name = str(suggestion["cluster_name"]).strip()
                    if new_name and new_name.lower() != str(row["cluster_name"]).lower():
                        cluster_info.at[i, "cluster_name"] = new_name
                        renamed += 1
            if renamed:
                logger.info("LLM cluster naming: renamed %d/%d clusters from TF-IDF defaults", renamed, len(cluster_info))
    except Exception:
        logger.exception("LLM cluster naming failed (non-fatal — TF-IDF names retained)")

    # --- 6. URL-level mapping ---
    logger.info("Step 5/6: Mapping clusters to URLs...")
    url_mapping = assign_url_clusters(chunks_df)
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

    # If no brand profile loaded AND LLM is enabled, auto-generate one from sampled site content.
    if not brand_profile.get("tone") and not brand_voice_pdf:
        try:
            from src import llm_advisor as _llm
            if _llm.is_enabled() and not chunks_df.empty:
                logger.info("Auto-generating brand voice profile from sampled site content...")
                # Sample up to 8 representative chunks (one per URL, prefer longer ones)
                sample_chunks = (
                    chunks_df.sort_values("chunk_text", key=lambda s: s.str.len(), ascending=False)
                    .drop_duplicates(subset="url")
                    .head(8)["chunk_text"].tolist()
                )
                generated = _llm.generate_brand_profile(
                    site_name=name, site_domain=domain, industry=industry, samples=sample_chunks,
                )
                if generated and isinstance(generated, dict):
                    import json as _json
                    profile_path = os.path.join(cache_dir(), "brand_profile.json")
                    with open(profile_path, "w") as f:
                        _json.dump(generated, f, indent=2)
                    brand_profile = generated
                    logger.info("Brand profile generated and saved to %s", profile_path)
                else:
                    logger.warning("Brand profile generation returned no result")
        except Exception:
            logger.exception("Brand profile auto-generation failed (non-fatal)")

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
        recommendations = recommendations[["cluster_id", "cluster_name", "content_type", "tone", "angle", "cta_style"]]
    else:
        logger.info("Step 6/6: Skipping recommendations (no brand profile)")

    # --- 9. FAISS index ---
    if not debug:
        logger.info("Building FAISS index...")
        faiss_path = os.path.join(cache_dir(), "embeddings.faiss")
        build_faiss_index(embeddings, save_path=faiss_path)
    else:
        logger.info("Skipping FAISS index (debug mode)")

    # --- 9b. Content freshness (sitemap lastmod, fall back to HTML scrape) ---
    try:
        from src.enhancements import score_content_freshness
        # Use the URLs we just analyzed as the HTML-scrape fallback
        target_urls = chunks_df["url"].drop_duplicates().tolist() if not chunks_df.empty else []
        score_content_freshness(sitemap_urls=sitemap_list, fallback_urls=target_urls)
    except Exception:
        logger.exception("Freshness scoring failed (non-fatal)")

    # --- 9c. Search intent classification ---
    try:
        from src.enhancements import classify_search_intent
        classify_search_intent(chunks_df)
    except Exception:
        logger.exception("Intent classification failed (non-fatal)")

    # --- 10. Export base outputs ---
    logger.info("Exporting results...")
    export_all(cluster_info, url_mapping, cannibalization, skipped, recommendations)

    # --- 11. Competitor analysis (optional) ---
    content_ideas_df = pd.DataFrame()
    if competitors:
        from src.competitor import run_competitor_analyses

        logger.info("Step 7: Competitor analysis (%d competitors)...", len(competitors))
        succeeded = run_competitor_analyses(
            competitors, cluster_info, name, max_urls_per_competitor=max_urls_per_competitor
        )
        # Persist resolved competitor list back into site config so downstream modules know
        site_config.competitors = succeeded
        save_site_config(site_config)
        logger.info("Competitor analysis complete: %s", ", ".join(succeeded) if succeeded else "(none succeeded)")

        # --- 12. Generate content ideas from gap data ---
        if succeeded:
            from src.content_ideas import generate_content_ideas

            logger.info("Step 8: Generating content briefs from gap data...")
            content_ideas_df = generate_content_ideas(site_config=site_config)
            logger.info("Content ideas: %d briefs generated", len(content_ideas_df))

    # --- 13. QA pass (must run before any render) ---
    from src.qa import run_qa, print_summary

    logger.info("Step 9: Running QA validation...")
    qa_report = run_qa(run_started_at=run_started_at)
    print_summary(qa_report)
    if qa_report.critical_count() > 0:
        logger.error(
            "QA found %d CRITICAL issues. Review output/qa_report.json before rendering the dashboard or PDF.",
            qa_report.critical_count(),
        )

    # --- 13b. Compute site health + 1-page exec summary + Claude artifact ---
    try:
        from src.site_health import compute_health, write_health
        from src.exec_summary import generate_exec_summary
        from src.dashboard_artifact import generate_artifact

        logger.info("Step 9b: Computing site health + exec summary + Claude artifact...")
        health_snap = compute_health(site_config=site_config)
        write_health(health_snap)
        exec_path = generate_exec_summary(site_config=site_config, health=health_snap)
        artifact_path = generate_artifact(site_config=site_config)
        logger.info(
            "Site Health: %d/100 (%s) -> exec %s, artifact %s",
            health_snap.composite, health_snap.composite_label, exec_path, artifact_path,
        )
    except Exception:
        logger.exception("Site health / exec summary / artifact generation failed (non-fatal)")

    # --- 13b-2. Vector map (2D embedding projection per URL) ---
    try:
        from src.vector_map import build_vector_map
        logger.info("Building vector map (2D embedding projection)...")
        build_vector_map(chunks_df=chunks_df, embeddings=embeddings, cluster_info=cluster_info)
    except Exception:
        logger.exception("Vector map build failed (non-fatal)")

    # --- 13c. Render the interactive dashboard + PDF report ---
    # These read from the output dir, so they need to run after exports + health are done.
    try:
        from src.dashboard import generate_dashboard

        logger.info("Step 9c: Rendering interactive dashboard...")
        dash_path = generate_dashboard(site_config=site_config)
        logger.info("Dashboard rendered: %s", dash_path)
    except Exception:
        logger.exception("Dashboard render failed (non-fatal)")

    try:
        from src.report import generate_pdf

        logger.info("Step 9d: Rendering PDF report...")
        pdf_path = generate_pdf(site_config=site_config)
        logger.info("PDF report: %s", pdf_path)
    except Exception:
        logger.exception("PDF report render failed (non-fatal — wkhtmltopdf or Chrome may be missing)")

    # --- 14. Snapshot this run for historical context ---
    snapshot_path = None
    if not skip_history:
        from src.run_history import snapshot_run, diff_against_previous

        try:
            metadata = snapshot_run(site_config, runs_root=runs_root or os.path.abspath("./runs"))
            snapshot_path = metadata.snapshot_dir
            logger.info("Run snapshot saved: %s", snapshot_path)
            delta = diff_against_previous(site_config.name, runs_root=runs_root or os.path.abspath("./runs"))
            if delta:
                logger.info(
                    "Delta vs previous run (%s -> %s): %s",
                    delta["from_run"], delta["to_run"], delta["delta"],
                )
        except Exception:
            logger.exception("Failed to create run snapshot (run still completed)")

    # --- Summary ---
    print("\n" + "=" * 60)
    print("TOPICAL AUTHORITY MAPPER - COMPLETE")
    print("=" * 60)
    print(f"  Site:            {name} ({domain})")
    if industry:
        print(f"  Industry:        {industry}")
    print(f"  URLs processed:  {chunks_df['url'].nunique()}")
    print(f"  URLs skipped:    {len(skipped)}")
    print(f"  Total chunks:    {len(chunks_df)}")
    print(f"  Clusters found:  {len(cluster_info)}")
    print(f"  Cannibalization: {len(cannibalization)} clusters flagged")
    if competitors:
        print(f"  Competitors:     {', '.join(site_config.competitors) or '(none)'}")
    if not content_ideas_df.empty:
        print(f"  Content ideas:   {len(content_ideas_df)} briefs (output/content_ideas.csv)")
    print(f"  QA:              {qa_report.critical_count()} critical, {qa_report.warn_count()} warn")
    try:
        print(f"  Health:          {health_snap.composite}/100 ({health_snap.composite_label})")
    except (NameError, AttributeError):
        pass
    if snapshot_path:
        print(f"  Snapshot:        {snapshot_path}")
    print(f"  Output dir:      {OUT}/")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Topical Authority Mapper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--config", help="Path to a YAML config file. CLI args override its values.")

    src_group = parser.add_mutually_exclusive_group(required=False)
    src_group.add_argument("--input", "-i", help="Path to a file with URLs (one per line)")
    src_group.add_argument("--sitemap", "-s", help="URL to an XML sitemap (parses all URLs from it)")

    parser.add_argument("--site-name", help="Human-readable site name. Defaults to the domain.")
    parser.add_argument("--site-domain", help="Bare hostname (e.g. 'acme.com'). Auto-derived if omitted.")
    parser.add_argument("--industry", help="Optional vertical hint (e.g. 'b2b-saas', 'ecommerce').")
    parser.add_argument(
        "--sitemap-url", action="append", default=[],
        help="Additional sitemap URL for freshness scoring (repeatable).",
    )
    parser.add_argument(
        "--competitor", action="append", default=[],
        help="Competitor domain or sitemap URL (repeatable). Each is auto-crawled and gap-analyzed.",
    )
    parser.add_argument(
        "--max-urls-per-competitor", type=int, default=100,
        help="Cap on URLs ingested per competitor (default 100).",
    )
    parser.add_argument(
        "--skip-pattern", action="append", default=[],
        help="Extra URL substring to skip (repeatable). Merged with built-in skip list.",
    )
    parser.add_argument(
        "--listing-pattern", action="append", default=[],
        help="Regex for URLs that are intentionally thin (hubs/archives). Repeatable.",
    )
    parser.add_argument("--output-dir", help="Override the output directory for CSVs/HTML/PDF.")
    parser.add_argument("--cache-dir", help="Override the cache directory for embeddings + site config.")
    parser.add_argument("--runs-root", help="Where to write timestamped run snapshots (default: ./runs).")
    parser.add_argument("--no-snapshot", action="store_true", help="Skip writing a run snapshot.")
    parser.add_argument("--brand-voice", "-b", help="Path to brand voice PDF (optional).")
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Enable LLM-powered analysis (cannibalization, thin-content judgment, audience inference, "
             "auto-generated brand voice profile). Requires ANTHROPIC_API_KEY env var. ~$0.05-0.15 per audit.",
    )
    parser.add_argument("--debug", "-d", action="store_true", help="Debug mode: 10 URLs, skip FAISS, verbose.")
    args = parser.parse_args()

    # Load YAML config first, then let CLI args override.
    cfg: dict = {}
    if args.config:
        cfg = _load_yaml_config(args.config)

    def pick(cli_val, key, default=None):
        """CLI value if non-falsy, else YAML, else default."""
        if cli_val:
            return cli_val
        return cfg.get(key) if cfg.get(key) is not None else default

    cache_path = pick(args.cache_dir, "cache_dir")
    if cache_path:
        set_runtime_cache_dir(cache_path)

    # Activate LLM advisor if requested
    if args.use_llm or os.environ.get("TAM_LLM_PROVIDER", "").lower() in ("anthropic", "claude"):
        from src.llm_advisor import enable_for_session, is_enabled
        ok = enable_for_session()
        if ok and is_enabled():
            print("✓ LLM advisor enabled (anthropic + claude-haiku-4-5)")
        else:
            print("⚠ LLM advisor requested but ANTHROPIC_API_KEY missing — falling back to rule-based")

    sitemap = pick(args.sitemap, "sitemap")
    input_file = pick(args.input, "input")
    if not sitemap and not input_file:
        parser.error("Must provide --sitemap or --input (via CLI or --config).")

    sitemaps = list(args.sitemap_url) + list(cfg.get("additional_sitemaps", []))
    if sitemap and sitemap not in sitemaps:
        sitemaps.append(sitemap)

    competitors = list(args.competitor) + list(cfg.get("competitors", []))
    skip_patterns = list(args.skip_pattern) + list(cfg.get("skip_patterns", []))
    listing_patterns = list(args.listing_pattern) + list(cfg.get("listing_patterns", []))

    run(
        input_file=input_file,
        sitemap_url=sitemap,
        brand_voice_pdf=pick(args.brand_voice, "brand_voice"),
        site_name=pick(args.site_name, "site_name"),
        site_domain=pick(args.site_domain, "site_domain"),
        sitemaps=sitemaps,
        industry=pick(args.industry, "industry"),
        output_dir_arg=pick(args.output_dir, "output_dir"),
        skip_patterns=skip_patterns,
        listing_patterns=listing_patterns,
        competitors=competitors,
        max_urls_per_competitor=int(args.max_urls_per_competitor or cfg.get("max_urls_per_competitor", 100)),
        runs_root=pick(args.runs_root, "runs_root"),
        skip_history=args.no_snapshot,
        debug=args.debug,
    )


if __name__ == "__main__":
    main()
