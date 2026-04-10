"""Generate an interactive HTML dashboard from analysis outputs."""

import json
import logging
import os
import re

import pandas as pd

from src.config import OUTPUT_DIR

logger = logging.getLogger(__name__)


def _classify_thin(url):
    """Classify thin content URL into category."""
    u = url.lower()
    if any(p in u for p in ["content-marketing-tools/", "marketing-tools/", "ai-tool"]):
        return "tool"
    if any(p in u for p in ["seo-services", "digital-marketing", "web-design", "los-angeles",
                             "orange-county", "california", "beach", "irvine", "corona",
                             "fullerton", "cerritos", "ontario", "riverside", "brea",
                             "costa-mesa", "huntington", "aliso-viejo", "anaheim"]):
        return "local"
    return "other"


def _thin_recommendation(url, category):
    """Generate a short recommendation for a thin content page."""
    slug = url.replace("https://azariangrowthagency.com/", "").strip("/")
    if category == "tool":
        tool = slug.split("/")[-1].replace("-", " ").title() if "/" in slug else slug
        return f"Expand to 500+ words: add use cases, pricing, pros/cons, and comparison to alternatives"
    if category == "local":
        city = slug.split("-")[-1].replace("/", "").title() if slug else "city"
        return f"Expand with local case studies, testimonials, service area details, and unique city-specific content"
    if "case-stud" in url:
        return "Add full case study: challenge, strategy, execution, results with metrics"
    if "industr" in url:
        return "Build out as industry pillar page: pain points, services, case studies, FAQs"
    if "guide" in url:
        return "Expand into a comprehensive resource hub with linked subtopics"
    return "Expand with substantive content or consolidate into a related pillar page"


def generate_dashboard():
    """Build a self-contained interactive HTML dashboard."""
    clusters = pd.read_csv(os.path.join(OUTPUT_DIR, "clusters.csv"))
    url_map = pd.read_csv(os.path.join(OUTPUT_DIR, "url_mapping.csv"))
    cannib = pd.read_csv(os.path.join(OUTPUT_DIR, "cannibalization.csv"))
    skipped = pd.read_csv(os.path.join(OUTPUT_DIR, "skipped_urls.csv"))

    recs_path = os.path.join(OUTPUT_DIR, "recommendations.csv")
    recs = pd.read_csv(recs_path) if os.path.exists(recs_path) else pd.DataFrame()

    # Load enhancement CSVs
    def _load(name):
        p = os.path.join(OUTPUT_DIR, name)
        return pd.read_csv(p) if os.path.exists(p) else pd.DataFrame()

    competitor_df = _load("competitor_topic_comparison.csv")
    similarity_df = _load("similarity_scores.csv")
    if not similarity_df.empty:
        similarity_df = similarity_df[similarity_df["similarity"] >= 0.80].head(50)
    intent_df = _load("search_intent.csv")
    freshness_df = _load("content_freshness.csv")
    brand_df = _load("brand_voice_scores.csv")
    merge_df = _load("cluster_merge_suggestions.csv")
    if not merge_df.empty:
        merge_df = merge_df.head(30)

    # Compute cluster sizes
    cluster_sizes = url_map[url_map["main_cluster"] != -1].groupby("main_cluster").size().reset_index(name="url_count")
    cluster_sizes = cluster_sizes.merge(clusters, left_on="main_cluster", right_on="cluster_id", how="inner")
    cluster_sizes = cluster_sizes.sort_values("url_count", ascending=False)

    top_clusters = cluster_sizes.head(30)
    noise_count = len(url_map[url_map["main_cluster"] == -1])

    # Cannibalization - full data with URLs
    cannib_full = cannib[cannib["cluster_id"] != -1].sort_values("url_count", ascending=False)

    # Content type distribution
    content_types = {}
    if not recs.empty and "content_type" in recs.columns:
        content_types = recs["content_type"].value_counts().to_dict()

    # Thin content with categories and recommendations
    # Filter out intentionally thin pages (listing/archive pages)
    from src.enhancements import is_intentionally_thin, classify_page_type
    thin = skipped[skipped["reason"].str.contains("thin", na=False)].copy()
    thin["is_listing"] = thin["url"].apply(is_intentionally_thin)
    thin["page_type"] = thin["url"].apply(classify_page_type)
    # Keep only pages that SHOULD have content (exclude listing/hub/archive pages)
    thin_actionable = thin[~thin["is_listing"]].copy()
    thin_listings = thin[thin["is_listing"]].copy()

    thin_actionable["category"] = thin_actionable["url"].apply(_classify_thin)
    thin_actionable["recommendation"] = thin_actionable.apply(lambda r: _thin_recommendation(r["url"], r["category"]), axis=1)
    thin_actionable["word_count"] = thin_actionable["reason"].str.extract(r"(\d+)").astype(float).fillna(0).astype(int)

    thin_tools = thin_actionable[thin_actionable["category"] == "tool"].to_dict("records")
    thin_local = thin_actionable[thin_actionable["category"] == "local"].to_dict("records")
    thin_other = thin_actionable[thin_actionable["category"] == "other"].to_dict("records")

    # Build URL detail data
    url_details = url_map.merge(
        clusters.rename(columns={"cluster_id": "main_cluster", "cluster_name": "cluster_name_lookup"}),
        on="main_cluster", how="left"
    )

    # JSON data
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

    # Full cannibalization detail with page types and actions
    cannib_detail = []
    for _, row in cannib_full.iterrows():
        urls = str(row["urls"]).split(" | ")
        # Classify each URL and assign an action
        url_details_list = []
        has_money_page = False
        for u in urls:
            ptype = classify_page_type(u)
            if ptype == "service":
                has_money_page = True
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
                "slug": u.replace("https://azariangrowthagency.com/", "/"),
                "type": ptype,
                "action": action,
                "role": role,
            })
        # Sort: money pages first, then support, then content
        role_order = {"money": 0, "support": 1, "content": 2}
        url_details_list.sort(key=lambda x: role_order.get(x["role"], 2))

        # Build cluster-level analysis
        types_present = set(d["type"] for d in url_details_list)
        has_conversion_risk = "service" in types_present and "blog" in types_present

        if has_conversion_risk:
            analysis = f"CONVERSION RISK: {sum(1 for d in url_details_list if d['type']=='blog')} blog posts competing against the service page for the same topic. Blog content may outrank the service page, pushing users away from conversion."
        elif len(urls) > 10:
            analysis = f"SEVERE TOPIC FRAGMENTATION: {len(urls)} pages covering the same topic dilutes authority. Consolidate into 1 pillar + 2-3 angle-specific posts."
        else:
            analysis = f"{len(urls)} pages overlap on this topic. Identify the strongest performer and merge weaker pages via 301 redirects."

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
        "skipped": len(thin_actionable),  # only actionable thin pages
        "skipped_listings": len(thin_listings),  # excluded listing pages
        "noise": noise_count,
        "thin_local": len(thin_local),
        "thin_tools": len(thin_tools),
        "thin_other": len(thin_other),
    }

    # Top cannibalized for exec summary
    top_cannib_summary = cannib_full.head(5)[["cluster_name", "url_count"]].to_dict("records")

    # Prepare enhancement data as JSON-safe dicts
    enh = {}
    if not competitor_df.empty:
        enh["competitor"] = competitor_df.to_dict("records")
        enh["comp_stats"] = {
            "gaps": len(competitor_df[competitor_df["status"] == "GAP"]),
            "advantages": len(competitor_df[competitor_df["status"] == "Azarian advantage"]),
            "shared": len(competitor_df[competitor_df["status"].str.contains("cover|overlap", na=False)]),
        }
    if not similarity_df.empty:
        sim_records = similarity_df.to_dict("records")
        for r in sim_records:
            r["url_a"] = r["url_a"].replace("https://azariangrowthagency.com/", "/")
            r["url_b"] = r["url_b"].replace("https://azariangrowthagency.com/", "/")
        enh["similarity"] = sim_records
    if not intent_df.empty:
        enh["intent"] = intent_df["primary_intent"].value_counts().to_dict()
    if not freshness_df.empty:
        enh["freshness"] = freshness_df["freshness"].value_counts().to_dict()
    if not brand_df.empty:
        enh["brand"] = {
            "distribution": brand_df["rating"].value_counts().to_dict(),
            "avg_score": round(brand_df["brand_score"].mean(), 1),
            "bottom": brand_df.head(20).to_dict("records"),
        }
    if not merge_df.empty:
        enh["merges"] = merge_df.to_dict("records")

    from src.dashboard_html import build_html
    html = build_html(
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
    )

    out_path = os.path.join(OUTPUT_DIR, "dashboard.html")
    with open(out_path, "w") as f:
        f.write(html)
    logger.info("Dashboard saved to %s", out_path)
    return out_path


def _build_html(treemap_data, cannib_chart_data, cannib_detail, content_types,
                all_clusters, url_table, stats, thin_tools, thin_local, thin_other, top_cannib_summary,
                enhancements=None):
    if enhancements is None:
        enhancements = {}

    # Pre-compute for executive summary
    total_thin = stats['thin_tools'] + stats['thin_local'] + stats['thin_other']
    total_cannib_urls = sum(c["count"] for c in cannib_detail)
    critical_count = sum(1 for c in cannib_detail if c["severity"] == "critical")
    high_count = sum(1 for c in cannib_detail if c["severity"] == "high")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Topical Authority Audit — Azarian Growth Agency</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
  :root {{
    --bg: #0f1117; --surface: #1a1d27; --border: #2a2d3a;
    --text: #e4e4e7; --muted: #9ca3af; --accent: #6366f1;
    --red: #ef4444; --green: #22c55e; --yellow: #eab308; --blue: #3b82f6;
  }}
  /* Tab navigation */
  .nav {{ display:flex; background:var(--surface); border-bottom:1px solid var(--border); padding:0 24px; position:sticky; top:0; z-index:100; overflow-x:auto; }}
  .nav-tab {{ padding:14px 20px; font-size:13px; font-weight:500; color:var(--muted); cursor:pointer; border-bottom:2px solid transparent; white-space:nowrap; transition:all 0.2s; }}
  .nav-tab:hover {{ color:var(--text); }}
  .nav-tab.active {{ color:var(--accent); border-bottom-color:var(--accent); }}
  .nav-tab .nav-badge {{ display:inline-block; padding:1px 6px; border-radius:8px; font-size:10px; margin-left:4px; background:rgba(99,102,241,0.15); color:var(--accent); }}
  .nav-tab .nav-badge.red {{ background:rgba(239,68,68,0.15); color:var(--red); }}
  .tab-content {{ display:none; }}
  .tab-content.active {{ display:block; }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; }}

  /* Header */
  .header {{ background: var(--surface); color: white; padding: 40px 48px; border-bottom: 1px solid var(--border); }}
  .header-top {{ display: flex; justify-content: space-between; align-items: flex-start; }}
  .header h1 {{ font-size: 28px; font-weight: 700; letter-spacing: -0.5px; }}
  .header .subtitle {{ color: var(--muted); font-size: 14px; margin-top: 4px; }}
  .header .date {{ color: #6b7280; font-size: 13px; }}
  .header-line {{ height: 3px; background: var(--accent); width: 60px; margin-top: 16px; }}

  /* Stats */
  .stats-grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 1px; background: var(--border); margin: 0; }}
  .stat {{ background: var(--surface); padding: 24px 20px; text-align: center; }}
  .stat .value {{ font-size: 36px; font-weight: 700; }}
  .stat .label {{ font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; margin-top: 4px; }}
  .stat .value.red {{ color: var(--red); }}
  .stat .value.yellow {{ color: var(--yellow); }}
  .stat .value.muted {{ color: var(--muted); }}
  .stat .value.accent {{ color: var(--accent); }}

  /* Sections */
  .section {{ padding: 32px 48px; }}
  .section + .section {{ border-top: 1px solid var(--border); }}
  .section h2 {{ font-size: 20px; font-weight: 700; margin-bottom: 8px; color: var(--text); }}
  .section .section-desc {{ color: var(--muted); font-size: 14px; margin-bottom: 20px; }}

  /* Executive Summary */
  .exec-summary {{ background: #141620; padding: 32px 48px; border-bottom: 1px solid var(--border); }}
  .exec-summary h2 {{ font-size: 20px; font-weight: 700; margin-bottom: 16px; }}
  .exec-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
  .exec-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 20px; }}
  .exec-card h3 {{ font-size: 14px; font-weight: 600; margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }}
  .exec-card p {{ font-size: 13px; color: var(--muted); line-height: 1.7; }}
  .exec-card .highlight {{ font-weight: 600; color: var(--text); }}
  .dot {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; }}
  .dot-red {{ background: var(--red); }}
  .dot-yellow {{ background: var(--yellow); }}
  .dot-blue {{ background: var(--accent); }}
  .dot-green {{ background: var(--green); }}

  /* Scorecard table */
  .scorecard {{ width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 16px; }}
  .scorecard th {{ text-align: left; padding: 10px 14px; background: #111320; font-weight: 500; color: var(--muted);
                  text-transform: uppercase; font-size: 11px; letter-spacing: 0.5px; }}
  .scorecard td {{ padding: 10px 14px; border-bottom: 1px solid var(--border); }}
  .scorecard .status {{ font-weight: 600; font-size: 12px; }}
  .scorecard .status-critical {{ color: var(--red); }}
  .scorecard .status-warning {{ color: var(--yellow); }}
  .scorecard .status-ok {{ color: var(--green); }}
  .scorecard .status-info {{ color: var(--accent); }}

  /* Charts */
  .chart-row {{ display: grid; grid-template-columns: 2fr 1fr; gap: 20px; }}
  .chart-box {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 20px; }}
  .chart-box h3 {{ font-size: 13px; color: var(--muted); margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px; }}

  /* Tables */
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ text-align: left; padding: 10px 14px; background: #111320; color: var(--muted); font-weight: 500;
       text-transform: uppercase; font-size: 11px; letter-spacing: 0.5px; position: sticky; top: 0; z-index: 1; }}
  td {{ padding: 10px 14px; border-bottom: 1px solid var(--border); vertical-align: top; }}
  tr:hover td {{ background: rgba(99,102,241,0.07); }}
  .table-wrap {{ max-height: 600px; overflow-y: auto; border: 1px solid var(--border); border-radius: 8px; }}

  /* Badges */
  .badge {{ display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; }}
  .badge-red {{ background: rgba(239,68,68,0.15); color: var(--red); border: 1px solid rgba(239,68,68,0.3); }}
  .badge-yellow {{ background: rgba(234,179,8,0.15); color: var(--yellow); border: 1px solid rgba(234,179,8,0.3); }}
  .badge-green {{ background: rgba(34,197,94,0.15); color: var(--green); border: 1px solid rgba(34,197,94,0.3); }}
  .badge-blue {{ background: rgba(59,130,246,0.15); color: var(--blue); border: 1px solid rgba(59,130,246,0.3); }}
  .badge-gray {{ background: rgba(156,163,175,0.1); color: var(--muted); border: 1px solid var(--border); }}

  /* Search */
  .search {{ width: 100%; padding: 12px 16px; background: var(--surface); border: 1px solid var(--border);
            border-radius: 8px; color: var(--text); font-size: 14px; margin-bottom: 16px; outline: none; }}
  .search:focus {{ border-color: var(--accent); box-shadow: 0 0 0 3px rgba(99,102,241,0.15); }}

  /* Tabs */
  .tabs {{ display: flex; gap: 0; margin-bottom: 20px; }}
  .tab {{ padding: 10px 20px; background: var(--surface); border: 1px solid var(--border); cursor: pointer;
         font-size: 13px; color: var(--muted); font-weight: 500; transition: all 0.2s; }}
  .tab:first-child {{ border-radius: 8px 0 0 8px; }}
  .tab:last-child {{ border-radius: 0 8px 8px 0; }}
  .tab.active {{ background: var(--accent); color: white; border-color: var(--accent); }}
  .tab:hover:not(.active) {{ color: var(--text); background: #22253a; }}

  /* Detail panel */
  .detail-panel {{ display: none; background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
                  padding: 20px; margin-bottom: 16px; }}
  .detail-panel.show {{ display: block; }}
  .detail-panel h3 {{ margin-bottom: 12px; font-size: 16px; }}
  .detail-urls {{ max-height: 200px; overflow-y: auto; }}
  .detail-urls a {{ display: block; padding: 4px 0; font-size: 13px; color: var(--blue); }}

  /* Cannib cards */
  .cannib-list {{ display: flex; flex-direction: column; gap: 12px; }}
  .cannib-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; cursor: pointer; transition: all 0.15s; }}
  .cannib-card:hover {{ border-color: var(--accent); box-shadow: 0 2px 8px rgba(0,0,0,0.2); }}
  .cannib-card.expanded .cannib-urls {{ display: block; }}
  .cannib-header {{ display: flex; justify-content: space-between; align-items: center; }}
  .cannib-header h4 {{ font-size: 14px; font-weight: 600; }}
  .cannib-meta {{ display: flex; gap: 12px; align-items: center; }}
  .cannib-rec {{ font-size: 12px; color: var(--muted); margin-top: 6px; font-style: italic; }}
  .cannib-urls {{ display: none; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border); }}
  .cannib-urls a {{ display: block; padding: 3px 0; font-size: 13px; color: var(--blue); }}
  .cannib-arrow {{ color: var(--muted); transition: transform 0.2s; }}
  .cannib-card.expanded .cannib-arrow {{ transform: rotate(90deg); }}

  /* Thin content */
  .thin-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; margin-bottom: 20px; }}
  .thin-card-header {{ padding: 16px 20px; background: #1e2130; border-bottom: 1px solid var(--border);
                       display: flex; justify-content: space-between; align-items: center; cursor: pointer; }}
  .thin-card-header h3 {{ font-size: 15px; font-weight: 600; }}
  .thin-card-body {{ display: none; }}
  .thin-card.expanded .thin-card-body {{ display: block; }}
  .thin-url-row {{ padding: 10px 20px; border-bottom: 1px solid var(--border); display: grid; grid-template-columns: 1fr 60px 2fr; gap: 16px; align-items: center; }}
  .thin-url-row:last-child {{ border-bottom: none; }}
  .thin-url-row a {{ color: var(--blue); font-size: 13px; word-break: break-all; }}
  .thin-url-row .words {{ font-size: 12px; color: var(--red); font-weight: 600; text-align: center; }}
  .thin-url-row .rec {{ font-size: 12px; color: var(--muted); }}

  .kw {{ color: var(--muted); font-size: 12px; max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  a {{ color: var(--blue); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}

  .thin-url-row a {{ color: var(--blue); }}

  .footer {{ padding: 24px 48px; background: var(--surface); border-top: 1px solid var(--border);
            font-size: 12px; color: var(--muted); text-align: center; }}
</style>
</head>
<body>

<!-- HEADER -->
<div class="header">
  <div class="header-top">
    <div>
      <h1>TOPICAL AUTHORITY AUDIT</h1>
      <div class="subtitle">azariangrowthagency.com</div>
    </div>
    <div style="text-align:right">
      <div class="date">Prepared by: Azarian Growth Agency</div>
      <div class="date">Date: April 2026</div>
      <div class="date">Source: Topical Authority Mapper | {stats['total_urls']} Pages Analyzed</div>
    </div>
  </div>
  <div class="header-line"></div>
</div>

<!-- STATS -->
<div class="stats-grid">
  <div class="stat"><div class="value accent">{stats['total_urls']}</div><div class="label">URLs Analyzed</div></div>
  <div class="stat"><div class="value accent">{stats['total_clusters']}</div><div class="label">Topic Clusters</div></div>
  <div class="stat"><div class="value red">{stats['cannib_flags']}</div><div class="label">Cannibalization Flags</div></div>
  <div class="stat"><div class="value yellow">{stats['skipped']}</div><div class="label">Thin / Skipped Pages</div></div>
  <div class="stat"><div class="value muted">{stats['noise']}</div><div class="label">Unclustered Pages</div></div>
</div>

<!-- EXECUTIVE SUMMARY -->
<div class="exec-summary">
  <h2>Executive Summary</h2>
  <p style="color:var(--muted);font-size:14px;margin-bottom:20px;max-width:900px;">
    This analysis mapped {stats['total_urls']} indexable pages across azariangrowthagency.com into {stats['total_clusters']} semantic topic clusters
    using AI-powered content embeddings. The site demonstrates strong topical breadth across core verticals (PPC, SEO, SaaS, fintech, legal)
    but suffers from significant content cannibalization and topic fragmentation that is diluting ranking potential.
  </p>

  <div class="exec-grid">
    <div class="exec-card">
      <h3><span class="dot dot-red"></span> Critical: Content Cannibalization</h3>
      <p>
        <span class="highlight">{stats['cannib_flags']} of {stats['total_clusters']} clusters</span> have multiple URLs competing for the same topic.
        The worst offenders — {', '.join(c['cluster_name'] + ' (' + str(c['url_count']) + ')' for c in top_cannib_summary)} —
        have 14-31 pages each fighting for the same keywords. This directly dilutes PageRank, confuses Google's ranking signals,
        and splits click-through across weaker pages instead of concentrating authority on pillar content.
      </p>
    </div>
    <div class="exec-card">
      <h3><span class="dot dot-yellow"></span> Warning: Thin Content ({stats['thin_tools'] + stats['thin_local'] + stats['thin_other']} pages)</h3>
      <p>
        <span class="highlight">{stats['thin_tools']} tool review pages</span> average under 300 words — too thin to rank.
        <span class="highlight">{stats['thin_local']} local/city landing pages</span> are stubs under 150 words with no unique content.
        <span class="highlight">{stats['thin_other']} hub/guide pages</span> (case studies, industry pages) need substantive content.
        These pages consume crawl budget without contributing to topical authority.
      </p>
    </div>
    <div class="exec-card">
      <h3><span class="dot dot-blue"></span> Opportunity: Topic Depth vs. Breadth</h3>
      <p>
        With {stats['total_clusters']} clusters across ~1,000 pages, most topics average only 3-5 pages each.
        The site is <span class="highlight">wide but shallow</span> on many verticals. Consolidating cannibalized clusters into
        pillar pages and building supporting content around them would create stronger topical authority signals
        for Google and AI search engines (GEO/AEO).
      </p>
    </div>
    <div class="exec-card">
      <h3><span class="dot dot-green"></span> Strength: ICP-Aligned Verticals</h3>
      <p>
        Strong vertical clusters align directly with Azarian's ICPs:
        <span class="highlight">Legal (21 pages), Private Equity (20), Fintech (16), SaaS (17), Home Services (7)</span>.
        These represent topical authority strongholds. Recommendation: protect and deepen these clusters
        rather than broadening into more topics.
      </p>
    </div>
  </div>

  <!-- Scorecard -->
  <table class="scorecard" style="margin-top:24px;">
    <thead><tr><th>Area</th><th>Status</th><th>Issues</th><th>Impact</th></tr></thead>
    <tbody>
      <tr><td>Topic Coverage (Breadth)</td><td><span class="status status-ok">Strong</span></td><td>{stats['total_clusters']} clusters</td><td>Good coverage across core verticals and ICPs</td></tr>
      <tr><td>Content Cannibalization</td><td><span class="status status-critical">Critical</span></td><td>{stats['cannib_flags']} clusters</td><td>Diluted ranking signals, split authority across competing pages</td></tr>
      <tr><td>Thin Content</td><td><span class="status status-warning">Needs Fix</span></td><td>{stats['thin_tools'] + stats['thin_local'] + stats['thin_other']} pages</td><td>Wasted crawl budget, no ranking potential</td></tr>
      <tr><td>Unclustered / Orphan Pages</td><td><span class="status status-warning">Needs Fix</span></td><td>{stats['noise']} pages</td><td>Off-topic or isolated content not supporting any cluster</td></tr>
      <tr><td>Content Type Balance</td><td><span class="status status-info">Review</span></td><td>69% educational</td><td>Low on comparison and how-to content — SERP feature gaps</td></tr>
    </tbody>
  </table>
</div>

<!-- CHARTS -->
<div class="section">
  <h2>Topic Cluster Overview</h2>
  <p class="section-desc">Top 30 clusters by page count. Click clusters for detail.</p>
  <div class="chart-row">
    <div class="chart-box"><h3>Topic Cluster Map</h3><div id="treemap"></div></div>
    <div class="chart-box"><h3>Content Type Distribution</h3><div id="pie"></div></div>
  </div>
</div>

<!-- CANNIBALIZATION CHART -->
<div class="section">
  <h2>Cannibalization Overview</h2>
  <p class="section-desc">Clusters where multiple URLs compete for the same topic. Bars show URL count per cluster.</p>
  <div class="chart-box"><div id="cannib-bar"></div></div>
</div>

<!-- CANNIBALIZATION DETAIL -->
<div class="section">
  <h2>Cannibalization Detail — Affected URLs</h2>
  <p class="section-desc">{stats['cannib_flags']} clusters flagged. Click any cluster to expand and see all competing URLs with recommendations.</p>
  <div class="tabs">
    <div class="tab active" onclick="filterCannib('all',this)">All ({len(cannib_detail)})</div>
    <div class="tab" onclick="filterCannib('critical',this)">Critical ({critical_count})</div>
    <div class="tab" onclick="filterCannib('high',this)">High ({high_count})</div>
    <div class="tab" onclick="filterCannib('moderate',this)">Moderate ({len(cannib_detail) - critical_count - high_count})</div>
  </div>
  <input type="text" class="search" id="cannib-search" placeholder="Search cannibalized clusters...">
  <div id="cannib-list" class="cannib-list"></div>
</div>

<!-- THIN CONTENT DETAIL -->
<div class="section">
  <h2>Thin Content — Pages Needing Action</h2>
  <p class="section-desc">{stats['thin_tools'] + stats['thin_local'] + stats['thin_other']} pages flagged as thin content (&lt;300 words). Each includes a specific recommendation.</p>

  <div class="thin-card" id="thin-tools">
    <div class="thin-card-header" onclick="this.parentElement.classList.toggle('expanded')">
      <h3><span class="badge badge-yellow">{stats['thin_tools']}</span>&nbsp; Tool Review Pages</h3>
      <span style="color:var(--muted);font-size:12px">Click to expand</span>
    </div>
    <div class="thin-card-body" id="thin-tools-body"></div>
  </div>

  <div class="thin-card" id="thin-local">
    <div class="thin-card-header" onclick="this.parentElement.classList.toggle('expanded')">
      <h3><span class="badge badge-red">{stats['thin_local']}</span>&nbsp; Local / City Landing Pages</h3>
      <span style="color:var(--muted);font-size:12px">Click to expand</span>
    </div>
    <div class="thin-card-body" id="thin-local-body"></div>
  </div>

  <div class="thin-card" id="thin-other">
    <div class="thin-card-header" onclick="this.parentElement.classList.toggle('expanded')">
      <h3><span class="badge badge-gray">{stats['thin_other']}</span>&nbsp; Other Thin Pages (Case Studies, Hubs, Guides)</h3>
      <span style="color:var(--muted);font-size:12px">Click to expand</span>
    </div>
    <div class="thin-card-body" id="thin-other-body"></div>
  </div>
</div>

<!-- ENHANCEMENTS -->
<div id="enh-competitor" class="section" style="display:none">
  <h2>Competitor Gap Analysis</h2>
  <p class="section-desc">Topic comparison: Azarian Growth Agency vs NoGood vs SingleGrain</p>
  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-bottom:20px;">
    <div class="stat" style="padding:16px"><div class="value" style="font-size:28px;color:var(--green)" id="comp-adv">0</div><div class="label">Azarian Advantages</div></div>
    <div class="stat" style="padding:16px"><div class="value" style="font-size:28px;color:var(--blue)" id="comp-shared">0</div><div class="label">Shared Topics</div></div>
    <div class="stat" style="padding:16px"><div class="value" style="font-size:28px;color:var(--red)" id="comp-gaps">0</div><div class="label">Content Gaps</div></div>
  </div>
  <div class="chart-box"><div id="comp-chart"></div></div>
  <input type="text" class="search" id="comp-search" placeholder="Search topics..." style="margin-top:16px">
  <div class="table-wrap" style="margin-top:0"><table id="comp-table"><thead><tr><th>Topic</th><th>Azarian</th><th>NoGood</th><th>SingleGrain</th><th>Status</th></tr></thead><tbody></tbody></table></div>
</div>

<div id="enh-similarity" class="section" style="display:none">
  <h2>Near-Duplicate Pages</h2>
  <p class="section-desc">URL pairs with 80%+ content similarity — candidates for merging or differentiation.</p>
  <div class="table-wrap"><table id="sim-table"><thead><tr><th>URL A</th><th>URL B</th><th>Similarity</th><th>Action</th></tr></thead><tbody></tbody></table></div>
</div>

<div id="enh-intent" class="section" style="display:none">
  <h2>Search Intent Distribution</h2>
  <p class="section-desc">Classification of all analyzed pages by search intent type.</p>
  <div class="chart-row"><div class="chart-box"><div id="intent-chart"></div></div><div class="chart-box" id="intent-summary" style="display:flex;flex-direction:column;justify-content:center;padding:24px;font-size:14px;line-height:2.2;"></div></div>
</div>

<div id="enh-freshness" class="section" style="display:none">
  <h2>Content Freshness</h2>
  <p class="section-desc">How recently content was last modified, based on sitemap lastmod dates.</p>
  <div class="chart-box"><div id="freshness-chart"></div></div>
</div>

<div id="enh-brand" class="section" style="display:none">
  <h2>Brand Voice Alignment</h2>
  <p class="section-desc">How well each page aligns with Azarian's brand voice profile.</p>
  <div class="chart-row">
    <div class="chart-box"><div id="brand-chart"></div></div>
    <div class="chart-box" style="display:flex;flex-direction:column;justify-content:center;padding:24px;">
      <div style="font-size:48px;font-weight:700;color:var(--accent)" id="brand-avg">—</div>
      <div style="font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:1px">Avg Brand Score / 100</div>
    </div>
  </div>
  <h3 style="margin-top:20px;font-size:14px;color:var(--muted)">Lowest Scoring Pages</h3>
  <div class="table-wrap"><table id="brand-table"><thead><tr><th>URL</th><th>Score</th><th>Rating</th><th>Tone Match</th><th>Violations</th></tr></thead><tbody></tbody></table></div>
</div>

<div id="enh-merges" class="section" style="display:none">
  <h2>Cluster Merge Suggestions</h2>
  <p class="section-desc">Clusters with high semantic overlap that should be combined to strengthen topical authority.</p>
  <div class="table-wrap"><table id="merge-table"><thead><tr><th>Cluster A</th><th>Cluster B</th><th>Similarity</th><th>Recommendation</th></tr></thead><tbody></tbody></table></div>
</div>

<!-- ALL CLUSTERS -->
<div class="section">
  <h2>All Clusters</h2>
  <p class="section-desc">Click any row to see all URLs and content recommendations for that cluster.</p>
  <input type="text" class="search" id="cluster-search" placeholder="Search clusters by name, keyword, or content type...">
  <div id="cluster-detail" class="detail-panel">
    <h3 id="detail-title"></h3>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:12px;">
      <div><strong>Keywords:</strong> <span id="detail-kw" style="color:var(--muted);"></span></div>
      <div><strong>Content Type:</strong> <span id="detail-type"></span></div>
      <div><strong>Angle:</strong> <span id="detail-angle"></span></div>
      <div><strong>CTA Style:</strong> <span id="detail-cta"></span></div>
    </div>
    <strong>URLs in this cluster:</strong>
    <div id="detail-urls" class="detail-urls"></div>
  </div>
  <div class="table-wrap">
    <table id="cluster-table">
      <thead><tr><th>ID</th><th>Cluster Name</th><th>URLs</th><th>Keywords</th><th>Content Type</th><th>Status</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>
</div>

<!-- URL EXPLORER -->
<div class="section">
  <h2>URL Explorer</h2>
  <p class="section-desc">Search any URL to see its cluster assignment.</p>
  <input type="text" class="search" id="url-search" placeholder="Search URLs...">
  <div class="table-wrap">
    <table id="url-table">
      <thead><tr><th>URL</th><th>Cluster ID</th><th>Cluster Name</th><th>Secondary Clusters</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>
</div>

<div class="footer">
  Topical Authority Mapper &mdash; Azarian Growth Agency &mdash; April 2026 &mdash; CONFIDENTIAL
</div>

<script>
const TREEMAP = {json.dumps(treemap_data)};
const CANNIB_CHART = {json.dumps(cannib_chart_data)};
const CANNIB_DETAIL = {json.dumps(cannib_detail)};
const CONTENT_TYPES = {json.dumps(content_types)};
const ALL_CLUSTERS = {json.dumps(all_clusters)};
const URL_TABLE = {json.dumps(url_table)};
const THIN_TOOLS = {json.dumps(thin_tools)};
const THIN_LOCAL = {json.dumps(thin_local)};
const THIN_OTHER = {json.dumps(thin_other)};

const plotBg = '#1a1d27';
const plotText = '#9ca3af';
const plotLayout = {{ paper_bgcolor: plotBg, plot_bgcolor: plotBg, font: {{ color: plotText, size: 12 }}, margin: {{ t: 10, b: 30, l: 40, r: 10 }} }};

// Treemap — Viridis colorscale like v1
Plotly.newPlot('treemap', [{{
  type: 'treemap',
  labels: TREEMAP.labels,
  values: TREEMAP.values,
  parents: TREEMAP.labels.map(() => ''),
  text: TREEMAP.keywords.map(k => k.split(',').slice(0,3).join(', ')),
  hovertemplate: '<b>%{{label}}</b><br>%{{value}} URLs<br>%{{text}}<extra></extra>',
  textinfo: 'label+value',
  textfont: {{ size: 14, color: '#ffffff' }},
  marker: {{ colorscale: 'Viridis', colors: TREEMAP.values }},
}}], {{...plotLayout, margin: {{t:10,b:10,l:10,r:10}}, height: 420}}, {{responsive: true}});

// Content type pie
Plotly.newPlot('pie', [{{
  type: 'pie', labels: Object.keys(CONTENT_TYPES), values: Object.values(CONTENT_TYPES),
  hole: 0.45, textinfo: 'label+percent',
  marker: {{ colors: ['#6366f1','#8b5cf6','#a78bfa','#c4b5fd','#3b82f6','#60a5fa'] }},
  textfont: {{ size: 11 }},
}}], {{...plotLayout, height: 420, showlegend: false, margin: {{t:10,b:10,l:10,r:10}}}}, {{responsive: true}});

// Cannibalization bar — HORIZONTAL for readable labels
Plotly.newPlot('cannib-bar', [{{
  type: 'bar',
  y: CANNIB_CHART.labels.slice().reverse(),
  x: CANNIB_CHART.values.slice().reverse(),
  orientation: 'h',
  marker: {{ color: CANNIB_CHART.values.slice().reverse().map(v => v >= 10 ? '#ef4444' : v >= 6 ? '#eab308' : '#22c55e') }},
  hovertemplate: '<b>%{{y}}</b><br>%{{x}} competing URLs<extra></extra>',
  text: CANNIB_CHART.values.slice().reverse(),
  textposition: 'outside',
  textfont: {{ size: 11, color: '#9ca3af' }},
}}], {{
  ...plotLayout,
  height: Math.max(500, CANNIB_CHART.labels.length * 28),
  margin: {{t:10, b:20, l: 200, r: 60}},
  xaxis: {{title: 'Competing URLs', gridcolor: '#2a2d3a'}},
  yaxis: {{tickfont: {{size: 12, color: '#e4e4e7'}}}},
}}, {{responsive: true}});

// Cannibalization detail list
let currentCannibFilter = 'all';
function filterCannib(severity, tabEl) {{
  currentCannibFilter = severity;
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  if (tabEl) tabEl.classList.add('active');
  renderCannibList();
}}

function renderCannibList() {{
  const search = (document.getElementById('cannib-search').value || '').toLowerCase();
  const container = document.getElementById('cannib-list');
  let items = CANNIB_DETAIL;
  if (currentCannibFilter !== 'all') items = items.filter(c => c.severity === currentCannibFilter);
  if (search) items = items.filter(c => c.name.toLowerCase().includes(search) || c.urls.some(u => u.toLowerCase().includes(search)));

  container.innerHTML = items.map((c, i) => `
    <div class="cannib-card" onclick="this.classList.toggle('expanded')">
      <div class="cannib-header">
        <h4>${{c.name}}</h4>
        <div class="cannib-meta">
          <span class="badge ${{c.severity === 'critical' ? 'badge-red' : c.severity === 'high' ? 'badge-yellow' : 'badge-green'}}">${{c.count}} URLs &middot; ${{c.severity}}</span>
          <span class="cannib-arrow">&#9654;</span>
        </div>
      </div>
      <div class="cannib-rec">${{c.recommendation}}</div>
      <div class="cannib-urls">
        ${{c.urls.map(u => `<a href="${{u}}" target="_blank">${{u.replace('https://azariangrowthagency.com/','')}}</a>`).join('')}}
      </div>
    </div>
  `).join('');
}}
renderCannibList();
document.getElementById('cannib-search').addEventListener('input', renderCannibList);

// Thin content sections
function renderThinSection(data, bodyId) {{
  const body = document.getElementById(bodyId);
  body.innerHTML = data.map(d => `
    <div class="thin-url-row">
      <a href="${{d.url}}" target="_blank">${{d.url.replace('https://azariangrowthagency.com/','')}}</a>
      <div class="words">${{d.word_count}}w</div>
      <div class="rec">${{d.recommendation}}</div>
    </div>
  `).join('');
}}
renderThinSection(THIN_TOOLS, 'thin-tools-body');
renderThinSection(THIN_LOCAL, 'thin-local-body');
renderThinSection(THIN_OTHER, 'thin-other-body');

// Cluster table
function renderClusterTable(filter = '') {{
  const tbody = document.querySelector('#cluster-table tbody');
  const f = filter.toLowerCase();
  const rows = ALL_CLUSTERS.filter(c =>
    !f || c.name.toLowerCase().includes(f) || c.keywords.toLowerCase().includes(f) || c.content_type.toLowerCase().includes(f)
  );
  tbody.innerHTML = rows.map(c => `
    <tr style="cursor:pointer" onclick="showClusterDetail(${{c.id}})">
      <td>${{c.id}}</td>
      <td><strong>${{c.name}}</strong></td>
      <td>${{c.urls}}</td>
      <td class="kw">${{c.keywords}}</td>
      <td><span class="badge badge-blue">${{c.content_type || '-'}}</span></td>
      <td>${{c.cannibalized ? '<span class="badge badge-red">Cannibalized</span>' : '<span class="badge badge-green">OK</span>'}}</td>
    </tr>
  `).join('');
}}
renderClusterTable();
document.getElementById('cluster-search').addEventListener('input', e => renderClusterTable(e.target.value));

function showClusterDetail(id) {{
  const c = ALL_CLUSTERS.find(x => x.id === id);
  if (!c) return;
  const urls = URL_TABLE.filter(u => u.cluster === id);
  document.getElementById('detail-title').textContent = `[${{c.id}}] ${{c.name}} — ${{c.urls}} URLs`;
  document.getElementById('detail-kw').textContent = c.keywords;
  document.getElementById('detail-type').textContent = c.content_type;
  document.getElementById('detail-angle').textContent = c.angle;
  document.getElementById('detail-cta').textContent = c.cta;
  document.getElementById('detail-urls').innerHTML = urls.map(u =>
    `<a href="${{u.url}}" target="_blank">${{u.url}}</a>`
  ).join('');
  document.getElementById('cluster-detail').classList.add('show');
  document.getElementById('cluster-detail').scrollIntoView({{behavior:'smooth',block:'nearest'}});
}}

// URL table
function renderUrlTable(filter = '') {{
  const tbody = document.querySelector('#url-table tbody');
  const f = filter.toLowerCase();
  const rows = URL_TABLE.filter(u => !f || u.url.toLowerCase().includes(f) || (u.name && u.name.toLowerCase().includes(f)));
  const limited = rows.slice(0, 200);
  tbody.innerHTML = limited.map(u => `
    <tr>
      <td style="max-width:400px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
        <a href="${{u.url}}" target="_blank">${{u.url.replace('https://azariangrowthagency.com/','')}}</a>
      </td>
      <td>${{u.cluster}}</td>
      <td>${{u.name || 'Unclustered'}}</td>
      <td style="color:var(--muted)">${{u.secondary || ''}}</td>
    </tr>
  `).join('');
  if (rows.length > 200) tbody.innerHTML += `<tr><td colspan="4" style="color:var(--muted);text-align:center">Showing 200 of ${{rows.length}} &mdash; refine your search</td></tr>`;
}}
renderUrlTable();
document.getElementById('url-search').addEventListener('input', e => renderUrlTable(e.target.value));

// === ENHANCEMENTS ===
const ENH = {json.dumps(enhancements)};

// Competitor gap
if (ENH.competitor) {{
  document.getElementById('enh-competitor').style.display = '';
  document.getElementById('comp-adv').textContent = ENH.comp_stats.advantages;
  document.getElementById('comp-shared').textContent = ENH.comp_stats.shared;
  document.getElementById('comp-gaps').textContent = ENH.comp_stats.gaps;

  const compGroups = {{}};
  ENH.competitor.forEach(c => {{ compGroups[c.status] = (compGroups[c.status]||0)+1; }});
  Plotly.newPlot('comp-chart',[{{
    type:'bar', y:Object.keys(compGroups), x:Object.values(compGroups), orientation:'h',
    marker:{{color:Object.keys(compGroups).map(k=>k.includes('GAP')?'#ef4444':k.includes('advantage')?'#22c55e':'#6366f1')}},
    text:Object.values(compGroups), textposition:'outside', textfont:{{color:'#9ca3af',size:11}},
  }}],{{...plotLayout,height:150,margin:{{t:5,b:20,l:180,r:50}},yaxis:{{tickfont:{{size:12,color:'#e4e4e7'}}}},xaxis:{{gridcolor:'#2a2d3a'}}}},{{responsive:true}});

  function renderCompTable(f='') {{
    const tbody=document.querySelector('#comp-table tbody');
    const rows=ENH.competitor.filter(c=>!f||c.topic.toLowerCase().includes(f));
    tbody.innerHTML=rows.slice(0,200).map(c=>`<tr>
      <td>${{c.topic}}</td><td>${{c.azarian?'Y':''}}</td><td>${{c.nogood?'Y':''}}</td><td>${{c.singlegrain?'Y':''}}</td>
      <td><span class="badge ${{c.status.includes('GAP')?'badge-red':c.status.includes('advantage')?'badge-green':'badge-blue'}}">${{c.status}}</span></td>
    </tr>`).join('');
  }}
  renderCompTable();
  document.getElementById('comp-search').addEventListener('input',e=>renderCompTable(e.target.value.toLowerCase()));
}}

// Similarity
if (ENH.similarity) {{
  document.getElementById('enh-similarity').style.display = '';
  const tbody=document.querySelector('#sim-table tbody');
  tbody.innerHTML=ENH.similarity.map(s=>`<tr>
    <td style="font-size:12px">${{s.url_a}}</td><td style="font-size:12px">${{s.url_b}}</td>
    <td style="color:${{s.similarity>=0.92?'#ef4444':s.similarity>=0.80?'#eab308':'#9ca3af'}};font-weight:700">${{(s.similarity*100).toFixed(0)}}%</td>
    <td style="font-size:11px;color:var(--muted)">${{s.action}}</td>
  </tr>`).join('');
}}

// Intent
if (ENH.intent) {{
  document.getElementById('enh-intent').style.display = '';
  const iLabels=Object.keys(ENH.intent), iValues=Object.values(ENH.intent);
  const iColors={{'informational':'#6366f1','commercial':'#3b82f6','transactional':'#22c55e','navigational':'#9ca3af'}};
  Plotly.newPlot('intent-chart',[{{
    type:'pie',labels:iLabels,values:iValues,hole:0.5,textinfo:'label+percent',
    marker:{{colors:iLabels.map(l=>iColors[l]||'#6b7280')}},textfont:{{size:12}},
  }}],{{...plotLayout,height:300,showlegend:false,margin:{{t:10,b:10,l:10,r:10}}}},{{responsive:true}});
  const total=iValues.reduce((a,b)=>a+b,0);
  document.getElementById('intent-summary').innerHTML=iLabels.map(l=>
    `<div><span style="color:${{iColors[l]||'#6b7280'}};font-weight:700">${{ENH.intent[l]}}</span> <span style="color:var(--muted)">${{l}} (${{(ENH.intent[l]/total*100).toFixed(0)}}%)</span></div>`
  ).join('');
}}

// Freshness
if (ENH.freshness) {{
  document.getElementById('enh-freshness').style.display = '';
  const fOrder=['Fresh (< 1 month)','Recent (1-3 months)','Aging (3-6 months)','Stale (6-12 months)','Decaying (12+ months)'];
  const fLabels=fOrder.filter(k=>ENH.freshness[k]);
  const fValues=fLabels.map(k=>ENH.freshness[k]||0);
  const fColors={{'Fresh (< 1 month)':'#22c55e','Recent (1-3 months)':'#4ade80','Aging (3-6 months)':'#eab308','Stale (6-12 months)':'#f97316','Decaying (12+ months)':'#ef4444'}};
  Plotly.newPlot('freshness-chart',[{{
    type:'bar',y:fLabels.slice().reverse(),x:fValues.slice().reverse(),orientation:'h',
    marker:{{color:fLabels.slice().reverse().map(l=>fColors[l])}},
    text:fValues.slice().reverse(),textposition:'outside',textfont:{{color:'#9ca3af',size:12}},
  }}],{{...plotLayout,height:250,margin:{{t:10,b:20,l:200,r:60}},xaxis:{{gridcolor:'#2a2d3a'}},yaxis:{{tickfont:{{size:12,color:'#e4e4e7'}}}}}},{{responsive:true}});
}}

// Brand voice
if (ENH.brand) {{
  document.getElementById('enh-brand').style.display = '';
  document.getElementById('brand-avg').textContent = ENH.brand.avg_score;
  const bLabels=Object.keys(ENH.brand.distribution),bValues=Object.values(ENH.brand.distribution);
  const bColors={{'On-brand':'#22c55e','Partially aligned':'#eab308','Needs work':'#f97316','Off-brand':'#ef4444'}};
  Plotly.newPlot('brand-chart',[{{
    type:'pie',labels:bLabels,values:bValues,hole:0.5,textinfo:'label+percent',
    marker:{{colors:bLabels.map(l=>bColors[l]||'#6b7280')}},textfont:{{size:12}},
  }}],{{...plotLayout,height:300,showlegend:false,margin:{{t:10,b:10,l:10,r:10}}}},{{responsive:true}});
  const bTbody=document.querySelector('#brand-table tbody');
  bTbody.innerHTML=ENH.brand.bottom.map(b=>`<tr>
    <td style="font-size:12px">${{b.url.replace('https://azariangrowthagency.com/','/')}}</td>
    <td style="font-weight:700;color:${{b.brand_score<25?'#ef4444':b.brand_score<50?'#f97316':'#eab308'}}">${{b.brand_score}}</td>
    <td><span class="badge ${{b.rating==='Off-brand'?'badge-red':b.rating==='Needs work'?'badge-yellow':'badge-blue'}}">${{b.rating}}</span></td>
    <td style="font-size:11px;color:var(--muted)">${{b.tone_matches||'none'}}</td>
    <td style="font-size:11px;color:var(--muted)">${{b.violations||'none'}}</td>
  </tr>`).join('');
}}

// Cluster merges
if (ENH.merges) {{
  document.getElementById('enh-merges').style.display = '';
  const mTbody=document.querySelector('#merge-table tbody');
  mTbody.innerHTML=ENH.merges.map(m=>`<tr>
    <td>${{m.cluster_a_name}}</td><td>${{m.cluster_b_name}}</td>
    <td style="color:${{m.similarity>=0.85?'#ef4444':'#eab308'}};font-weight:700">${{(m.similarity*100).toFixed(0)}}%</td>
    <td><span class="badge ${{m.recommendation==='MERGE'?'badge-red':'badge-yellow'}}">${{m.recommendation}}</span></td>
  </tr>`).join('');
}}
</script>
</body>
</html>"""


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    path = generate_dashboard()
    print(f"Dashboard: {path}")
