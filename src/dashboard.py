"""Generate an interactive HTML dashboard from analysis outputs."""

import logging
import os

import pandas as pd

from src.config import SiteConfig, load_site_config, output_dir

logger = logging.getLogger(__name__)


# Generic, content-based hints used to label thin pages. Heuristic only —
# the page-type classifier in src.enhancements is the source of truth.
_TOOL_HINTS = ("/tools/", "/tool/", "tool-review", "/marketing-tools/", "/ai-tools/")
_LOCAL_HINTS = ("/locations/", "/cities/", "-near-me", "/areas/")
_LOCAL_PATH_HINTS = ("services-for-", "services-in-", "marketing-for-", "design-for-", "agency-in-")


def _classify_thin(url: str) -> str:
    """Classify a thin URL into a coarse category for grouping in the dashboard."""
    u = url.lower()
    if any(h in u for h in _TOOL_HINTS):
        return "tool"
    if any(h in u for h in _LOCAL_HINTS) or any(h in u for h in _LOCAL_PATH_HINTS):
        return "local"
    return "other"


def _thin_recommendation(url: str, category: str) -> str:
    """Generate a short recommendation for a thin content page."""
    if category == "tool":
        return "Expand to 500+ words: add use cases, pricing, pros/cons, and comparison to alternatives"
    if category == "local":
        return "Expand with local case studies, testimonials, service area details, and unique location-specific content"
    if "case-stud" in url:
        return "Add full case study: challenge, strategy, execution, results with metrics"
    if "industr" in url:
        return "Build out as industry pillar page: pain points, services, case studies, FAQs"
    if "guide" in url:
        return "Expand into a comprehensive resource hub with linked subtopics"
    return "Expand with substantive content or consolidate into a related pillar page"


def _discover_competitor_csvs() -> list[tuple[str, pd.DataFrame]]:
    """Return list of (display_name, dataframe) for every competitor_gap_*.csv in OUTPUT_DIR."""
    results = []
    out = output_dir()
    if not os.path.isdir(out):
        return results
    for fname in sorted(os.listdir(out)):
        if fname.startswith("competitor_gap_") and fname.endswith(".csv"):
            stem = fname[len("competitor_gap_"):-len(".csv")]
            display_name = stem.replace("_", " ").title()
            df = pd.read_csv(os.path.join(out, fname))
            if not df.empty:
                results.append((display_name, df))
    return results


def generate_dashboard(site_config: SiteConfig | None = None):
    """Build a self-contained interactive HTML dashboard."""
    if site_config is None:
        site_config = load_site_config() or SiteConfig(name="Site", domain="")

    out = output_dir()
    clusters = pd.read_csv(os.path.join(out, "clusters.csv"))
    url_map = pd.read_csv(os.path.join(out, "url_mapping.csv"))
    cannib = pd.read_csv(os.path.join(out, "cannibalization.csv"))
    skipped = pd.read_csv(os.path.join(out, "skipped_urls.csv"))

    recs_path = os.path.join(out, "recommendations.csv")
    recs = pd.read_csv(recs_path) if os.path.exists(recs_path) else pd.DataFrame()

    def _load(name):
        p = os.path.join(out, name)
        return pd.read_csv(p) if os.path.exists(p) else pd.DataFrame()

    similarity_df = _load("similarity_scores.csv")
    if not similarity_df.empty:
        similarity_df = similarity_df[similarity_df["similarity"] >= 0.80].head(50)
    intent_df = _load("search_intent.csv")
    freshness_df = _load("content_freshness.csv")
    brand_df = _load("brand_voice_scores.csv")
    merge_df = _load("cluster_merge_suggestions.csv")
    if not merge_df.empty:
        merge_df = merge_df.head(30)

    # Discover competitors dynamically by reading any competitor_gap_*.csv files.
    competitor_dfs = _discover_competitor_csvs()
    competitor_names = [name for name, _ in competitor_dfs]

    # Content ideas (generated from competitor gaps)
    ideas_path = os.path.join(out, "content_ideas.csv")
    content_ideas_df = pd.read_csv(ideas_path) if os.path.exists(ideas_path) else pd.DataFrame()

    # Build a unified topic comparison table: rows = unique topics, cols = target + each competitor.
    competitor_table = []
    if competitor_dfs:
        # Collect topic → status map per competitor.
        topic_state: dict[str, dict] = {}
        for comp_name, df in competitor_dfs:
            for _, row in df.iterrows():
                topic = str(row.get("keyword", "")).strip()
                status = str(row.get("status", "")).lower()
                if not topic:
                    continue
                state = topic_state.setdefault(
                    topic,
                    {"topic": topic, "target": False, "competitors": {c: False for c in competitor_names}},
                )
                target_present = "advantage" in status or "shared" in status or "both cover" in status
                comp_present = "gap" in status or "shared" in status or "both cover" in status
                if target_present:
                    state["target"] = True
                if comp_present:
                    state["competitors"][comp_name] = True
        for state in topic_state.values():
            covered_by_comp = any(state["competitors"].values())
            if state["target"] and not covered_by_comp:
                final_status = "ADVANTAGE"
            elif covered_by_comp and not state["target"]:
                final_status = "GAP"
            else:
                final_status = "SHARED"
            state["status"] = final_status
            competitor_table.append(state)

    # Cluster sizes
    cluster_sizes = url_map[url_map["main_cluster"] != -1].groupby("main_cluster").size().reset_index(name="url_count")
    cluster_sizes = cluster_sizes.merge(clusters, left_on="main_cluster", right_on="cluster_id", how="inner")
    cluster_sizes = cluster_sizes.sort_values("url_count", ascending=False)

    top_clusters = cluster_sizes.head(30)
    noise_count = len(url_map[url_map["main_cluster"] == -1])

    cannib_full = cannib[cannib["cluster_id"] != -1].sort_values("url_count", ascending=False)

    content_types = {}
    if not recs.empty and "content_type" in recs.columns:
        content_types = recs["content_type"].value_counts().to_dict()

    from src.enhancements import is_intentionally_thin, classify_page_type
    thin = skipped[skipped["reason"].str.contains("thin", na=False)].copy()
    thin["is_listing"] = thin["url"].apply(is_intentionally_thin)
    thin["page_type"] = thin["url"].apply(classify_page_type)
    thin_actionable = thin[~thin["is_listing"]].copy()
    thin_listings = thin[thin["is_listing"]].copy()

    thin_actionable["category"] = thin_actionable["url"].apply(_classify_thin)
    thin_actionable["recommendation"] = thin_actionable.apply(
        lambda r: _thin_recommendation(r["url"], r["category"]), axis=1
    )
    thin_actionable["word_count"] = thin_actionable["reason"].str.extract(r"(\d+)").astype(float).fillna(0).astype(int)

    thin_tools = thin_actionable[thin_actionable["category"] == "tool"].to_dict("records")
    thin_local = thin_actionable[thin_actionable["category"] == "local"].to_dict("records")
    thin_other = thin_actionable[thin_actionable["category"] == "other"].to_dict("records")

    # URL detail data
    url_details = url_map.merge(
        clusters.rename(columns={"cluster_id": "main_cluster", "cluster_name": "cluster_name_lookup"}),
        on="main_cluster", how="left"
    )

    treemap_data = {
        "labels": top_clusters["cluster_name"].tolist(),
        "values": top_clusters["url_count"].astype(int).tolist(),
        "ids": top_clusters["cluster_id"].astype(int).tolist(),
        "keywords": top_clusters["keywords"].tolist(),
    }

    cannib_chart = cannib_full.head(25)
    cannib_chart_data = {
        "labels": cannib_chart["cluster_name"].tolist(),
        "values": cannib_chart["url_count"].astype(int).tolist(),
    }

    # Cannibalization detail with page types and actions
    cannib_detail = []
    for _, row in cannib_full.iterrows():
        urls = str(row["urls"]).split(" | ")
        url_details_list = []
        for u in urls:
            ptype = classify_page_type(u)
            if ptype == "service":
                action = "PROTECT — this is the conversion page"
                role = "money"
            elif ptype == "case-study":
                action = "KEEP — supports trust and conversion"
                role = "support"
            elif ptype == "industry":
                action = "KEEP — unique vertical angle"
                role = "support"
            elif ptype == "local-landing":
                action = "KEEP if geo-targeted, otherwise merge"
                role = "support"
            else:
                action = "EVALUATE — merge into pillar or differentiate angle"
                role = "content"
            url_details_list.append({
                "url": u,
                "slug": site_config.strip_url(u),
                "type": ptype,
                "action": action,
                "role": role,
            })
        role_order = {"money": 0, "support": 1, "content": 2}
        url_details_list.sort(key=lambda x: role_order.get(x["role"], 2))

        types_present = set(d["type"] for d in url_details_list)
        has_conversion_risk = "service" in types_present and "blog" in types_present

        if has_conversion_risk:
            analysis = (
                f"CONVERSION RISK: {sum(1 for d in url_details_list if d['type']=='blog')} blog posts competing "
                "against the service page for the same topic. Blog content may outrank the service page, "
                "pushing users away from conversion."
            )
        elif len(urls) > 10:
            analysis = (
                f"SEVERE TOPIC FRAGMENTATION: {len(urls)} pages covering the same topic dilutes authority. "
                "Consolidate into 1 pillar + 2-3 angle-specific posts."
            )
        else:
            analysis = (
                f"{len(urls)} pages overlap on this topic. Identify the strongest performer and merge weaker "
                "pages via 301 redirects."
            )

        kw_row = clusters[clusters["cluster_id"] == row["cluster_id"]]
        keywords = kw_row.iloc[0]["keywords"] if len(kw_row) > 0 else ""

        cannib_detail.append({
            "id": int(row["cluster_id"]),
            "name": row["cluster_name"],
            "count": int(row["url_count"]),
            "urls": url_details_list,
            "keywords": keywords.split(", ")[:5],
            "analysis": analysis,
            "has_conversion_risk": has_conversion_risk,
            "severity": "critical" if row["url_count"] >= 10 or has_conversion_risk else "high" if row["url_count"] >= 6 else "moderate",
        })

    all_clusters_data = []
    for _, row in cluster_sizes.iterrows():
        rec_row = recs[recs["cluster_id"] == row["cluster_id"]] if not recs.empty else pd.DataFrame()
        all_clusters_data.append({
            "id": int(row["cluster_id"]),
            "name": row["cluster_name"],
            "urls": int(row["url_count"]),
            "keywords": row["keywords"],
            "content_type": rec_row.iloc[0]["content_type"] if len(rec_row) > 0 else "",
            "tone": rec_row.iloc[0]["tone"] if len(rec_row) > 0 else "",
            "angle": rec_row.iloc[0]["angle"] if len(rec_row) > 0 else "",
            "cta": rec_row.iloc[0]["cta_style"] if len(rec_row) > 0 else "",
            "cannibalized": int(row["cluster_id"]) in cannib["cluster_id"].values,
        })

    url_table = []
    for _, row in url_details.iterrows():
        url_table.append({
            "url": row["url"],
            "cluster": int(row["main_cluster"]) if pd.notna(row["main_cluster"]) else -1,
            "name": row.get("cluster_name_lookup", row.get("cluster_name", "Unclustered")),
            "secondary": row.get("secondary_clusters", ""),
        })

    stats = {
        "total_urls": len(url_map),
        "total_clusters": len(clusters),
        "cannib_flags": len(cannib_full),
        "skipped": len(thin_actionable),
        "skipped_listings": len(thin_listings),
        "noise": noise_count,
        "thin_local": len(thin_local),
        "thin_tools": len(thin_tools),
        "thin_other": len(thin_other),
    }

    top_cannib_summary = cannib_full.head(5)[["cluster_name", "url_count"]].to_dict("records")

    enh = {}
    if competitor_table:
        gaps = sum(1 for r in competitor_table if r["status"] == "GAP")
        advantages = sum(1 for r in competitor_table if r["status"] == "ADVANTAGE")
        shared = sum(1 for r in competitor_table if r["status"] == "SHARED")
        enh["competitor"] = {
            "rows": competitor_table,
            "names": competitor_names,
        }
        enh["comp_stats"] = {"gaps": gaps, "advantages": advantages, "shared": shared}
    if not similarity_df.empty:
        sim_records = similarity_df.to_dict("records")
        for r in sim_records:
            r["url_a"] = site_config.strip_url(r["url_a"])
            r["url_b"] = site_config.strip_url(r["url_b"])
        enh["similarity"] = sim_records
    if not intent_df.empty:
        enh["intent"] = intent_df["primary_intent"].value_counts().to_dict()
    if not freshness_df.empty:
        enh["freshness"] = freshness_df["freshness"].value_counts().to_dict()
    if not brand_df.empty:
        bottom_records = brand_df.head(20).to_dict("records")
        for r in bottom_records:
            r["url"] = site_config.strip_url(r["url"])
        enh["brand"] = {
            "distribution": brand_df["rating"].value_counts().to_dict(),
            "avg_score": round(brand_df["brand_score"].mean(), 1),
            "bottom": bottom_records,
        }
    if not merge_df.empty:
        enh["merges"] = merge_df.to_dict("records")
    if not content_ideas_df.empty:
        ideas_records = content_ideas_df.to_dict("records")
        # Split pipe-delimited fields back into arrays for nicer rendering
        for r in ideas_records:
            r["suggested_keywords"] = [k.strip() for k in str(r.get("suggested_keywords", "")).split("|") if k.strip()]
            r["key_questions"] = [q.strip() for q in str(r.get("key_questions", "")).split("|") if q.strip()]
        enh["content_ideas"] = ideas_records
        enh["content_ideas_stats"] = {
            "total": len(content_ideas_df),
            "p1": int((content_ideas_df["priority"] == "P1").sum()),
            "p2": int((content_ideas_df["priority"] == "P2").sum()),
            "p3": int((content_ideas_df["priority"] == "P3").sum()),
        }

    # Load (or compute) health snapshot for the hero
    health_data: dict = {}
    health_path = os.path.join(out, "site_health.json")
    if os.path.exists(health_path):
        try:
            import json as _json
            with open(health_path) as _f:
                health_data = _json.load(_f)
        except Exception:
            health_data = {}
    if not health_data:
        try:
            from src.site_health import compute_health
            snap = compute_health(site_config=site_config)
            health_data = snap.to_dict()
        except Exception:
            logger.exception("Could not compute site health for dashboard")

    from src.dashboard_html import build_html
    html = build_html(
        site_config=site_config,
        treemap_data=treemap_data,
        cannib_chart_data=cannib_chart_data,
        cannib_detail=cannib_detail,
        content_types=content_types,
        all_clusters=all_clusters_data,
        url_table=url_table,
        stats=stats,
        thin_tools=thin_tools,
        thin_local=thin_local,
        thin_other=thin_other,
        top_cannib_summary=top_cannib_summary,
        enhancements=enh,
        health=health_data,
    )

    out_path = os.path.join(out, "dashboard.html")
    with open(out_path, "w") as f:
        f.write(html)
    logger.info("Dashboard saved to %s", out_path)
    return out_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    path = generate_dashboard()
    print(f"Dashboard: {path}")
