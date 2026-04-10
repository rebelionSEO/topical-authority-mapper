"""Generate a professional PDF report matching the technical SEO audit style."""

import logging
import os
from datetime import datetime

import pandas as pd

from src.config import OUTPUT_DIR

logger = logging.getLogger(__name__)


def _classify_thin(url):
    u = url.lower()
    if any(p in u for p in ["content-marketing-tools/", "marketing-tools/", "ai-tool"]):
        return "Tool Review"
    if any(p in u for p in ["seo-services", "digital-marketing", "web-design", "los-angeles",
                             "orange-county", "california", "beach", "irvine", "corona",
                             "fullerton", "cerritos", "ontario", "riverside", "brea",
                             "costa-mesa", "huntington", "aliso-viejo", "anaheim"]):
        return "Local Landing Page"
    return "Other"


def generate_pdf():
    """Generate the topical authority audit PDF report."""
    clusters = pd.read_csv(os.path.join(OUTPUT_DIR, "clusters.csv"))
    url_map = pd.read_csv(os.path.join(OUTPUT_DIR, "url_mapping.csv"))
    cannib = pd.read_csv(os.path.join(OUTPUT_DIR, "cannibalization.csv"))
    skipped = pd.read_csv(os.path.join(OUTPUT_DIR, "skipped_urls.csv"))
    recs_path = os.path.join(OUTPUT_DIR, "recommendations.csv")
    recs = pd.read_csv(recs_path) if os.path.exists(recs_path) else pd.DataFrame()

    # Compute data
    cluster_sizes = url_map[url_map["main_cluster"] != -1].groupby("main_cluster").size().reset_index(name="url_count")
    cluster_sizes = cluster_sizes.merge(clusters, left_on="main_cluster", right_on="cluster_id", how="inner")
    cluster_sizes = cluster_sizes.sort_values("url_count", ascending=False)

    cannib_full = cannib[cannib["cluster_id"] != -1].sort_values("url_count", ascending=False)
    noise_count = len(url_map[url_map["main_cluster"] == -1])

    thin = skipped[skipped["reason"].str.contains("thin", na=False)].copy()
    thin["category"] = thin["url"].apply(_classify_thin)
    thin["word_count"] = thin["reason"].str.extract(r"(\d+)").astype(float).fillna(0).astype(int)

    content_types = {}
    if not recs.empty and "content_type" in recs.columns:
        content_types = recs["content_type"].value_counts().to_dict()

    thin_tools = thin[thin["category"] == "Tool Review"]
    thin_local = thin[thin["category"] == "Local Landing Page"]
    thin_other = thin[thin["category"] == "Other"]

    total_urls = len(url_map)
    total_clusters = len(clusters)
    total_cannib = len(cannib_full)
    total_skipped = len(skipped)
    critical_cannib = cannib_full[cannib_full["url_count"] >= 10]
    high_cannib = cannib_full[(cannib_full["url_count"] >= 6) & (cannib_full["url_count"] < 10)]

    # Build HTML for PDF
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
@page {{ size: A4; margin: 60px 50px 60px 50px; }}
@media print {{ .page-break {{ page-break-before: always; }} }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif;
       color: #1f2937; font-size: 11px; line-height: 1.6; }}

/* Cover */
.cover {{ text-align: center; padding: 120px 0 60px; }}
.cover h1 {{ font-size: 32px; font-weight: 800; color: #111827; letter-spacing: -0.5px; }}
.cover .sub {{ font-size: 16px; color: #4A7BF7; font-weight: 500; margin-top: 4px; }}
.cover .domain {{ font-size: 14px; color: #6b7280; margin-top: 8px; }}
.cover-line {{ height: 3px; width: 80px; background: #4A7BF7; margin: 30px auto; }}
.cover .meta {{ font-size: 12px; color: #9ca3af; margin-top: 20px; line-height: 1.8; }}
.cover .conf {{ font-size: 11px; color: #9ca3af; font-style: italic; margin-top: 40px; }}

/* Section headers */
h2 {{ font-size: 18px; font-weight: 700; color: #111827; margin: 28px 0 12px; padding-bottom: 6px; border-bottom: 2px solid #4A7BF7; }}
h3 {{ font-size: 14px; font-weight: 700; color: #4A7BF7; margin: 20px 0 8px; }}
h4 {{ font-size: 12px; font-weight: 600; color: #374151; margin: 14px 0 6px; }}
p {{ margin: 6px 0; }}

/* Tables */
table {{ width: 100%; border-collapse: collapse; font-size: 10.5px; margin: 10px 0 16px; }}
th {{ text-align: left; padding: 8px 10px; background: #f3f4f6; font-weight: 600; color: #374151;
     border-bottom: 2px solid #e5e7eb; font-size: 10px; text-transform: uppercase; letter-spacing: 0.3px; }}
td {{ padding: 7px 10px; border-bottom: 1px solid #f3f4f6; vertical-align: top; }}
tr:nth-child(even) td {{ background: #fafafa; }}

/* Status labels */
.status {{ font-weight: 700; font-size: 10px; }}
.critical {{ color: #dc2626; }}
.warning {{ color: #d97706; }}
.ok {{ color: #16a34a; }}
.info {{ color: #4A7BF7; }}

/* Key numbers */
.key-numbers {{ display: flex; gap: 16px; margin: 16px 0 20px; }}
.key-num {{ flex: 1; text-align: center; border: 1px solid #e5e7eb; border-radius: 6px; padding: 14px 8px; }}
.key-num .val {{ font-size: 24px; font-weight: 800; }}
.key-num .val.red {{ color: #dc2626; }}
.key-num .val.yellow {{ color: #d97706; }}
.key-num .val.blue {{ color: #4A7BF7; }}
.key-num .val.gray {{ color: #6b7280; }}
.key-num .lbl {{ font-size: 9px; color: #9ca3af; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 2px; }}

/* Issue blocks */
.issue {{ margin: 16px 0; padding: 14px 16px; background: #fafafa; border-left: 3px solid #4A7BF7; border-radius: 0 6px 6px 0; }}
.issue.critical-issue {{ border-left-color: #dc2626; }}
.issue.warning-issue {{ border-left-color: #d97706; }}
.issue h4 {{ margin: 0 0 6px; color: #111827; }}
.issue p {{ margin: 4px 0; font-size: 11px; }}
.issue .label {{ font-size: 10px; font-weight: 600; color: #6b7280; }}

/* URL list */
.url-list {{ font-size: 10px; color: #4A7BF7; margin: 4px 0; }}
.url-list span {{ display: block; padding: 2px 0; color: #374151; }}

/* Recommendation box */
.rec-box {{ background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 6px; padding: 12px 14px; margin: 10px 0; }}
.rec-box p {{ font-size: 11px; margin: 3px 0; }}
.rec-box strong {{ color: #1e40af; }}

/* Action items */
.action {{ margin: 8px 0; padding: 10px 14px; background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 6px; }}
.action p {{ margin: 3px 0; font-size: 11px; }}
.action .priority {{ font-size: 10px; font-weight: 700; }}
.action .priority.p1 {{ color: #dc2626; }}
.action .priority.p2 {{ color: #d97706; }}
.action .priority.p3 {{ color: #4A7BF7; }}
</style></head><body>

<!-- COVER PAGE -->
<div class="cover">
  <h1>TOPICAL AUTHORITY AUDIT</h1>
  <div class="sub">EXECUTIVE SUMMARY</div>
  <div class="domain">azariangrowthagency.com</div>
  <div class="cover-line"></div>
  <div class="meta">
    Prepared by: Azarian Growth Agency<br>
    Date: April 2026<br>
    Source: Topical Authority Mapper | {total_urls} Pages Analyzed
  </div>
  <div class="conf">CONFIDENTIAL</div>
</div>

<div class="page-break"></div>

<!-- EXECUTIVE OVERVIEW -->
<h2>Executive Overview</h2>
<p>This audit analyzed <strong>{total_urls} pages</strong> on azariangrowthagency.com using AI-powered semantic
analysis (sentence-transformer embeddings + UMAP/HDBSCAN clustering). The site has strong topical breadth across
core verticals aligned with Azarian's 8 ICPs. However, <strong>significant content cannibalization</strong> and
<strong>thin content issues</strong> are actively diluting ranking potential, wasting crawl budget, and splitting
authority across competing pages.</p>

<!-- SCORECARD -->
<h3>Audit Scorecard</h3>
<table>
  <thead><tr><th>Area</th><th>Status</th><th>Issues</th><th>Impact Level</th></tr></thead>
  <tbody>
    <tr><td>Topic Coverage (Breadth)</td><td><span class="status ok">Strong</span></td><td>{total_clusters} clusters</td><td>Good coverage across core verticals and ICPs</td></tr>
    <tr><td>Content Cannibalization</td><td><span class="status critical">Critical</span></td><td>{total_cannib} clusters</td><td>Diluted ranking signals, split authority</td></tr>
    <tr><td>Thin Content</td><td><span class="status warning">Needs Fix</span></td><td>{total_skipped} pages</td><td>Wasted crawl budget, no ranking potential</td></tr>
    <tr><td>Unclustered / Orphan Pages</td><td><span class="status warning">Needs Fix</span></td><td>{noise_count} pages</td><td>Off-topic or isolated content</td></tr>
    <tr><td>Content Type Balance</td><td><span class="status info">Review</span></td><td>69% educational</td><td>Low on comparison and how-to content</td></tr>
    <tr><td>ICP Alignment</td><td><span class="status ok">Strong</span></td><td>8 verticals active</td><td>Legal, PE, Fintech, SaaS, Home Services aligned</td></tr>
  </tbody>
</table>

<!-- KEY NUMBERS -->
<h3>Key Numbers</h3>
<div class="key-numbers">
  <div class="key-num"><div class="val blue">{total_clusters}</div><div class="lbl">Topic Clusters</div></div>
  <div class="key-num"><div class="val red">{total_cannib}</div><div class="lbl">Cannibalization Flags</div></div>
  <div class="key-num"><div class="val yellow">{total_skipped}</div><div class="lbl">Thin / Skipped Pages</div></div>
  <div class="key-num"><div class="val gray">{noise_count}</div><div class="lbl">Unclustered Pages</div></div>
</div>

<div class="page-break"></div>

<!-- CRITICAL ISSUES -->
<h2>Critical Issues &mdash; Direct Ranking Impact</h2>
<p>These issues are actively degrading search performance and topical authority. Prioritize immediate resolution.</p>

<div class="issue critical-issue">
  <h4>C-001: Severe Content Cannibalization ({total_cannib} clusters affected)</h4>
  <p><span class="label">Problem:</span> {total_cannib} of {total_clusters} topic clusters have multiple URLs competing
  for the same keywords. {len(critical_cannib)} clusters have 10+ competing pages. The top offenders:</p>
  <table>
    <thead><tr><th>Cluster</th><th>Competing URLs</th><th>Severity</th></tr></thead>
    <tbody>"""

    for _, row in cannib_full.head(15).iterrows():
        severity = "Critical" if row["url_count"] >= 10 else "High" if row["url_count"] >= 6 else "Moderate"
        sclass = "critical" if severity == "Critical" else "warning" if severity == "High" else "info"
        html += f"""
      <tr><td>{row['cluster_name']}</td><td>{int(row['url_count'])}</td><td><span class="status {sclass}">{severity}</span></td></tr>"""

    html += f"""
    </tbody>
  </table>
  <p><span class="label">Fix:</span> Audit each cannibalized cluster. For each, identify the strongest performing URL
  (by traffic, backlinks, conversions) and consolidate the rest via 301 redirects or content merges.
  Differentiate remaining pages with unique angles, keywords, and search intent.</p>
  <p><span class="label">Growth Impact:</span> Consolidated authority on pillar pages improves rankings, reduces
  crawl waste, and concentrates link equity. Expected 10-25% ranking improvement on affected keywords.</p>
  <p><span class="label">Effort:</span> High | 4-6 weeks (phased by cluster priority)</p>
</div>

<div class="issue critical-issue">
  <h4>C-002: Thin Content Pages ({len(thin)} pages under 300 words)</h4>
  <p><span class="label">Problem:</span> {len(thin)} pages have insufficient content to rank or contribute to topical authority:</p>
  <table>
    <thead><tr><th>Category</th><th>Count</th><th>Avg Words</th><th>Issue</th></tr></thead>
    <tbody>
      <tr><td>Tool Review Pages</td><td>{len(thin_tools)}</td><td>{int(thin_tools['word_count'].mean()) if len(thin_tools) > 0 else 0}</td><td>Short descriptions, no depth</td></tr>
      <tr><td>Local/City Landing Pages</td><td>{len(thin_local)}</td><td>{int(thin_local['word_count'].mean()) if len(thin_local) > 0 else 0}</td><td>Stubs with no unique content</td></tr>
      <tr><td>Other (Case Studies, Hubs)</td><td>{len(thin_other)}</td><td>{int(thin_other['word_count'].mean()) if len(thin_other) > 0 else 0}</td><td>Missing substantive content</td></tr>
    </tbody>
  </table>
  <p><span class="label">Fix:</span> Expand high-value thin pages to 500+ words with unique content. For low-value pages,
  either noindex or consolidate into parent topics. Prioritize local landing pages that serve geo-targeting.</p>
  <p><span class="label">Growth Impact:</span> Removes crawl budget waste. Expanded pages gain ranking eligibility.
  Improved topical depth signals for Google and AI search engines.</p>
  <p><span class="label">Effort:</span> Medium | 3-4 weeks</p>
</div>

<div class="issue warning-issue">
  <h4>C-003: Orphan / Unclustered Pages ({noise_count} pages)</h4>
  <p><span class="label">Problem:</span> {noise_count} pages don't semantically cluster with any topic on the site.
  These are either off-topic, too unique to support with surrounding content, or mixed-intent pages that
  confuse clustering algorithms &mdash; and likely confuse Google too.</p>
  <p><span class="label">Fix:</span> Review each orphan page. Either: (a) create supporting content to build a cluster around it,
  (b) merge it into an existing related cluster, or (c) noindex if it serves no organic purpose.</p>
  <p><span class="label">Effort:</span> Low-Medium | 1-2 weeks</p>
</div>

<div class="page-break"></div>

<!-- TOP CLUSTERS -->
<h2>Top 25 Topic Clusters</h2>
<p>Clusters ranked by number of pages. Larger clusters indicate areas of topical investment.</p>
<table>
  <thead><tr><th>#</th><th>Cluster Name</th><th>Pages</th><th>Top Keywords</th><th>Cannibalized?</th></tr></thead>
  <tbody>"""

    for i, (_, row) in enumerate(cluster_sizes.head(25).iterrows(), 1):
        is_cannib = int(row["cluster_id"]) in cannib["cluster_id"].values
        kws = ", ".join(row["keywords"].split(", ")[:5])
        html += f"""
    <tr><td>{i}</td><td><strong>{row['cluster_name']}</strong></td><td>{int(row['url_count'])}</td>
    <td style="font-size:10px;color:#6b7280">{kws}</td>
    <td>{'<span class="status critical">Yes</span>' if is_cannib else '<span class="status ok">No</span>'}</td></tr>"""

    html += """
  </tbody>
</table>

<div class="page-break"></div>"""

    # CANNIBALIZATION DETAIL
    html += """
<h2>Cannibalization Detail &mdash; Affected URLs</h2>
<p>Each cannibalized cluster with all competing URLs listed. Sorted by severity.</p>"""

    for _, row in cannib_full.head(20).iterrows():
        urls = str(row["urls"]).split(" | ")
        severity = "Critical" if row["url_count"] >= 10 else "High" if row["url_count"] >= 6 else "Moderate"
        sclass = "critical-issue" if severity == "Critical" else "warning-issue" if severity == "High" else ""
        html += f"""
<div class="issue {sclass}">
  <h4>{row['cluster_name']} &mdash; {int(row['url_count'])} competing URLs <span class="status {'critical' if severity=='Critical' else 'warning'}">[{severity}]</span></h4>
  <div class="url-list">"""
        for u in urls:
            slug = u.replace("https://azariangrowthagency.com/", "/")
            html += f"""<span>{slug}</span>"""
        html += f"""</div>
  <p style="font-size:10px;color:#6b7280;margin-top:6px"><em>{row['recommendation']}</em></p>
</div>"""

    html += '<div class="page-break"></div>'

    # THIN CONTENT DETAIL
    html += """
<h2>Thin Content &mdash; Pages Needing Action</h2>
<p>All pages under 300 words, grouped by category with specific recommendations.</p>"""

    for cat_name, cat_df in [("Tool Review Pages", thin_tools), ("Local/City Landing Pages", thin_local), ("Other Thin Pages", thin_other)]:
        if len(cat_df) == 0:
            continue
        html += f"""
<h3>{cat_name} ({len(cat_df)} pages)</h3>
<table>
  <thead><tr><th>URL</th><th>Words</th><th>Recommendation</th></tr></thead>
  <tbody>"""
        for _, r in cat_df.iterrows():
            slug = r["url"].replace("https://azariangrowthagency.com/", "/")
            if cat_name == "Tool Review Pages":
                rec = "Expand to 500+ words: use cases, pricing, pros/cons, comparison"
            elif cat_name == "Local/City Landing Pages":
                rec = "Add local case studies, testimonials, service area content"
            else:
                if "case-stud" in r["url"]:
                    rec = "Add full case study: challenge, strategy, results with metrics"
                elif "industr" in r["url"]:
                    rec = "Build as industry pillar: pain points, services, case studies"
                elif "guide" in r["url"]:
                    rec = "Expand into comprehensive resource hub"
                else:
                    rec = "Expand with content or consolidate into related pillar page"
            html += f"""
    <tr><td style="font-size:10px;color:#4A7BF7">{slug}</td>
    <td style="color:#dc2626;font-weight:600;text-align:center">{int(r['word_count'])}</td>
    <td style="font-size:10px">{rec}</td></tr>"""
        html += """
  </tbody>
</table>"""

    html += '<div class="page-break"></div>'

    # CONTENT TYPE DISTRIBUTION
    html += """
<h2>Content Type Distribution</h2>
<p>Recommended content formats based on cluster keyword analysis and brand voice alignment.</p>
<table>
  <thead><tr><th>Content Type</th><th>Clusters</th><th>% of Total</th></tr></thead>
  <tbody>"""
    for ct, count in content_types.items():
        pct = round(count / total_clusters * 100, 1)
        html += f"""
    <tr><td>{ct}</td><td>{count}</td><td>{pct}%</td></tr>"""
    html += """
  </tbody>
</table>

<div class="rec-box">
  <p><strong>Gap Identified:</strong> Only 1 comparison page and 3 how-to guides across 195 clusters.
  These content types dominate featured snippets and AI answer citations. Recommend creating
  comparison and how-to content for top 10 revenue-driving clusters.</p>
</div>"""

    html += '<div class="page-break"></div>'

    # Load enhancement CSVs
    def _load_enh(name):
        p = os.path.join(OUTPUT_DIR, name)
        return pd.read_csv(p) if os.path.exists(p) else pd.DataFrame()

    comp_df = _load_enh("competitor_topic_comparison.csv")
    sim_df = _load_enh("similarity_scores.csv")
    if not sim_df.empty:
        sim_df = sim_df[sim_df["similarity"] >= 0.80].sort_values("similarity", ascending=False).head(25)
    fresh_df = _load_enh("content_freshness.csv")
    brand_enh = _load_enh("brand_voice_scores.csv")
    merge_enh = _load_enh("cluster_merge_suggestions.csv")
    if not merge_enh.empty:
        merge_enh = merge_enh.head(20)

    # COMPETITOR GAP ANALYSIS
    if not comp_df.empty:
        gaps = comp_df[comp_df["status"] == "GAP"]
        advs = comp_df[comp_df["status"] == "Azarian advantage"]
        shared = comp_df[comp_df["status"].str.contains("cover|overlap", na=False)]
        html += f"""
<h2>Competitor Gap Analysis</h2>
<p>Topic cluster comparison between Azarian Growth Agency, NoGood.io, and SingleGrain.com.
Analysis based on crawl data from both competitor sites mapped into topic clusters.</p>

<table>
  <thead><tr><th>Metric</th><th>Count</th><th>Impact</th></tr></thead>
  <tbody>
    <tr><td>Azarian-only topics</td><td><span class="status ok">{len(advs)}</span></td><td>Strong competitive moat — protect and deepen these</td></tr>
    <tr><td>Shared topics (all cover)</td><td><span class="status info">{len(shared)}</span></td><td>Table stakes — ensure superior depth and quality</td></tr>
    <tr><td>Content gaps (competitors cover, Azarian doesn't)</td><td><span class="status critical">{len(gaps)}</span></td><td>Missing opportunities — evaluate for strategic fit</td></tr>
  </tbody>
</table>

<h3>Key Content Gaps</h3>
<table>
  <thead><tr><th>Topic</th><th>Covered By</th></tr></thead>
  <tbody>"""
        for _, r in gaps.head(20).iterrows():
            covered = []
            if r.get("nogood") == "Y": covered.append("NoGood")
            if r.get("singlegrain") == "Y": covered.append("SingleGrain")
            html += f"""
    <tr><td>{r['topic']}</td><td>{', '.join(covered)}</td></tr>"""
        html += """
  </tbody>
</table>

<div class="rec-box">
  <p><strong>Priority Gaps to Address:</strong> YouTube/video marketing, Instagram/TikTok content,
  healthcare vertical, enterprise ABM/SEO, influencer marketing, and Reddit/community strategies.
  These represent high-search-volume topics where competitors are capturing traffic Azarian is not.</p>
</div>"""
        html += '<div class="page-break"></div>'

    # NEAR-DUPLICATE PAGES
    if not sim_df.empty:
        html += """
<h2>Near-Duplicate Pages</h2>
<p>URL pairs with 80%+ content similarity identified via cosine similarity of page embeddings.
These pages are competing against each other and should be merged or differentiated.</p>
<table>
  <thead><tr><th>URL A</th><th>URL B</th><th>Similarity</th><th>Action</th></tr></thead>
  <tbody>"""
        for _, r in sim_df.iterrows():
            slug_a = r["url_a"].replace("https://azariangrowthagency.com/", "/")
            slug_b = r["url_b"].replace("https://azariangrowthagency.com/", "/")
            color = "critical" if r["similarity"] >= 0.92 else "warning"
            html += f"""
    <tr><td style="font-size:10px;color:#4A7BF7">{slug_a}</td>
    <td style="font-size:10px;color:#4A7BF7">{slug_b}</td>
    <td><span class="status {color}">{r['similarity']:.0%}</span></td>
    <td style="font-size:10px">{r['action']}</td></tr>"""
        html += """
  </tbody>
</table>"""
        html += '<div class="page-break"></div>'

    # CONTENT FRESHNESS
    if not fresh_df.empty:
        fresh_counts = fresh_df["freshness"].value_counts()
        total_fresh = len(fresh_df)
        html += f"""
<h2>Content Freshness Analysis</h2>
<p>Content age based on sitemap lastmod dates across {total_fresh} URLs.</p>
<table>
  <thead><tr><th>Freshness</th><th>Pages</th><th>% of Total</th><th>Status</th></tr></thead>
  <tbody>"""
        order = ["Fresh (< 1 month)", "Recent (1-3 months)", "Aging (3-6 months)", "Stale (6-12 months)", "Decaying (12+ months)"]
        status_map = {"Fresh (< 1 month)": "ok", "Recent (1-3 months)": "ok", "Aging (3-6 months)": "warning", "Stale (6-12 months)": "critical", "Decaying (12+ months)": "critical"}
        for cat in order:
            count = fresh_counts.get(cat, 0)
            pct = round(count / total_fresh * 100, 1) if total_fresh > 0 else 0
            html += f"""
    <tr><td>{cat}</td><td>{count}</td><td>{pct}%</td><td><span class="status {status_map[cat]}">{status_map[cat].title()}</span></td></tr>"""
        stale_pct = round((fresh_counts.get("Stale (6-12 months)", 0) + fresh_counts.get("Decaying (12+ months)", 0)) / total_fresh * 100) if total_fresh > 0 else 0
        html += f"""
  </tbody>
</table>
<div class="rec-box">
  <p><strong>Critical Finding:</strong> {stale_pct}% of content is 6+ months old. Content decay directly impacts
  rankings as Google favors freshness signals. Establish a quarterly content refresh cadence targeting
  highest-traffic stale pages first.</p>
</div>"""

    # BRAND VOICE
    if not brand_enh.empty:
        brand_counts = brand_enh["rating"].value_counts()
        avg_score = round(brand_enh["brand_score"].mean(), 1)
        html += f"""
<h3>Brand Voice Alignment</h3>
<p>Each page scored against Azarian's brand voice profile (tone, style, do/don't rules). Average score: <strong>{avg_score}/100</strong>.</p>
<table>
  <thead><tr><th>Rating</th><th>Pages</th><th>% of Total</th></tr></thead>
  <tbody>"""
        for rating in ["On-brand", "Partially aligned", "Needs work", "Off-brand"]:
            count = brand_counts.get(rating, 0)
            pct = round(count / len(brand_enh) * 100, 1)
            html += f"""
    <tr><td>{rating}</td><td>{count}</td><td>{pct}%</td></tr>"""
        html += """
  </tbody>
</table>"""

    # CLUSTER MERGES
    if not merge_enh.empty:
        html += """
<h3>Cluster Merge Opportunities</h3>
<p>Clusters with high semantic overlap that should be combined to concentrate topical authority.</p>
<table>
  <thead><tr><th>Cluster A</th><th>Cluster B</th><th>Similarity</th><th>Recommendation</th></tr></thead>
  <tbody>"""
        for _, r in merge_enh.iterrows():
            color = "critical" if r["recommendation"] == "MERGE" else "warning"
            html += f"""
    <tr><td>{r['cluster_a_name']}</td><td>{r['cluster_b_name']}</td>
    <td><span class="status {color}">{r['similarity']:.0%}</span></td>
    <td>{r['recommendation']}</td></tr>"""
        html += """
  </tbody>
</table>"""

    html += '<div class="page-break"></div>'

    # CAMPAIGN BRIEFS
    html += """
<h2>Campaign Briefs &mdash; Growth Opportunities</h2>
<p>The following campaigns are derived directly from audit findings where fixes unlock measurable growth.</p>

<h3>Campaign 1: Cannibalization Consolidation Sprint</h3>
<table>
  <thead><tr><th>Field</th><th>Detail</th></tr></thead>
  <tbody>
    <tr><td><strong>Objective</strong></td><td>Consolidate competing pages into authoritative pillar content for each topic cluster</td></tr>
    <tr><td><strong>Trigger</strong></td><td>C-001: """ + str(total_cannib) + """ clusters with multiple URLs competing for the same keywords</td></tr>
    <tr><td><strong>Scope</strong></td><td>Phase 1: """ + str(len(critical_cannib)) + """ critical clusters (10+ URLs). Phase 2: """ + str(len(high_cannib)) + """ high-priority clusters (6-9 URLs). Phase 3: Remaining moderate clusters.</td></tr>
    <tr><td><strong>Execution</strong></td><td>For each cluster: identify strongest URL by traffic + backlinks. Merge content from weaker pages. 301 redirect merged pages. Update internal links. Differentiate any pages kept with unique search intent.</td></tr>
    <tr><td><strong>Success Metrics</strong></td><td>Zero duplicate-intent pages per cluster. Improved avg position for target keywords. Increased organic CTR on consolidated pages.</td></tr>
    <tr><td><strong>Growth Forecast</strong></td><td>10-25% ranking improvement on affected keywords. Concentrated link equity. Cleaner crawl signals. Improved AI citation rates.</td></tr>
    <tr><td><strong>Timeline</strong></td><td>4-6 weeks. Phase 1 in Week 1-2 (highest ROI). Phase 2 in Week 3-4. Phase 3 ongoing.</td></tr>
  </tbody>
</table>

<h3>Campaign 2: Thin Content Expansion & Cleanup</h3>
<table>
  <thead><tr><th>Field</th><th>Detail</th></tr></thead>
  <tbody>
    <tr><td><strong>Objective</strong></td><td>Expand high-value thin pages to ranking eligibility or remove low-value pages from the index</td></tr>
    <tr><td><strong>Trigger</strong></td><td>C-002: """ + str(len(thin)) + """ pages under 300 words consuming crawl budget without ranking</td></tr>
    <tr><td><strong>Scope</strong></td><td>Phase 1: """ + str(len(thin_local)) + """ local landing pages (geo-targeting value). Phase 2: """ + str(len(thin_tools)) + """ tool review pages. Phase 3: """ + str(len(thin_other)) + """ hub/guide pages.</td></tr>
    <tr><td><strong>Execution</strong></td><td>Phase 1: Expand local pages with city-specific content, testimonials, service details (500+ words each). Phase 2: Enrich tool pages with use cases, pricing, comparisons. Phase 3: Build out case studies and industry hubs. Noindex pages that cannot be expanded.</td></tr>
    <tr><td><strong>Success Metrics</strong></td><td>Zero pages under 300 words in the index. Local pages ranking for geo-modified keywords. Tool pages capturing comparison search intent.</td></tr>
    <tr><td><strong>Growth Forecast</strong></td><td>Recovered crawl budget. New ranking eligibility for 100+ pages. Improved topical depth signals across all clusters.</td></tr>
    <tr><td><strong>Timeline</strong></td><td>3-4 weeks. Phase 1 in Week 1 (highest geo-targeting ROI). Phase 2 in Week 2-3. Phase 3 in Week 3-4.</td></tr>
  </tbody>
</table>

<h3>Campaign 3: Content Type Diversification</h3>
<table>
  <thead><tr><th>Field</th><th>Detail</th></tr></thead>
  <tbody>
    <tr><td><strong>Objective</strong></td><td>Create comparison pages and how-to guides for top revenue clusters to capture featured snippets and AI citations</td></tr>
    <tr><td><strong>Trigger</strong></td><td>Content type gap: 69% educational content, only 1 comparison page and 3 how-to guides</td></tr>
    <tr><td><strong>Scope</strong></td><td>10 comparison pages + 10 how-to guides targeting top clusters (PPC, SaaS, Fintech, Legal, CRO, Growth Marketing, Facebook Ads, Link Building, Email Marketing, Local SEO)</td></tr>
    <tr><td><strong>Execution</strong></td><td>Research SERP features for each cluster's top keywords. Create content matching the dominant SERP format. Optimize for featured snippets (tables, lists, step-by-step). Structure for AI parsability (schema, clear headings, concise answers).</td></tr>
    <tr><td><strong>Success Metrics</strong></td><td>Featured snippet capture for 5+ target keywords. AI citation appearances in ChatGPT/Perplexity for core service queries.</td></tr>
    <tr><td><strong>Growth Forecast</strong></td><td>Featured snippets drive 2-3x CTR vs standard results. AI citations build brand authority in zero-click environments.</td></tr>
    <tr><td><strong>Timeline</strong></td><td>4 weeks. 5 pieces per week.</td></tr>
  </tbody>
</table>"""

    html += '<div class="page-break"></div>'

    # ACTION ITEMS
    html += """
<h2>Recommended Execution Order</h2>
<p>Based on growth impact relative to effort, here is the recommended sequence:</p>
<table>
  <thead><tr><th>Order</th><th>Action</th><th>Campaign</th><th>Effort</th><th>Timeline</th><th>Impact</th></tr></thead>
  <tbody>
    <tr><td>1</td><td>Consolidate top 10 cannibalized clusters (10+ URLs each)</td><td>Campaign 1 P1</td><td>High</td><td>2 weeks</td><td><span class="status critical">High</span></td></tr>
    <tr><td>2</td><td>Expand local/city landing pages (geo-targeting)</td><td>Campaign 2 P1</td><td>Medium</td><td>1 week</td><td><span class="status critical">High</span></td></tr>
    <tr><td>3</td><td>Create 10 comparison pages for top clusters</td><td>Campaign 3 P1</td><td>Medium</td><td>2 weeks</td><td><span class="status critical">High</span></td></tr>
    <tr><td>4</td><td>Consolidate remaining cannibalized clusters (6-9 URLs)</td><td>Campaign 1 P2</td><td>Medium</td><td>2 weeks</td><td><span class="status warning">Medium</span></td></tr>
    <tr><td>5</td><td>Expand tool review pages to 500+ words</td><td>Campaign 2 P2</td><td>Medium</td><td>2 weeks</td><td><span class="status warning">Medium</span></td></tr>
    <tr><td>6</td><td>Create 10 how-to guides for top clusters</td><td>Campaign 3 P2</td><td>Medium</td><td>2 weeks</td><td><span class="status warning">Medium</span></td></tr>
    <tr><td>7</td><td>Review and resolve orphan pages</td><td>Maintenance</td><td>Low</td><td>1 week</td><td><span class="status info">Low</span></td></tr>
    <tr><td>8</td><td>Build out case study and industry hub pages</td><td>Campaign 2 P3</td><td>Medium</td><td>2 weeks</td><td><span class="status warning">Medium</span></td></tr>
  </tbody>
</table>
<p>Steps 1-3 represent the highest ROI actions and should be executed in the first 4 weeks.</p>"""

    html += '<div class="page-break"></div>'

    # CONCLUSIONS
    html += f"""
<h2>Conclusions</h2>
<p>The topical foundation of azariangrowthagency.com is <strong>strong in breadth but fragmented in depth</strong>.
With {total_clusters} topic clusters across {total_urls} pages, the site covers its core verticals well &mdash;
Legal, Private Equity, Fintech, SaaS, Home Services, and Growth Marketing all have meaningful content presence
aligned with Azarian's 8 ICPs.</p>

<p>However, three structural issues are actively limiting organic performance:</p>

<p><strong>1. Content Cannibalization is the #1 priority.</strong> {total_cannib} clusters have multiple pages fighting
for the same keywords. The worst cases (Facebook Ads: 31 pages, Link Building: 29, Content Marketing: 24) are
splitting authority so broadly that no single page can rank effectively. Consolidation into pillar pages will
produce the fastest ranking improvements.</p>

<p><strong>2. Thin content is wasting crawl budget.</strong> {len(thin)} pages with under 300 words are being
crawled and indexed but have zero chance of ranking. The {len(thin_local)} local landing pages represent a missed
geo-targeting opportunity &mdash; expanding them is a quick win for local search visibility.</p>

<p><strong>3. Content type diversity is too narrow.</strong> 69% of content is educational/conversion hybrid.
The near-absence of comparison pages and how-to guides means Azarian is missing featured snippets, People Also Ask
results, and AI citation opportunities that competitors are capturing.</p>

<h3>What This Means for Growth</h3>
<p>Executing all three campaigns over the next 8-10 weeks will produce:</p>
<ul style="margin:8px 0 8px 20px;">
  <li><strong>Consolidated authority</strong> on pillar pages that rank higher and earn more backlinks</li>
  <li><strong>Recovered crawl budget</strong> from removing thin content waste</li>
  <li><strong>New ranking eligibility</strong> for 100+ expanded pages</li>
  <li><strong>Featured snippet capture</strong> through comparison and how-to content</li>
  <li><strong>Improved AI visibility</strong> (GEO/AEO) through cleaner topic signals and structured content</li>
</ul>

<p>The result is a site that <strong>ranks more clearly, earns more traffic per page, and is more visible</strong>
to the AI-powered search interfaces (ChatGPT, Perplexity, Gemini) that are increasingly driving discovery
for Azarian's PE, VC, and enterprise audience.</p>

<div class="rec-box" style="margin-top:20px;">
  <p><strong>Next Steps:</strong></p>
  <p>1. Review the interactive dashboard (dashboard.html) for drill-down into each cluster and URL</p>
  <p>2. Begin Campaign 1 Phase 1: audit and consolidate the top 10 cannibalized clusters</p>
  <p>3. Begin Campaign 2 Phase 1: expand local/city landing pages with unique content</p>
  <p>4. Schedule follow-up analysis in 8 weeks to measure consolidation impact</p>
</div>

</body></html>"""

    # Save HTML
    html_path = os.path.join(OUTPUT_DIR, "report.html")
    with open(html_path, "w") as f:
        f.write(html)

    # Convert to PDF using weasyprint or wkhtmltopdf
    pdf_path = os.path.join(OUTPUT_DIR, "Topical_Authority_Audit_AGA_April_2026.pdf")

    # Try wkhtmltopdf first (common on macOS)
    import subprocess
    try:
        result = subprocess.run(
            ["wkhtmltopdf", "--enable-local-file-access", "--page-size", "A4",
             "--margin-top", "15mm", "--margin-bottom", "15mm",
             "--margin-left", "12mm", "--margin-right", "12mm",
             html_path, pdf_path],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            logger.info("PDF generated with wkhtmltopdf: %s", pdf_path)
            return pdf_path
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback: try Chrome headless
    for chrome in ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                   "/Applications/Chromium.app/Contents/MacOS/Chromium"]:
        if os.path.exists(chrome):
            try:
                result = subprocess.run(
                    [chrome, "--headless", "--disable-gpu",
                     f"--print-to-pdf={pdf_path}",
                     "--no-margins",
                     f"file://{html_path}"],
                    capture_output=True, text=True, timeout=30
                )
                if os.path.exists(pdf_path):
                    logger.info("PDF generated with Chrome headless: %s", pdf_path)
                    return pdf_path
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue

    logger.warning("No PDF converter found. HTML report saved to: %s", html_path)
    logger.warning("Install wkhtmltopdf: brew install wkhtmltopdf")
    return html_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    path = generate_pdf()
    print(f"Report: {path}")
