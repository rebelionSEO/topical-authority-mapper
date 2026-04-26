"""Generate a professional PDF report from the topical authority analysis."""

import logging
import os
import re
from datetime import datetime

import pandas as pd

from src.config import SiteConfig, load_site_config, output_dir

logger = logging.getLogger(__name__)


_TOOL_HINTS = ("/tools/", "/tool/", "tool-review", "/marketing-tools/", "/ai-tools/")
_LOCAL_HINTS = ("/locations/", "/cities/", "-near-me", "/areas/")
_LOCAL_PATH_HINTS = ("services-for-", "services-in-", "marketing-for-", "design-for-", "agency-in-")


def _classify_thin(url: str) -> str:
    u = url.lower()
    if any(h in u for h in _TOOL_HINTS):
        return "Tool Review"
    if any(h in u for h in _LOCAL_HINTS) or any(h in u for h in _LOCAL_PATH_HINTS):
        return "Local Landing Page"
    return "Other"


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "site"


def _discover_competitor_csvs() -> list[tuple[str, pd.DataFrame]]:
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


def generate_pdf(site_config: SiteConfig | None = None):
    """Generate the topical authority audit PDF report."""
    if site_config is None:
        site_config = load_site_config() or SiteConfig(name="Site", domain="")

    site_name = site_config.name
    site_domain = site_config.domain or "(unknown domain)"

    out = output_dir()
    clusters = pd.read_csv(os.path.join(out, "clusters.csv"))
    url_map = pd.read_csv(os.path.join(out, "url_mapping.csv"))
    cannib = pd.read_csv(os.path.join(out, "cannibalization.csv"))
    skipped = pd.read_csv(os.path.join(out, "skipped_urls.csv"))
    recs_path = os.path.join(out, "recommendations.csv")
    recs = pd.read_csv(recs_path) if os.path.exists(recs_path) else pd.DataFrame()

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

    today = datetime.now().strftime("%B %Y")

    # Worst offenders summary text
    if not cannib_full.empty:
        worst_offenders = ", ".join(
            f"{row['cluster_name']} ({int(row['url_count'])})"
            for _, row in cannib_full.head(3).iterrows()
        )
    else:
        worst_offenders = "none detected"

    # Build HTML
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
@page {{ size: A4; margin: 60px 50px 60px 50px; }}
@media print {{ .page-break {{ page-break-before: always; }} }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif;
       color: #1f2937; font-size: 11px; line-height: 1.6; }}
.cover {{ text-align: center; padding: 120px 0 60px; }}
.cover h1 {{ font-size: 32px; font-weight: 800; color: #111827; letter-spacing: -0.5px; }}
.cover .sub {{ font-size: 16px; color: #4A7BF7; font-weight: 500; margin-top: 4px; }}
.cover .domain {{ font-size: 14px; color: #6b7280; margin-top: 8px; }}
.cover-line {{ height: 3px; width: 80px; background: #4A7BF7; margin: 30px auto; }}
.cover .meta {{ font-size: 12px; color: #9ca3af; margin-top: 20px; line-height: 1.8; }}
.cover .conf {{ font-size: 11px; color: #9ca3af; font-style: italic; margin-top: 40px; }}
h2 {{ font-size: 18px; font-weight: 700; color: #111827; margin: 28px 0 12px; padding-bottom: 6px; border-bottom: 2px solid #4A7BF7; }}
h3 {{ font-size: 14px; font-weight: 700; color: #4A7BF7; margin: 20px 0 8px; }}
h4 {{ font-size: 12px; font-weight: 600; color: #374151; margin: 14px 0 6px; }}
p {{ margin: 6px 0; }}
table {{ width: 100%; border-collapse: collapse; font-size: 10.5px; margin: 10px 0 16px; }}
th {{ text-align: left; padding: 8px 10px; background: #f3f4f6; font-weight: 600; color: #374151;
     border-bottom: 2px solid #e5e7eb; font-size: 10px; text-transform: uppercase; letter-spacing: 0.3px; }}
td {{ padding: 7px 10px; border-bottom: 1px solid #f3f4f6; vertical-align: top; }}
tr:nth-child(even) td {{ background: #fafafa; }}
.status {{ font-weight: 700; font-size: 10px; }}
.critical {{ color: #dc2626; }}
.warning {{ color: #d97706; }}
.ok {{ color: #16a34a; }}
.info {{ color: #4A7BF7; }}
.key-numbers {{ display: flex; gap: 16px; margin: 16px 0 20px; }}
.key-num {{ flex: 1; text-align: center; border: 1px solid #e5e7eb; border-radius: 6px; padding: 14px 8px; }}
.key-num .val {{ font-size: 24px; font-weight: 800; }}
.key-num .val.red {{ color: #dc2626; }}
.key-num .val.yellow {{ color: #d97706; }}
.key-num .val.blue {{ color: #4A7BF7; }}
.key-num .val.gray {{ color: #6b7280; }}
.key-num .lbl {{ font-size: 9px; color: #9ca3af; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 2px; }}
.issue {{ margin: 16px 0; padding: 14px 16px; background: #fafafa; border-left: 3px solid #4A7BF7; border-radius: 0 6px 6px 0; }}
.issue.critical-issue {{ border-left-color: #dc2626; }}
.issue.warning-issue {{ border-left-color: #d97706; }}
.issue h4 {{ margin: 0 0 6px; color: #111827; }}
.issue p {{ margin: 4px 0; font-size: 11px; }}
.issue .label {{ font-size: 10px; font-weight: 600; color: #6b7280; }}
.url-list {{ font-size: 10px; color: #4A7BF7; margin: 4px 0; }}
.url-list span {{ display: block; padding: 2px 0; color: #374151; }}
.rec-box {{ background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 6px; padding: 12px 14px; margin: 10px 0; }}
.rec-box p {{ font-size: 11px; margin: 3px 0; }}
.rec-box strong {{ color: #1e40af; }}
</style></head><body>

<div class="cover">
  <h1>TOPICAL AUTHORITY AUDIT</h1>
  <div class="sub">EXECUTIVE SUMMARY</div>
  <div class="domain">{site_domain}</div>
  <div class="cover-line"></div>
  <div class="meta">
    Site: {site_name}<br>
    Date: {today}<br>
    Source: Topical Authority Mapper | {total_urls} Pages Analyzed
  </div>
  <div class="conf">CONFIDENTIAL</div>
</div>

<div class="page-break"></div>

<h2>Executive Overview</h2>
<p>This audit analyzed <strong>{total_urls} pages</strong> on {site_domain} using AI-powered semantic
analysis (sentence-transformer embeddings + UMAP/HDBSCAN clustering). The pipeline mapped every page
into one of <strong>{total_clusters} topic clusters</strong>, then layered on cannibalization detection,
intent classification, freshness scoring, brand voice alignment, and competitor topic gap analysis.</p>

<p>The headline findings: <strong>{total_cannib} clusters show content cannibalization</strong>
(multiple URLs competing for the same keywords), <strong>{total_skipped} pages</strong> are flagged
as thin or non-rankable, and <strong>{noise_count} pages</strong> do not semantically attach to any topic.
Top cannibalization offenders: {worst_offenders}.</p>

<h3>Audit Scorecard</h3>
<table>
  <thead><tr><th>Area</th><th>Status</th><th>Issues</th><th>Impact Level</th></tr></thead>
  <tbody>
    <tr><td>Topic Coverage (Breadth)</td><td><span class="status {'ok' if total_clusters >= 20 else 'warning'}">{'Strong' if total_clusters >= 20 else 'Limited'}</span></td><td>{total_clusters} clusters</td><td>Site-wide topical breadth</td></tr>
    <tr><td>Content Cannibalization</td><td><span class="status {'critical' if total_cannib >= 10 else 'warning' if total_cannib > 0 else 'ok'}">{'Critical' if total_cannib >= 10 else 'Needs Fix' if total_cannib > 0 else 'Clean'}</span></td><td>{total_cannib} clusters</td><td>Diluted ranking signals, split authority</td></tr>
    <tr><td>Thin Content</td><td><span class="status {'warning' if total_skipped > 10 else 'ok'}">{'Needs Fix' if total_skipped > 10 else 'Acceptable'}</span></td><td>{total_skipped} pages</td><td>Wasted crawl budget, no ranking potential</td></tr>
    <tr><td>Unclustered / Orphan Pages</td><td><span class="status {'warning' if noise_count > 5 else 'ok'}">{'Needs Fix' if noise_count > 5 else 'Acceptable'}</span></td><td>{noise_count} pages</td><td>Off-topic or isolated content</td></tr>
  </tbody>
</table>

<h3>Key Numbers</h3>
<div class="key-numbers">
  <div class="key-num"><div class="val blue">{total_clusters}</div><div class="lbl">Topic Clusters</div></div>
  <div class="key-num"><div class="val red">{total_cannib}</div><div class="lbl">Cannibalization Flags</div></div>
  <div class="key-num"><div class="val yellow">{total_skipped}</div><div class="lbl">Thin / Skipped Pages</div></div>
  <div class="key-num"><div class="val gray">{noise_count}</div><div class="lbl">Unclustered Pages</div></div>
</div>

<div class="page-break"></div>

<h2>Critical Issues &mdash; Direct Ranking Impact</h2>
<p>These issues are actively degrading search performance and topical authority. Prioritize immediate resolution.</p>

<div class="issue critical-issue">
  <h4>C-001: Content Cannibalization ({total_cannib} clusters affected)</h4>
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

    html += """
    </tbody>
  </table>
  <p><span class="label">Fix:</span> Audit each cannibalized cluster. For each, identify the strongest performing URL
  (by traffic, backlinks, conversions) and consolidate the rest via 301 redirects or content merges.
  Differentiate remaining pages with unique angles, keywords, and search intent.</p>
  <p><span class="label">Growth Impact:</span> Consolidated authority on pillar pages improves rankings, reduces
  crawl waste, and concentrates link equity.</p>
  <p><span class="label">Effort:</span> High | 4-6 weeks (phased by cluster priority)</p>
</div>

<div class="issue critical-issue">
  <h4>C-002: Thin Content Pages (""" + str(len(thin)) + """ pages under 300 words)</h4>
  <p><span class="label">Problem:</span> """ + str(len(thin)) + """ pages have insufficient content to rank or contribute to topical authority:</p>
  <table>
    <thead><tr><th>Category</th><th>Count</th><th>Avg Words</th><th>Issue</th></tr></thead>
    <tbody>
      <tr><td>Tool Review Pages</td><td>""" + str(len(thin_tools)) + """</td><td>""" + str(int(thin_tools['word_count'].mean()) if len(thin_tools) > 0 else 0) + """</td><td>Short descriptions, no depth</td></tr>
      <tr><td>Local/Location Landing Pages</td><td>""" + str(len(thin_local)) + """</td><td>""" + str(int(thin_local['word_count'].mean()) if len(thin_local) > 0 else 0) + """</td><td>Stubs with no unique content</td></tr>
      <tr><td>Other (Case Studies, Hubs)</td><td>""" + str(len(thin_other)) + """</td><td>""" + str(int(thin_other['word_count'].mean()) if len(thin_other) > 0 else 0) + """</td><td>Missing substantive content</td></tr>
    </tbody>
  </table>
  <p><span class="label">Fix:</span> Expand high-value thin pages to 500+ words with unique content. For low-value pages,
  either noindex or consolidate into parent topics.</p>
  <p><span class="label">Effort:</span> Medium | 3-4 weeks</p>
</div>

<div class="issue warning-issue">
  <h4>C-003: Orphan / Unclustered Pages (""" + str(noise_count) + """ pages)</h4>
  <p><span class="label">Problem:</span> """ + str(noise_count) + """ pages don't semantically cluster with any topic on the site.
  These are either off-topic, too unique to support with surrounding content, or mixed-intent pages that
  confuse clustering algorithms &mdash; and likely confuse Google too.</p>
  <p><span class="label">Fix:</span> Review each orphan page. Either: (a) create supporting content to build a cluster around it,
  (b) merge it into an existing related cluster, or (c) noindex if it serves no organic purpose.</p>
  <p><span class="label">Effort:</span> Low-Medium | 1-2 weeks</p>
</div>

<div class="page-break"></div>

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

<div class="page-break"></div>

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
            slug = site_config.strip_url(u)
            html += f"""<span>{slug}</span>"""
        html += f"""</div>
  <p style="font-size:10px;color:#6b7280;margin-top:6px"><em>{row['recommendation']}</em></p>
</div>"""

    html += '<div class="page-break"></div>'

    html += """
<h2>Thin Content &mdash; Pages Needing Action</h2>
<p>All pages under 300 words, grouped by category with specific recommendations.</p>"""

    for cat_name, cat_df in [
        ("Tool Review Pages", thin_tools),
        ("Local/Location Landing Pages", thin_local),
        ("Other Thin Pages", thin_other),
    ]:
        if len(cat_df) == 0:
            continue
        html += f"""
<h3>{cat_name} ({len(cat_df)} pages)</h3>
<table>
  <thead><tr><th>URL</th><th>Words</th><th>Recommendation</th></tr></thead>
  <tbody>"""
        for _, r in cat_df.iterrows():
            slug = site_config.strip_url(r["url"])
            if cat_name == "Tool Review Pages":
                rec = "Expand to 500+ words: use cases, pricing, pros/cons, comparison"
            elif cat_name.startswith("Local"):
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

    html += """
<h2>Content Type Distribution</h2>
<p>Recommended content formats based on cluster keyword analysis and brand voice alignment.</p>
<table>
  <thead><tr><th>Content Type</th><th>Clusters</th><th>% of Total</th></tr></thead>
  <tbody>"""
    for ct, count in content_types.items():
        pct = round(count / total_clusters * 100, 1) if total_clusters else 0
        html += f"""
    <tr><td>{ct}</td><td>{count}</td><td>{pct}%</td></tr>"""
    html += """
  </tbody>
</table>"""

    html += '<div class="page-break"></div>'

    # Enhancement CSVs
    def _load_enh(name):
        p = os.path.join(out, name)
        return pd.read_csv(p) if os.path.exists(p) else pd.DataFrame()

    competitor_dfs = _discover_competitor_csvs()
    sim_df = _load_enh("similarity_scores.csv")
    if not sim_df.empty:
        sim_df = sim_df[sim_df["similarity"] >= 0.80].sort_values("similarity", ascending=False).head(25)
    fresh_df = _load_enh("content_freshness.csv")
    brand_enh = _load_enh("brand_voice_scores.csv")
    merge_enh = _load_enh("cluster_merge_suggestions.csv")
    if not merge_enh.empty:
        merge_enh = merge_enh.head(20)

    # Competitor gap analysis: stats only — actionable briefs live in the Content Ideas section
    if competitor_dfs:
        comp_label = ", ".join(name for name, _ in competitor_dfs)
        html += f"""
<h2>Competitor Gap Analysis</h2>
<p>Per-competitor topic coverage between {site_name} and {comp_label}. The actual gap topics
are turned into ready-to-execute content briefs in the <em>Content Ideas</em> section below
&mdash; this table is the summary view.</p>

<table>
  <thead><tr><th>Competitor</th><th>{site_name} advantages</th><th>Shared topics</th><th>Gaps ({site_name} missing)</th></tr></thead>
  <tbody>"""
        for comp_name, comp_df in competitor_dfs:
            gaps = comp_df[comp_df["status"].str.contains("GAP", case=False, na=False)]
            advs = comp_df[comp_df["status"].str.contains("ADVANTAGE", case=False, na=False)]
            shared = comp_df[comp_df["status"].str.contains("SHARED|cover", case=False, na=False)]
            html += f"""
    <tr>
      <td><strong>{comp_name}</strong></td>
      <td><span class="status ok">{len(advs)}</span></td>
      <td><span class="status info">{len(shared)}</span></td>
      <td><span class="status critical">{len(gaps)}</span></td>
    </tr>"""
        html += """
  </tbody>
</table>"""
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
            slug_a = site_config.strip_url(r["url_a"])
            slug_b = site_config.strip_url(r["url_b"])
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
  <p><strong>Finding:</strong> {stale_pct}% of content is 6+ months old. Content decay impacts rankings as
  Google favors freshness signals. Establish a quarterly refresh cadence targeting highest-traffic stale pages first.</p>
</div>"""

    # BRAND VOICE
    if not brand_enh.empty:
        brand_counts = brand_enh["rating"].value_counts()
        avg_score = round(brand_enh["brand_score"].mean(), 1)
        html += f"""
<h3>Brand Voice Alignment</h3>
<p>Each page scored against {site_name}'s brand voice profile (tone, style, do/don't rules). Average score: <strong>{avg_score}/100</strong>.</p>
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

    # CONTENT IDEAS (from gap analysis)
    ideas_df = _load_enh("content_ideas.csv")
    if not ideas_df.empty:
        html += '<div class="page-break"></div>'
        p1 = int((ideas_df["priority"] == "P1").sum())
        p2 = int((ideas_df["priority"] == "P2").sum())
        p3 = int((ideas_df["priority"] == "P3").sum())
        html += f"""
<h2>Content Ideas &mdash; Ready to Brief</h2>
<p>Each row below is a content brief derived from competitor gap analysis: a topic
that one or more competitors cover that {site_name} does not. Priority reflects how
many competitors validate the topic ({p1} P1, {p2} P2, {p3} P3).</p>

<table>
  <thead><tr><th>Pri</th><th>Title</th><th>Type</th><th>Words</th><th>Validated by</th></tr></thead>
  <tbody>"""
        for _, r in ideas_df.head(30).iterrows():
            pcls = "critical" if r["priority"] == "P1" else "warning" if r["priority"] == "P2" else "info"
            html += f"""
    <tr>
      <td><span class="status {pcls}">{r['priority']}</span></td>
      <td><strong>{r['title']}</strong>
          <div style="font-size:9.5px;color:#6b7280;margin-top:2px">Gap topic: <em>{r['gap_topic']}</em> &middot; Audience: {r['target_audience']}</div>
      </td>
      <td style="font-size:10px">{r['content_type']}</td>
      <td style="text-align:center;font-weight:600">{int(r['est_word_count'])}</td>
      <td style="font-size:10px;color:#6b7280">{r['covered_by']}</td>
    </tr>"""
        html += """
  </tbody>
</table>"""

        # Detailed briefs for top 10 (full key questions + keywords)
        html += """
<h3>Top 10 briefs in detail</h3>
<p>Hand these to the content team as-is. Each brief includes target keywords and the
core questions a strong piece must answer.</p>"""
        for _, r in ideas_df.head(10).iterrows():
            pcls = "critical-issue" if r["priority"] == "P1" else "warning-issue" if r["priority"] == "P2" else ""
            kws = " | ".join(str(r["suggested_keywords"]).split("|"))
            questions = str(r["key_questions"]).split("|")
            q_html = "".join(f"<li>{q.strip()}</li>" for q in questions if q.strip())
            html += f"""
<div class="issue {pcls}">
  <h4>[{r['priority']}] {r['title']}</h4>
  <p><span class="label">Format:</span> {r['content_type']} &middot;
     <span class="label">Length:</span> ~{int(r['est_word_count'])} words &middot;
     <span class="label">Audience:</span> {r['target_audience']}</p>
  <p><span class="label">Gap topic:</span> <em>{r['gap_topic']}</em> &middot;
     <span class="label">Validated by:</span> {r['covered_by']}</p>
  <p><span class="label">Target keywords:</span> {kws}</p>
  <p><span class="label">Key questions to answer:</span></p>
  <ul style="margin:4px 0 0 20px;font-size:10.5px;line-height:1.6">{q_html}</ul>
</div>"""
        html += '<div class="page-break"></div>'

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

    # CONCLUSIONS — generic, data-driven, no hardcoded narrative
    has_critical_cannib = total_cannib >= 10
    has_thin = len(thin) > 10
    html += f"""
<h2>Conclusions &amp; Recommended Execution Order</h2>

<p>{site_name}'s topical map covers <strong>{total_clusters} clusters across {total_urls} pages</strong>.
The structural issues that most directly impact rankings, in priority order:</p>

<ol style="margin:8px 0 12px 20px;font-size:11px;line-height:1.8;">
  <li><strong>Cannibalization &mdash; {total_cannib} clusters</strong>{' (priority #1: this is the biggest lever).' if has_critical_cannib else '.'} Consolidate competing pages into single pillars per topic. Largest gains come from clusters with 10+ competing URLs.</li>
  <li><strong>Thin content &mdash; {len(thin)} pages</strong>{' (significant crawl waste).' if has_thin else '.'} Expand to 500+ words or noindex.</li>
  <li><strong>Orphan pages &mdash; {noise_count} pages</strong> with no semantic cluster. Either build supporting content, merge, or noindex.</li>
</ol>

<div class="rec-box">
  <p><strong>Suggested 30-day plan:</strong></p>
  <p>1. Week 1-2: tackle the top {min(10, len(critical_cannib))} cannibalized clusters with 10+ competing URLs (highest ROI).</p>
  <p>2. Week 2-3: expand the {len(thin_local) if len(thin_local) > 0 else 0} location/local landing pages and the {len(thin_tools) if len(thin_tools) > 0 else 0} tool review pages.</p>
  <p>3. Week 3-4: review orphan pages and ship internal linking improvements for the largest clusters.</p>
  <p>4. Re-run the analysis after week 4 to measure consolidation impact.</p>
</div>

<p style="margin-top:16px;font-size:10px;color:#9ca3af">Open <code>output/dashboard.html</code> for an interactive
drill-down into every cluster, URL, and recommendation.</p>

</body></html>"""

    # Save HTML
    html_path = os.path.join(out, "report.html")
    with open(html_path, "w") as f:
        f.write(html)

    # Convert to PDF
    pdf_filename = f"Topical_Authority_Audit_{_slugify(site_name)}_{datetime.now().strftime('%Y_%m')}.pdf"
    pdf_path = os.path.join(out, pdf_filename)

    import subprocess
    try:
        result = subprocess.run(
            ["wkhtmltopdf", "--enable-local-file-access", "--page-size", "A4",
             "--margin-top", "15mm", "--margin-bottom", "15mm",
             "--margin-left", "12mm", "--margin-right", "12mm",
             html_path, pdf_path],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            logger.info("PDF generated with wkhtmltopdf: %s", pdf_path)
            return pdf_path
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    for chrome in [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]:
        if os.path.exists(chrome):
            try:
                subprocess.run(
                    [chrome, "--headless", "--disable-gpu",
                     f"--print-to-pdf={pdf_path}",
                     "--no-margins",
                     f"file://{html_path}"],
                    capture_output=True, text=True, timeout=30,
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
