"""Tabbed HTML template for the Topical Authority dashboard.

Self-contained: opens via file:// without a server. CSS + JS + JSON all inlined so
the dashboard ships as a single HTML.

Features:
  - Health Score hero (composite + 5 subscores) on the Summary tab
  - Run-history sparkline + delta vs previous run
  - Topic Cluster scatter quadrant (URL count × cannibalization severity)
  - Brand voice radial gauge
  - Donut + side-list charts (replaces the unreadable pies)
  - Treemap recolored by cannibalization severity (color), URL count = size
  - Empty states on every tab (no more silent blank panels)
  - Sortable tables (click column headers, ↑↓)
  - Per-table "Download CSV" buttons
  - Copy-to-clipboard on URLs / cluster names / brief titles (toast confirmation)
  - Deep links via URL hash (#tab=cannib&cluster=23)
  - Lazy chart init (Plotly only renders the active tab; rest defer)
  - 150ms debounced search
  - Glossary tooltips for SEO terms (data-tip="...")
  - Print stylesheet (light-mode, expanded cards)
"""

import json
from datetime import datetime
from html import escape


def _safe(value, default=""):
    return value if value is not None else default


def build_html(
    site_config,
    treemap_data,
    cannib_chart_data,
    cannib_detail,
    content_types,
    all_clusters,
    url_table,
    stats,
    thin_tools,
    thin_local,
    thin_other,
    top_cannib_summary,
    enhancements=None,
    health=None,
    thin_groups=None,
    vector_map=None,
    ask_examples=None,
    agent_run=None,
    agent_lessons_md="",
):
    if enhancements is None:
        enhancements = {}
    if health is None:
        health = {}
    if thin_groups is None:
        thin_groups = []
    if vector_map is None:
        vector_map = {"points": [], "cluster_legend": {}}
    if ask_examples is None:
        ask_examples = []

    site_name = escape(site_config.name) if site_config else "Site"
    site_domain = site_config.domain if site_config else ""
    site_domain_safe = escape(site_domain)
    today = datetime.now().strftime("%B %Y")

    total_thin = stats["thin_tools"] + stats["thin_local"] + stats["thin_other"]
    critical_count = sum(1 for c in cannib_detail if c["severity"] == "critical")
    high_count = sum(1 for c in cannib_detail if c["severity"] == "high")
    has_comp = "competitor" in enhancements
    has_sim = "similarity" in enhancements
    has_intent = "intent" in enhancements
    has_fresh = "freshness" in enhancements
    has_brand = "brand" in enhancements
    has_merge = "merges" in enhancements
    has_ideas = "content_ideas" in enhancements

    competitor_names = enhancements.get("competitor", {}).get("names", []) if has_comp else []
    competitor_th = "".join(f"<th data-sort=\"text\">{escape(name)}</th>" for name in competitor_names)

    # Action items — dedupe what's already shown in nav badges + key findings
    actions = []
    if critical_count:
        actions.append({"priority": "P1", "action": f"Consolidate {critical_count} critical cannibalized clusters (10+ competing URLs)", "impact": "High", "effort": "2 weeks"})
    near_dupes = len([s for s in enhancements.get("similarity", []) if s.get("similarity", 0) >= 0.92])
    if near_dupes:
        actions.append({"priority": "P1", "action": f"Merge {near_dupes} near-duplicate page pairs (92%+ similarity)", "impact": "High", "effort": "1 week"})
    if has_fresh:
        stale = sum(v for k, v in enhancements["freshness"].items() if "Stale" in k or "Decaying" in k)
        if stale:
            actions.append({"priority": "P1", "action": f"Refresh {stale} stale pages (6+ months old)", "impact": "High", "effort": "3-4 weeks"})
    if total_thin:
        actions.append({"priority": "P2", "action": f"Expand {total_thin} thin pages to 500+ words or noindex", "impact": "Medium", "effort": "3 weeks"})
    if has_comp:
        gaps = enhancements["comp_stats"]["gaps"]
        if gaps:
            actions.append({"priority": "P2", "action": f"Brief content team on {gaps} competitor gap topics (see Content Ideas tab)", "impact": "Medium", "effort": "4 weeks"})
    if stats["noise"]:
        actions.append({"priority": "P2", "action": f"Resolve {stats['noise']} unclustered orphan pages", "impact": "Medium", "effort": "1 week"})
    if has_brand:
        off = sum(v for k, v in enhancements["brand"]["distribution"].items() if k in ("Off-brand", "Needs work"))
        if off:
            actions.append({"priority": "P3", "action": f"Align {off} off-brand pages with brand voice guidelines", "impact": "Low", "effort": "Ongoing"})

    # ---- HTML ----
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Topical Authority Audit — {site_name}</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
:root {{
  --bg:#0f1117; --surface:#1a1d27; --surface-alt:#13151f; --border:#2a2d3a;
  --text:#e4e4e7; --muted:#9ca3af; --accent:#6366f1; --accent-soft:rgba(99,102,241,0.15);
  --red:#ef4444; --green:#22c55e; --yellow:#eab308; --blue:#3b82f6; --orange:#f97316;
}}
*{{ margin:0; padding:0; box-sizing:border-box; }}
html {{ scroll-behavior:smooth; }}
body{{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; background:var(--bg); color:var(--text); line-height:1.55; }}

/* Header */
.header{{ background:var(--surface); border-bottom:1px solid var(--border); padding:18px 32px; display:flex; justify-content:space-between; align-items:center; }}
.header h1{{ font-size:18px; font-weight:700; }}
.header .meta{{ font-size:12px; color:var(--muted); text-align:right; line-height:1.5; }}
.header a.print-link {{ color:var(--accent); font-size:11px; text-decoration:none; margin-left:12px; }}
.header a.print-link:hover {{ text-decoration:underline; }}

/* Nav */
.nav{{ display:flex; background:var(--surface-alt); border-bottom:1px solid var(--border); position:sticky; top:0; z-index:100; overflow-x:auto; padding:0 16px; }}
.nav-tab{{ padding:12px 18px; font-size:13px; font-weight:500; color:var(--muted); cursor:pointer; border-bottom:2px solid transparent; white-space:nowrap; transition:all 0.15s; user-select:none; }}
.nav-tab:hover{{ color:var(--text); }}
.nav-tab.active{{ color:var(--accent); border-bottom-color:var(--accent); }}
.nbadge{{ display:inline-block; padding:1px 6px; border-radius:8px; font-size:10px; margin-left:4px; }}
.nbadge-r{{ background:rgba(239,68,68,0.15); color:var(--red); }}
.nbadge-b{{ background:var(--accent-soft); color:var(--accent); }}

/* Tab panes */
.tab-pane{{ display:none; padding:24px 32px; }}
.tab-pane.active{{ display:block; }}

/* Health Hero */
.hero{{ background:linear-gradient(135deg,#1a1d27 0%,#212536 100%); border:1px solid var(--border); border-radius:12px; padding:24px; margin-bottom:20px; display:grid; grid-template-columns:240px 1fr; gap:24px; align-items:center; }}
.hero .score-block{{ text-align:center; }}
.hero .score-num{{ font-size:72px; font-weight:800; line-height:1; }}
.hero .score-num.green{{ color:var(--green); }}
.hero .score-num.yellow{{ color:var(--yellow); }}
.hero .score-num.red{{ color:var(--red); }}
.hero .score-num.unknown{{ color:var(--muted); }}
.hero .score-label{{ font-size:10px; color:var(--muted); text-transform:uppercase; letter-spacing:1.2px; margin-top:4px; font-weight:600; }}
.hero .score-delta{{ display:inline-block; margin-top:6px; padding:2px 10px; border-radius:10px; font-size:11px; font-weight:600; }}
.hero .delta-up{{ background:rgba(34,197,94,0.15); color:var(--green); }}
.hero .delta-down{{ background:rgba(239,68,68,0.15); color:var(--red); }}
.hero .delta-flat{{ background:rgba(156,163,175,0.15); color:var(--muted); }}
.subscore-grid{{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:10px; }}
.subscore{{ background:var(--surface-alt); border:1px solid var(--border); border-radius:8px; padding:10px 12px; }}
.subscore .label{{ font-size:10px; color:var(--muted); text-transform:uppercase; letter-spacing:0.5px; }}
.subscore .row{{ display:flex; justify-content:space-between; align-items:baseline; margin:6px 0 4px; }}
.subscore .val{{ font-size:22px; font-weight:700; }}
.subscore .val.green{{ color:var(--green); }}
.subscore .val.yellow{{ color:var(--yellow); }}
.subscore .val.red{{ color:var(--red); }}
.subscore .val.unknown{{ color:var(--muted); }}
.subscore .delta{{ font-size:11px; color:var(--muted); }}
.subscore .delta.up{{ color:var(--green); }}
.subscore .delta.down{{ color:var(--red); }}
.subscore .bar{{ background:var(--border); height:4px; border-radius:2px; overflow:hidden; }}
.subscore .bar-fill{{ height:100%; transition:width 0.3s; }}
.subscore .detail{{ font-size:10.5px; color:var(--muted); margin-top:5px; min-height:14px; }}

/* Sparkline */
.sparkline-wrap{{ display:flex; align-items:center; gap:8px; margin-top:6px; justify-content:center; font-size:10px; color:var(--muted); }}

/* Stats strip (used elsewhere) */
.stats{{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:1px; background:var(--border); margin-bottom:20px; border-radius:8px; overflow:hidden; }}
.stat{{ background:var(--surface); padding:18px 14px; text-align:center; }}
.stat .v{{ font-size:30px; font-weight:700; line-height:1.1; }}
.stat .l{{ font-size:10px; color:var(--muted); text-transform:uppercase; letter-spacing:1px; margin-top:4px; }}

/* Cards */
.card{{ background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:18px; margin-bottom:14px; }}
.card h3{{ font-size:13px; color:var(--muted); text-transform:uppercase; letter-spacing:0.5px; margin-bottom:12px; display:flex; align-items:center; justify-content:space-between; }}
.card h3 .csv-btn{{ font-size:11px; color:var(--accent); cursor:pointer; padding:3px 10px; border:1px solid var(--accent); border-radius:14px; background:transparent; font-weight:500; }}
.card h3 .csv-btn:hover{{ background:var(--accent-soft); }}
.row{{ display:grid; gap:14px; }}
.row-2{{ grid-template-columns:1fr 1fr; }}
.row-3{{ grid-template-columns:1fr 1fr 1fr; }}
.row-2-1{{ grid-template-columns:2fr 1fr; }}
@media (max-width:780px){{
  .row-2,.row-3,.row-2-1{{ grid-template-columns:1fr; }}
  .hero{{ grid-template-columns:1fr; }}
}}

/* Tables */
table{{ width:100%; border-collapse:collapse; font-size:13px; }}
th{{ text-align:left; padding:10px 12px; background:#111320; color:var(--muted); font-weight:500; text-transform:uppercase; font-size:11px; letter-spacing:0.5px; position:sticky; top:0; z-index:1; user-select:none; }}
th.sortable{{ cursor:pointer; }}
th.sortable:hover{{ color:var(--text); }}
th.sortable::after{{ content:" ↕"; color:var(--border); font-size:10px; }}
th.sort-asc::after{{ content:" ↑"; color:var(--accent); }}
th.sort-desc::after{{ content:" ↓"; color:var(--accent); }}
td{{ padding:10px 12px; border-bottom:1px solid var(--border); vertical-align:top; }}
tr:hover td{{ background:rgba(99,102,241,0.05); }}
.tw{{ max-height:560px; overflow-y:auto; border:1px solid var(--border); border-radius:8px; }}

/* URL cells: truncate long, show full on hover via title attr */
.url-cell{{ max-width:340px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}

/* Badges */
.b{{ display:inline-block; padding:2px 8px; border-radius:10px; font-size:11px; font-weight:600; }}
.b-r{{ background:rgba(239,68,68,0.15); color:var(--red); }}
.b-y{{ background:rgba(234,179,8,0.15); color:var(--yellow); }}
.b-g{{ background:rgba(34,197,94,0.15); color:var(--green); }}
.b-b{{ background:rgba(59,130,246,0.15); color:var(--blue); }}
.b-m{{ background:rgba(156,163,175,0.1); color:var(--muted); }}
.b-o{{ background:rgba(249,115,22,0.15); color:var(--orange); }}

/* Search */
.srch{{ width:100%; padding:10px 14px; background:var(--surface); border:1px solid var(--border); border-radius:8px; color:var(--text); font-size:14px; margin-bottom:12px; outline:none; }}
.srch:focus{{ border-color:var(--accent); box-shadow:0 0 0 3px rgba(99,102,241,0.15); }}

/* Expandable cards */
.expand{{ cursor:pointer; }}
.expand-body{{ display:none; margin-top:12px; padding-top:12px; border-top:1px solid var(--border); }}
.expand.open .expand-body{{ display:block; }}
.expand-arrow{{ color:var(--muted); transition:transform 0.2s; display:inline-block; }}
.expand.open .expand-arrow{{ transform:rotate(90deg); }}

/* Detail panel */
.detail{{ display:none; background:var(--surface); border:1px solid var(--accent); border-radius:8px; padding:16px; margin-bottom:12px; }}
.detail.show{{ display:block; }}

/* Action items */
.action-row{{ display:grid; grid-template-columns:60px 1fr 80px 80px; gap:12px; padding:10px 0; border-bottom:1px solid var(--border); align-items:center; font-size:13px; }}
.action-row:last-child{{ border-bottom:none; }}
.priority{{ font-weight:700; font-size:12px; }}
.priority.p1{{ color:var(--red); }}
.priority.p2{{ color:var(--yellow); }}
.priority.p3{{ color:var(--blue); }}

/* Links */
a{{ color:var(--blue); text-decoration:none; }}
a:hover{{ text-decoration:underline; }}
.kw{{ color:var(--muted); font-size:12px; max-width:280px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}

/* Empty state */
.empty{{ padding:48px 24px; text-align:center; color:var(--muted); border:2px dashed var(--border); border-radius:12px; }}
.empty .ico{{ font-size:32px; margin-bottom:8px; opacity:0.4; }}
.empty .msg{{ font-size:14px; margin-bottom:6px; color:var(--text); }}
.empty .hint{{ font-size:12px; }}
.empty code{{ background:var(--surface-alt); padding:2px 6px; border-radius:4px; font-size:11px; }}

/* Tooltips (CSS-only) */
[data-tip]{{ position:relative; cursor:help; border-bottom:1px dotted var(--muted); }}
[data-tip]:hover::after{{
  content:attr(data-tip); position:absolute; bottom:120%; left:50%; transform:translateX(-50%);
  background:#000; color:#fff; padding:6px 10px; border-radius:6px; font-size:11px; white-space:normal;
  width:240px; z-index:200; line-height:1.4; box-shadow:0 4px 12px rgba(0,0,0,0.4);
}}

/* Toast (clipboard confirmation) */
#toast{{ position:fixed; bottom:24px; left:50%; transform:translateX(-50%) translateY(100px); background:var(--accent); color:#fff; padding:10px 18px; border-radius:8px; font-size:13px; font-weight:500; opacity:0; transition:all 0.25s; pointer-events:none; z-index:1000; box-shadow:0 6px 20px rgba(0,0,0,0.4); }}
#toast.show{{ opacity:1; transform:translateX(-50%) translateY(0); }}

/* Brand gauge */
.gauge-wrap{{ position:relative; width:200px; height:120px; margin:0 auto; }}
.gauge-num{{ position:absolute; top:55%; left:50%; transform:translate(-50%,-50%); font-size:42px; font-weight:800; color:var(--accent); }}
.gauge-label{{ position:absolute; top:90%; left:50%; transform:translateX(-50%); font-size:10px; color:var(--muted); text-transform:uppercase; letter-spacing:1px; white-space:nowrap; }}

/* Footer */
.footer{{ padding:16px 32px; text-align:center; font-size:11px; color:var(--muted); border-top:1px solid var(--border); }}

/* Print stylesheet — light-mode, expand all, hide nav */
@media print {{
  :root {{ --bg:#fff; --surface:#fff; --surface-alt:#f9fafb; --border:#e5e7eb; --text:#1f2937; --muted:#6b7280; }}
  body{{ background:#fff; color:#1f2937; }}
  .nav,.csv-btn,.srch,#toast{{ display:none !important; }}
  .tab-pane{{ display:block !important; padding:16px 0; break-after:page; }}
  .tab-pane:last-child{{ break-after:auto; }}
  .expand-body{{ display:block !important; }}
  .header,.footer{{ background:#fff; }}
  .card,.hero,.stats,.subscore{{ break-inside:avoid; box-shadow:none; }}
  table th{{ background:#f3f4f6 !important; color:#374151 !important; }}
}}
</style>
</head>
<body>

<div id="toast"></div>

<div class="header">
  <div>
    <h1>Topical Authority Audit</h1>
    <span class="meta">{site_domain_safe}</span>
  </div>
  <div class="meta">
    {today} &mdash; {stats['total_urls']} pages analyzed
    <a href="javascript:window.print()" class="print-link">Print / Save PDF</a>
  </div>
</div>

<div class="nav" id="nav" role="tablist">
  <div class="nav-tab active" data-tab="summary">Summary</div>
  <div class="nav-tab" data-tab="clusters">Topic Clusters <span class="nbadge nbadge-b">{stats['total_clusters']}</span></div>
  <div class="nav-tab" data-tab="cannib">Cannibalization <span class="nbadge nbadge-r">{stats['cannib_flags']}</span></div>
  <div class="nav-tab" data-tab="duplicates">Duplicates <span class="nbadge nbadge-r">{len(enhancements.get('similarity',[]))}</span></div>
  <div class="nav-tab" data-tab="thin">Thin Content <span class="nbadge nbadge-r">{total_thin}</span></div>
  <div class="nav-tab" data-tab="intent">Search Intent</div>
  <div class="nav-tab" data-tab="freshness">Freshness</div>
  <div class="nav-tab" data-tab="brand">Brand Voice</div>
  <div class="nav-tab" data-tab="competitors">Competitors</div>
  <div class="nav-tab" data-tab="ideas">Content Ideas <span class="nbadge nbadge-b">{enhancements.get("content_ideas_stats", {}).get("total", 0)}</span></div>
  <div class="nav-tab" data-tab="vmap">Vector Map <span class="nbadge nbadge-b">{len(vector_map.get("points", []))}</span></div>
  <div class="nav-tab" data-tab="ask">Ask the Audit</div>
  <div class="nav-tab" data-tab="agent">Recommend Agent</div>
  <div class="nav-tab" data-tab="lessons">Lessons</div>
  <div class="nav-tab" data-tab="merges">Cluster Merges</div>
  <div class="nav-tab" data-tab="explorer">URL Explorer</div>
</div>

<!-- ==================== TAB: SUMMARY ==================== -->
<div class="tab-pane active" id="tab-summary">
  <div id="hero-mount"></div>

  <div class="row row-2" style="margin-bottom:14px">
    <div class="card">
      <h3>Key Findings</h3>
      <div id="key-findings" style="font-size:13px;line-height:1.85"></div>
    </div>
    <div class="card">
      <h3>Topic Cluster Quadrant <span data-tip="Each dot is a cluster. Top-right = many pages with cannibalization (consolidate first). Top-left = many pages, healthy (your pillars).">ⓘ</span></h3>
      <div id="quadrant" style="height:280px"></div>
    </div>
  </div>

  <div class="card">
    <h3>Action Items <span data-tip="Auto-generated from issues found. Prioritized by impact and validated by data.">ⓘ</span></h3>
    <div id="action-items"></div>
  </div>
</div>

<!-- ==================== TAB: CLUSTERS ==================== -->
<div class="tab-pane" id="tab-clusters">
  <div class="card">
    <h3>Topic Cluster Map (top 30) <span data-tip="Color = cannibalization severity (red = many competing URLs). Size = total pages.">ⓘ</span></h3>
    <div id="treemap"></div>
  </div>
  <input type="text" class="srch" id="cluster-search" placeholder="Search clusters by name, keyword, or content type...">
  <div id="cluster-detail" class="detail">
    <h3 id="detail-title" style="font-size:16px;margin-bottom:8px"></h3>
    <div style="margin-bottom:10px;font-size:13px"><strong>Keywords:</strong> <span id="detail-kw" style="color:var(--muted)"></span></div>
    <div id="detail-brand-block" style="display:none;margin-bottom:10px">
      <div class="row row-2" style="font-size:13px">
        <div><strong>Content Type:</strong> <span id="detail-type"></span></div>
        <div><strong>Angle:</strong> <span id="detail-angle" style="color:var(--muted)"></span></div>
        <div><strong>CTA Style:</strong> <span id="detail-cta" style="color:var(--muted)"></span></div>
      </div>
    </div>
    <div id="detail-brand-empty" style="display:none;font-size:12px;color:var(--muted);margin-bottom:10px;font-style:italic">
      No brand voice profile loaded. Pass <code style="background:var(--surface-alt);padding:1px 6px;border-radius:3px">--brand-voice &lt;pdf&gt;</code> to populate Content Type / Angle / CTA per cluster.
    </div>
    <strong>URLs:</strong>
    <div id="detail-urls" style="max-height:200px;overflow-y:auto"></div>
  </div>
  <div class="card" style="padding:0">
    <h3 style="padding:14px 18px 0 18px">All Clusters <button class="csv-btn" data-csv="clusters">Download CSV</button></h3>
    <div class="tw" style="border:none">
      <table id="cluster-table">
        <thead><tr>
          <th class="sortable" data-sort="num">ID</th>
          <th class="sortable" data-sort="text">Cluster</th>
          <th class="sortable" data-sort="num">URLs</th>
          <th>Keywords</th>
          <th class="sortable" data-sort="text">Type</th>
          <th class="sortable" data-sort="text">Status</th>
        </tr></thead>
        <tbody></tbody>
      </table>
    </div>
  </div>
</div>

<!-- ==================== TAB: CANNIBALIZATION ==================== -->
<div class="tab-pane" id="tab-cannib">
  <div class="card">
    <h3>Cannibalization by cluster <span data-tip="Pages competing for the same keywords. Tall bars = strongest consolidation candidates.">ⓘ</span></h3>
    <div id="cannib-bar-wrap" style="max-height:600px;overflow-y:auto"><div id="cannib-bar"></div></div>
  </div>
  <input type="text" class="srch" id="cannib-search" placeholder="Search cannibalized clusters...">
  <div id="cannib-list"></div>
</div>

<!-- ==================== TAB: DUPLICATES ==================== -->
<div class="tab-pane" id="tab-duplicates">
  <div id="duplicates-content"></div>
</div>

<!-- ==================== TAB: THIN CONTENT ==================== -->
<div class="tab-pane" id="tab-thin">
  <div id="thin-content"></div>
</div>

<!-- ==================== TAB: INTENT ==================== -->
<div class="tab-pane" id="tab-intent">
  <div id="intent-content"></div>
</div>

<!-- ==================== TAB: FRESHNESS ==================== -->
<div class="tab-pane" id="tab-freshness">
  <div id="freshness-content"></div>
</div>

<!-- ==================== TAB: BRAND VOICE ==================== -->
<div class="tab-pane" id="tab-brand">
  <div id="brand-content"></div>
</div>

<!-- ==================== TAB: COMPETITORS ==================== -->
<div class="tab-pane" id="tab-competitors">
  <div id="competitors-content"></div>
</div>

<!-- ==================== TAB: CONTENT IDEAS ==================== -->
<div class="tab-pane" id="tab-ideas">
  <div id="ideas-content"></div>
</div>

<!-- ==================== TAB: VECTOR MAP ==================== -->
<div class="tab-pane" id="tab-vmap">
  <div class="card">
    <h3>Embedding Space (2D projection) <span data-tip="Each dot is one URL. Coordinates come from a UMAP projection of the page's average chunk embedding. Pages near each other share semantic content.">ⓘ</span></h3>
    <p style="color:var(--muted);font-size:13px;margin-bottom:12px">The same FAISS index that drove cluster discovery during the audit is reused as a RAG retrieval store after. <strong>Two jobs, one artifact.</strong> Each dot below is one URL. Color = cluster. Hover for details.</p>
    <div id="vmap-chart" style="height:520px"></div>
  </div>
</div>

<!-- ==================== TAB: ASK THE AUDIT ==================== -->
<div class="tab-pane" id="tab-ask">
  <div id="ask-content"></div>
</div>

<!-- ==================== TAB: RECOMMEND AGENT ==================== -->
<div class="tab-pane" id="tab-agent">
  <div id="agent-content"></div>
</div>

<!-- ==================== TAB: LESSONS ==================== -->
<div class="tab-pane" id="tab-lessons">
  <div id="lessons-content"></div>
</div>

<!-- ==================== TAB: MERGES ==================== -->
<div class="tab-pane" id="tab-merges">
  <div id="merges-content"></div>
</div>

<!-- ==================== TAB: URL EXPLORER ==================== -->
<div class="tab-pane" id="tab-explorer">
  <input type="text" class="srch" id="url-search" placeholder="Search URLs...">
  <div class="card" style="padding:0">
    <h3 style="padding:14px 18px 0">URLs <button class="csv-btn" data-csv="urls">Download CSV</button></h3>
    <div class="tw" style="border:none">
      <table id="url-table">
        <thead><tr>
          <th class="sortable" data-sort="text">URL</th>
          <th class="sortable" data-sort="num">Cluster ID</th>
          <th class="sortable" data-sort="text">Primary cluster</th>
          <th class="sortable" data-sort="text" data-tip="The closest second-best cluster this URL also belongs to (the 'spoke'). Pages with a spoke cluster are good candidates to also link from that cluster's pillar.">Spoke cluster</th>
        </tr></thead>
        <tbody></tbody>
      </table>
    </div>
  </div>
</div>

<div class="footer">Topical Authority Audit &mdash; {site_name} &mdash; {today}</div>

<script>
// ============================================================================
// DATA — embedded JSON (kept inline so file:// works without a server)
// ============================================================================
const SITE_DOMAIN={json.dumps(site_domain)};
const SITE_NAME={json.dumps(site_config.name if site_config else "Site")};
const TREEMAP={json.dumps(treemap_data)};
const CANNIB_CHART={json.dumps(cannib_chart_data)};
const CANNIB_DETAIL={json.dumps(cannib_detail)};
const CONTENT_TYPES={json.dumps(content_types)};
const ALL_CLUSTERS={json.dumps(all_clusters)};
const URL_TABLE={json.dumps(url_table)};
const STATS={json.dumps(stats)};
const THIN_TOOLS={json.dumps(thin_tools)};
const THIN_LOCAL={json.dumps(thin_local)};
const THIN_OTHER={json.dumps(thin_other)};
const THIN_GROUPS={json.dumps(thin_groups)};
const VECTOR_MAP={json.dumps(vector_map)};
const ASK_EXAMPLES={json.dumps(ask_examples)};
const AGENT_RUN={json.dumps(agent_run)};
const AGENT_LESSONS_MD={json.dumps(agent_lessons_md)};
const ENH={json.dumps(enhancements)};
const HEALTH={json.dumps(health)};
const ACTIONS={json.dumps(actions)};

// ============================================================================
// HELPERS
// ============================================================================
const SITE_PREFIXES=[
  'https://'+SITE_DOMAIN+'/','http://'+SITE_DOMAIN+'/',
  'https://www.'+SITE_DOMAIN.replace(/^www\\./,'')+'/','http://www.'+SITE_DOMAIN.replace(/^www\\./,'')+'/'
];
function stripUrl(u){{ if(!u||!SITE_DOMAIN)return u||''; for(const p of SITE_PREFIXES){{ if(u.indexOf(p)===0)return '/'+u.slice(p.length); }} return u; }}

const PB='#1a1d27',PT='#9ca3af';
const PL={{paper_bgcolor:PB,plot_bgcolor:PB,font:{{color:PT,size:12}},margin:{{t:10,b:30,l:40,r:10}}}};

const typeColor={{'service':'#ef4444','industry':'#f97316','industry-hub':'#f97316','local-landing':'#eab308','blog':'#6366f1','tool-review':'#8b5cf6','webinar':'#3b82f6','case-study':'#22c55e','homepage':'#ef4444','listing':'#9ca3af'}};
const intentColor={{'comparison':'#8b5cf6','howto':'#3b82f6','definition':'#22c55e','framework':'#f97316','examples':'#eab308','metrics':'#06b6d4','checklist':'#a78bfa','guide':'#6366f1'}};
const severityColor={{'critical':'#ef4444','high':'#eab308','moderate':'#22c55e'}};

// Debounce helper
function debounce(fn, ms){{ let t; return function(...a){{ clearTimeout(t); t=setTimeout(()=>fn.apply(this,a),ms); }}; }}

// Toast
function toast(msg){{ const t=document.getElementById('toast'); t.textContent=msg; t.classList.add('show'); setTimeout(()=>t.classList.remove('show'),1600); }}

// Copy to clipboard
function copy(text){{
  if(navigator.clipboard){{ navigator.clipboard.writeText(text).then(()=>toast('Copied!')); }}
  else{{ const ta=document.createElement('textarea'); ta.value=text; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove(); toast('Copied!'); }}
}}

// CSV download from array of objects
function downloadCSV(filename, rows){{
  if(!rows||!rows.length){{ toast('Nothing to export'); return; }}
  const cols=Object.keys(rows[0]);
  const esc=v=>{{ if(v==null)return ''; const s=String(v); return /[",\\n]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s; }};
  const csv=[cols.join(',')].concat(rows.map(r=>cols.map(c=>esc(r[c])).join(','))).join('\\n');
  const blob=new Blob([csv],{{type:'text/csv'}});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download=filename;
  document.body.appendChild(a); a.click(); a.remove();
}}

// CSV registrations
const CSV_SOURCES={{
  clusters: ()=>ALL_CLUSTERS.map(c=>({{id:c.id,name:c.name,urls:c.urls,keywords:c.keywords,content_type:c.content_type,cannibalized:c.cannibalized}})),
  urls: ()=>URL_TABLE,
  ideas: ()=>(ENH.content_ideas||[]).map(i=>({{...i,suggested_keywords:Array.isArray(i.suggested_keywords)?i.suggested_keywords.join(' | '):i.suggested_keywords,key_questions:Array.isArray(i.key_questions)?i.key_questions.join(' | '):i.key_questions}})),
  cannib: ()=>CANNIB_DETAIL.map(c=>({{id:c.id,name:c.name,count:c.count,severity:c.severity,has_conversion_risk:c.has_conversion_risk,analysis:c.analysis,urls:c.urls.map(u=>u.url).join(' | ')}})),
  similarity: ()=>ENH.similarity||[],
  brand: ()=>(ENH.brand?ENH.brand.bottom:[]),
  competitor: ()=>(ENH.competitor?ENH.competitor.rows:[]).map(r=>{{const o={{topic:r.topic,target:r.target,status:r.status}};(ENH.competitor.names||[]).forEach(n=>o[n]=r.competitors&&r.competitors[n]?'Y':'');return o;}}),
  merges: ()=>ENH.merges||[],
}};

document.addEventListener('click',(e)=>{{
  const btn=e.target.closest('[data-csv]');
  if(btn){{ e.stopPropagation(); const key=btn.dataset.csv; const fn=CSV_SOURCES[key]; if(fn) downloadCSV(`${{key}}-${{SITE_DOMAIN||'site'}}.csv`, fn()); }}
}});

// Empty state helper
function emptyState(message, hint){{
  return `<div class="empty"><div class="ico">∅</div><div class="msg">${{message}}</div>${{hint?`<div class="hint">${{hint}}</div>`:''}}</div>`;
}}

// Sortable tables
function makeSortable(tableId){{
  const tbl=document.getElementById(tableId); if(!tbl) return;
  const heads=tbl.querySelectorAll('th.sortable');
  heads.forEach((th, idx)=>{{
    th.addEventListener('click',()=>{{
      const tbody=tbl.querySelector('tbody');
      const rows=Array.from(tbody.querySelectorAll('tr'));
      const isAsc=!th.classList.contains('sort-asc');
      heads.forEach(h=>h.classList.remove('sort-asc','sort-desc'));
      th.classList.add(isAsc?'sort-asc':'sort-desc');
      const sortType=th.dataset.sort||'text';
      rows.sort((a,b)=>{{
        const av=a.children[idx]?.innerText.trim()||'';
        const bv=b.children[idx]?.innerText.trim()||'';
        if(sortType==='num'){{ return (parseFloat(av)||0)-(parseFloat(bv)||0); }}
        return av.localeCompare(bv);
      }});
      if(!isAsc) rows.reverse();
      rows.forEach(r=>tbody.appendChild(r));
    }});
  }});
}}

// Lazy chart registry
const LAZY={{}};
function registerLazy(tabId, fn){{ if(!LAZY[tabId]) LAZY[tabId]=[]; LAZY[tabId].push(fn); }}
function runLazy(tabId){{ (LAZY[tabId]||[]).forEach(fn=>{{try{{fn();}}catch(e){{console.error(e);}}}}); LAZY[tabId]=[]; }}

// Tab nav with deep-linking
function activateTab(name){{
  document.querySelectorAll('.nav-tab').forEach(t=>t.classList.toggle('active',t.dataset.tab===name));
  document.querySelectorAll('.tab-pane').forEach(p=>p.classList.toggle('active',p.id==='tab-'+name));
  runLazy(name);
  // Resize only the visible tab's plots (avoids stale layout)
  setTimeout(()=>{{
    document.querySelectorAll('#tab-'+name+' .js-plotly-plot').forEach(el=>{{ try{{Plotly.Plots.resize(el);}}catch(e){{}} }});
  }},20);
  if(history.replaceState) history.replaceState(null,'','#tab='+name);
}}
document.querySelectorAll('.nav-tab').forEach(tab=>{{
  tab.addEventListener('click',()=>activateTab(tab.dataset.tab));
}});

// Parse hash on boot
function applyHash(){{
  const h=window.location.hash.replace('#','');
  if(!h) return;
  const params={{}}; h.split('&').forEach(p=>{{const [k,v]=p.split('='); params[k]=v;}});
  if(params.tab) activateTab(params.tab);
  if(params.cluster) setTimeout(()=>showDetail(parseInt(params.cluster)),200);
}}

// ============================================================================
// HEALTH HERO
// ============================================================================
function renderHero(){{
  const mount=document.getElementById('hero-mount'); if(!mount) return;
  if(!HEALTH||HEALTH.composite==null){{
    mount.innerHTML=emptyState('Site Health not computed yet','Health score is generated on each pipeline run.');
    return;
  }}
  const c=HEALTH.composite, lbl=HEALTH.composite_label||'unknown';
  const subs=HEALTH.subscores||{{}};
  const deltas=HEALTH.deltas||{{}};
  const spark=HEALTH.sparkline||[];

  // Sparkline SVG
  let sparkHTML='';
  if(spark.length>1){{
    const w=120,h=28; const min=Math.min(...spark), max=Math.max(...spark);
    const rng=Math.max(max-min,1);
    const pts=spark.map((v,i)=>`${{(i/(spark.length-1))*(w-4)+2}},${{h-2-((v-min)/rng)*(h-4)}}`);
    sparkHTML=`<svg width="${{w}}" height="${{h}}" viewBox="0 0 ${{w}} ${{h}}"><polyline fill="none" stroke="#6366f1" stroke-width="2" points="${{pts.join(' ')}}"/><circle cx="${{pts[pts.length-1].split(',')[0]}}" cy="${{pts[pts.length-1].split(',')[1]}}" r="2.5" fill="#6366f1"/></svg>`;
  }}

  // Composite delta badge
  let deltaHTML='';
  const compDelta=deltas.composite;
  if(compDelta==null) deltaHTML='';
  else if(compDelta>0) deltaHTML=`<span class="score-delta delta-up">▲ ${{compDelta}} vs last run</span>`;
  else if(compDelta<0) deltaHTML=`<span class="score-delta delta-down">▼ ${{Math.abs(compDelta)}} vs last run</span>`;
  else deltaHTML=`<span class="score-delta delta-flat">— no change</span>`;

  const subLabels={{coverage:'Topic Coverage',cannibalization:'Cannibalization',freshness:'Freshness',brand:'Brand Voice',competitive:'Competitive'}};
  const subTips={{
    coverage:'How broadly the site covers topical clusters relative to its size.',
    cannibalization:'Share of clusters with multiple URLs competing for the same keywords. Higher score = fewer conflicts.',
    freshness:'Share of pages that are NOT 6+ months stale. Higher = healthier publish cadence.',
    brand:'Average alignment with your brand voice profile (0-100).',
    competitive:'How many topics in the gap matrix the site already covers vs leaves to competitors.'
  }};
  const subColor={{green:'#22c55e',yellow:'#eab308',red:'#ef4444',unknown:'#9ca3af'}};
  const subHTML=Object.keys(subLabels).map(k=>{{
    const s=subs[k]; if(!s) return '';
    const c=subColor[s.label]||subColor.unknown;
    const d=deltas[k];
    let dHTML='';
    if(d!=null){{ if(d>0) dHTML=`<span class="delta up">▲ ${{d}}</span>`; else if(d<0) dHTML=`<span class="delta down">▼ ${{Math.abs(d)}}</span>`; else dHTML=`<span class="delta">—</span>`; }}
    return `<div class="subscore">
      <div class="label" data-tip="${{subTips[k]||''}}">${{subLabels[k]}}</div>
      <div class="row"><div class="val ${{s.label}}">${{s.score}}</div>${{dHTML}}</div>
      <div class="bar"><div class="bar-fill" style="width:${{s.score}}%;background:${{c}}"></div></div>
      <div class="detail">${{s.detail||''}}</div>
    </div>`;
  }}).join('');

  mount.innerHTML=`<div class="hero">
    <div class="score-block">
      <div class="score-num ${{lbl}}">${{c}}</div>
      <div class="score-label">Site Health / 100</div>
      <div>${{deltaHTML}}</div>
      ${{sparkHTML?`<div class="sparkline-wrap">${{sparkHTML}}<span>last ${{spark.length}} runs</span></div>`:''}}
    </div>
    <div>
      <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:10px">Subscores · weighted composite</div>
      <div class="subscore-grid">${{subHTML}}</div>
    </div>
  </div>`;
}}

// ============================================================================
// SUMMARY: Key Findings + Action Items
// ============================================================================
function renderKeyFindings(){{
  const el=document.getElementById('key-findings');
  const findings=[];
  if(STATS.cannib_flags) findings.push(`<div><span class="b b-r">Critical</span> <strong>${{STATS.cannib_flags}}</strong> clusters with <span data-tip="Multiple pages on the same site competing for the same keywords. Splits ranking signals and link equity.">cannibalization</span></div>`);
  const nearDupes=(ENH.similarity||[]).filter(s=>s.similarity>=0.92).length;
  if(nearDupes) findings.push(`<div><span class="b b-r">Critical</span> <strong>${{nearDupes}}</strong> near-duplicate page pairs (92%+)</div>`);
  const totalThin=(STATS.thin_tools||0)+(STATS.thin_local||0)+(STATS.thin_other||0);
  if(totalThin) findings.push(`<div><span class="b b-y">Warning</span> <strong>${{totalThin}}</strong> thin pages under 300 words</div>`);
  if(ENH.freshness){{ const stale=Object.entries(ENH.freshness).filter(([k])=>k.includes('Stale')||k.includes('Decaying')).reduce((a,[,v])=>a+v,0); if(stale) findings.push(`<div><span class="b b-y">Warning</span> <strong>${{stale}}</strong> pages 6+ months stale</div>`); }}
  if(ENH.comp_stats&&ENH.comp_stats.gaps) findings.push(`<div><span class="b b-b">Info</span> <strong>${{ENH.comp_stats.gaps}}</strong> topic gaps vs competitors</div>`);
  if(STATS.total_clusters) findings.push(`<div><span class="b b-g">Strength</span> <strong>${{STATS.total_clusters}}</strong> topic clusters identified</div>`);
  el.innerHTML=findings.length?findings.join(''):emptyState('No findings to report','Run the pipeline to populate this section.');
}}

function renderActionItems(){{
  const el=document.getElementById('action-items');
  if(!ACTIONS.length){{ el.innerHTML=emptyState('No action items','Pipeline reported no critical issues — clean run.'); return; }}
  el.innerHTML=`<div class="action-row" style="border-bottom:1px solid var(--border);font-weight:600;font-size:11px;color:var(--muted);text-transform:uppercase">
    <div>Priority</div><div>Action</div><div>Impact</div><div>Effort</div>
  </div>`+ACTIONS.map(a=>`<div class="action-row">
    <div class="priority ${{a.priority.toLowerCase()}}">${{a.priority}}</div>
    <div>${{a.action}}</div>
    <div>${{a.impact}}</div>
    <div style="color:var(--muted)">${{a.effort}}</div>
  </div>`).join('');
}}

// Cluster scatter quadrant on summary tab
registerLazy('summary',()=>{{
  if(!ALL_CLUSTERS.length){{ document.getElementById('quadrant').innerHTML=emptyState('No clusters yet'); return; }}
  const cannibSet=new Set(CANNIB_DETAIL.map(c=>c.id));
  const sevByCluster={{}}; CANNIB_DETAIL.forEach(c=>sevByCluster[c.id]={{count:c.count,sev:c.severity}});
  const x=ALL_CLUSTERS.map(c=>c.urls);
  const y=ALL_CLUSTERS.map(c=>{{ const s=sevByCluster[c.id]; return s?s.count:0; }});
  const labels=ALL_CLUSTERS.map(c=>c.name);
  const colors=ALL_CLUSTERS.map(c=>{{ const s=sevByCluster[c.id]; if(!s)return '#22c55e'; return severityColor[s.sev]||'#6366f1'; }});
  Plotly.newPlot('quadrant',[{{type:'scatter',mode:'markers',x,y,text:labels,
    hovertemplate:'<b>%{{text}}</b><br>%{{x}} URLs<br>%{{y}} cannibalized<extra></extra>',
    marker:{{size:12,color:colors,line:{{color:'#0f1117',width:1}}}}
  }}],{{...PL,height:280,margin:{{t:10,b:40,l:50,r:10}},
    xaxis:{{title:'Pages in cluster',gridcolor:'#2a2d3a',zerolinecolor:'#2a2d3a'}},
    yaxis:{{title:'Cannibalized pages',gridcolor:'#2a2d3a',zerolinecolor:'#2a2d3a'}},
    shapes:[
      {{type:'line',x0:Math.max(...x)/2,x1:Math.max(...x)/2,y0:0,y1:Math.max(...y,1),line:{{color:'#2a2d3a',dash:'dash'}}}},
      {{type:'line',x0:0,x1:Math.max(...x,1),y0:Math.max(...y,1)/2,y1:Math.max(...y,1)/2,line:{{color:'#2a2d3a',dash:'dash'}}}}
    ]
  }},{{responsive:true,displayModeBar:false}});
}});

// ============================================================================
// CLUSTERS TAB — treemap recolored by severity
// ============================================================================
registerLazy('clusters',()=>{{
  if(!TREEMAP.labels||!TREEMAP.labels.length){{ document.getElementById('treemap').innerHTML=emptyState('No clusters formed','Run the pipeline against more URLs.'); return; }}
  // De-duplicate cluster names (TF-IDF can produce duplicates like two "Marketing Leaders" clusters).
  // Plotly treemap silently breaks when label values collide — so we suffix duplicates.
  const seen={{}};
  const labels=TREEMAP.labels.map((n,i)=>{{
    seen[n]=(seen[n]||0)+1;
    return seen[n]>1?`${{n}} (#${{TREEMAP.ids[i]}})`:n;
  }});
  // Color by cannibalization severity if available, else neutral blue.
  const sevByName={{}}; CANNIB_DETAIL.forEach(c=>sevByName[c.name]={{count:c.count,sev:c.severity}});
  const colors=TREEMAP.labels.map(name=>{{ const s=sevByName[name]; return s?(severityColor[s.sev]||'#6366f1'):'#3b82f6'; }});
  // Build a label-with-size string. Plotly auto-clips when cells are too small for the
  // label, but explicit textposition + textfont control prevents the overflow / glitch
  // we saw with values like "Market Insi..." spilling out of cells.
  Plotly.newPlot('treemap',[{{type:'treemap',labels:labels,values:TREEMAP.values,
    parents:labels.map(()=>''),
    ids:TREEMAP.ids.map(String),
    text:TREEMAP.keywords.map(k=>k.split(',').slice(0,3).join(', ')),
    hovertemplate:'<b>%{{label}}</b><br>%{{value}} URLs<br>%{{text}}<extra></extra>',
    textinfo:'label+value',
    textfont:{{size:12,color:'#fff'}},
    textposition:'middle center',
    marker:{{colors,line:{{width:2,color:'#0f1117'}},pad:{{t:2,l:2,r:2,b:2}}}},
    pathbar:{{visible:false}},
    tiling:{{packing:'squarify',pad:2}},
  }}],{{...PL,margin:{{t:10,b:10,l:10,r:10}},height:480,
    uniformtext:{{minsize:10,mode:'hide'}}}},
    {{responsive:true,displayModeBar:false}});
}});

function renderClusterTable(filter=''){{
  const tb=document.querySelector('#cluster-table tbody'); if(!tb) return;
  if(!ALL_CLUSTERS.length){{ tb.parentElement.parentElement.innerHTML=emptyState('No clusters','Run the pipeline first.'); return; }}
  const fl=filter.toLowerCase();
  const rows=ALL_CLUSTERS.filter(c=>!fl||c.name.toLowerCase().includes(fl)||(c.keywords||'').toLowerCase().includes(fl)||(c.content_type||'').toLowerCase().includes(fl));
  tb.innerHTML=rows.map(c=>`<tr style="cursor:pointer" onclick="showDetail(${{c.id}})">
    <td>${{c.id}}</td>
    <td><strong>${{c.name}}</strong> <span style="color:var(--muted);font-size:11px;cursor:pointer" onclick="event.stopPropagation();copy('${{c.name.replace(/'/g,"\\\\'")}}')">⎘</span></td>
    <td>${{c.urls}}</td>
    <td class="kw" title="${{c.keywords||''}}">${{c.keywords||''}}</td>
    <td><span class="b b-b">${{c.content_type||'-'}}</span></td>
    <td>${{c.cannibalized?'<span class="b b-r">Cannibalized</span>':'<span class="b b-g">OK</span>'}}</td>
  </tr>`).join('');
}}

function showDetail(id){{
  const c=ALL_CLUSTERS.find(x=>x.id===id); if(!c) return;
  const urls=URL_TABLE.filter(u=>u.cluster===id);
  document.getElementById('detail-title').textContent=`[${{c.id}}] ${{c.name}} — ${{c.urls}} URLs`;
  document.getElementById('detail-kw').textContent=c.keywords||'';
  // Show the brand-voice fields only if we have data; otherwise show the helper note.
  const hasBrand = (c.content_type && c.content_type.trim()) || (c.angle && c.angle.trim()) || (c.cta && c.cta.trim());
  document.getElementById('detail-brand-block').style.display = hasBrand ? '' : 'none';
  document.getElementById('detail-brand-empty').style.display = hasBrand ? 'none' : '';
  if (hasBrand) {{
    document.getElementById('detail-type').textContent=c.content_type||'—';
    document.getElementById('detail-angle').textContent=c.angle||'—';
    document.getElementById('detail-cta').textContent=c.cta||'—';
  }}
  document.getElementById('detail-urls').innerHTML=urls.map(u=>`<a href="${{u.url}}" target="_blank" style="display:block;padding:3px 0;font-size:13px">${{u.url}}</a>`).join('');
  const panel=document.getElementById('cluster-detail');
  panel.classList.add('show');
  panel.scrollIntoView({{behavior:'smooth',block:'nearest'}});
  if(history.replaceState) history.replaceState(null,'','#tab=clusters&cluster='+id);
}}

// ============================================================================
// CANNIBALIZATION TAB
// ============================================================================
registerLazy('cannib',()=>{{
  if(!CANNIB_CHART.labels||!CANNIB_CHART.labels.length){{
    document.getElementById('cannib-bar-wrap').innerHTML=emptyState('No cannibalization detected','Clean topical structure — no clusters with multiple competing pages.');
    document.getElementById('cannib-list').innerHTML='';
    return;
  }}
  Plotly.newPlot('cannib-bar',[{{
    type:'bar',y:CANNIB_CHART.labels.slice().reverse(),x:CANNIB_CHART.values.slice().reverse(),orientation:'h',
    marker:{{color:CANNIB_CHART.values.slice().reverse().map(v=>v>=10?'#ef4444':v>=6?'#eab308':'#22c55e')}},
    text:CANNIB_CHART.values.slice().reverse(),textposition:'outside',textfont:{{color:'#9ca3af',size:11}},
  }}],{{...PL,height:Math.max(400,CANNIB_CHART.labels.length*26),margin:{{t:10,b:20,l:200,r:60}},
    xaxis:{{gridcolor:'#2a2d3a'}},yaxis:{{tickfont:{{size:12,color:'#e4e4e7'}}}}}},
    {{responsive:true,displayModeBar:false}});
}});

function renderCannib(filter=''){{
  const fl=filter.toLowerCase();
  const items=CANNIB_DETAIL.filter(c=>!fl||c.name.toLowerCase().includes(fl)||(c.analysis||'').toLowerCase().includes(fl));
  const list=document.getElementById('cannib-list');
  if(!items.length){{ list.innerHTML=emptyState('No matches'); return; }}
  list.innerHTML=items.map(c=>{{
    const isFalse=c.is_real_cannibalization===false;
    const cb=isFalse?'border-left:3px solid var(--muted);opacity:0.75;':(c.has_conversion_risk?'border-left:3px solid var(--red);':'');
    const sevBadge=isFalse?'<span class="b b-m" data-tip="The SEO advisor reviewed this cluster and determined the URLs are NOT actually competing for the same search intent. Probably mixed page types grouped by TF-IDF noise.">FALSE POSITIVE</span>':`<span class="b ${{c.severity==='critical'?'b-r':c.severity==='high'?'b-y':'b-g'}}">${{c.count}} URLs · ${{c.severity}}</span>`;
    return `
    <div class="card expand" onclick="this.classList.toggle('open')" style="cursor:pointer;${{cb}}">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <div>
          <strong>${{c.name}}</strong>
          ${{c.has_conversion_risk&&!isFalse?'<span class="b b-r" style="margin-left:8px" data-tip="A blog/info page is competing against a service page for the same keywords. Risk: blog outranks service, users never convert.">Conversion Risk</span>':''}}
        </div>
        <div>${{sevBadge}} <span class="expand-arrow">▶</span></div>
      </div>
      <div style="font-size:12px;color:var(--muted);margin-top:6px">${{c.analysis||''}}</div>
      ${{c.keywords&&c.keywords.length?'<div style="margin-top:4px;font-size:11px;color:var(--muted)">Shared keywords: '+c.keywords.join(', ')+'</div>':''}}
      ${{c.advisor_reasoning?`<div style="margin-top:4px;font-size:11px;color:var(--accent);font-style:italic">▶ ${{c.advisor_reasoning}}</div>`:''}}
      ${{c.winner_slug&&!isFalse?`<div style="margin-top:6px;font-size:11px;color:var(--green)">▶ Recommended winner: <code style="background:rgba(34,197,94,0.1);padding:1px 6px;border-radius:4px">${{c.winner_slug}}</code></div>`:''}}
      <div class="expand-body">
        <table style="font-size:12px">
          <thead><tr>
            <th style="width:9%">Verdict</th>
            <th style="width:33%">URL</th>
            <th style="width:11%">Type</th>
            <th style="width:12%">Intent</th>
            <th style="width:35%">Recommended action</th>
          </tr></thead>
          <tbody>${{c.urls.map(u=>{{
            const tc=typeColor[u.type]||'#6b7280';
            const ipc={{transactional:'#22c55e',commercial:'#3b82f6',navigational:'#9ca3af',informational:'#6366f1'}};
            const ic=ipc[u.intent_primary]||'#6b7280';
            const rec=u.recommendation||'MERGE';
            const recBadge={{WINNER:'b-g',MERGE:'b-r',DIFFERENTIATE:'b-y',REVIEW:'b-o',EXCLUDE:'b-m'}};
            const recCls=recBadge[rec]||'b-m';
            const isWinner=rec==='WINNER';
            const isExclude=rec==='EXCLUDE';
            const rowBg=isWinner?'background:rgba(34,197,94,0.07);':isExclude?'background:rgba(156,163,175,0.05);opacity:0.7;':'';
            const actionColor=isWinner?'var(--green)':isExclude?'var(--muted)':rec==='MERGE'?'var(--red)':rec==='DIFFERENTIATE'?'var(--yellow)':'var(--orange)';
            return `<tr style="${{rowBg}}">
              <td><span class="b ${{recCls}}">${{rec}}</span></td>
              <td><a href="${{u.url}}" target="_blank" class="url-cell" title="${{u.url}}">${{u.slug}}</a></td>
              <td><span class="b" style="background:${{tc+'22'}};color:${{tc}}">${{u.type}}</span></td>
              <td>${{u.intent_primary?`<span class="b" style="background:${{ic+'22'}};color:${{ic}}">${{u.intent_primary}}</span>`:'<span style="color:var(--muted);font-size:10px">—</span>'}}</td>
              <td style="color:${{actionColor}};font-weight:${{isWinner?'600':'400'}}">${{u.action}}</td>
            </tr>`;
          }}).join('')}}</tbody>
        </table>
      </div>
    </div>`;
  }}).join('');
}}

// ============================================================================
// DUPLICATES TAB
// ============================================================================
registerLazy('duplicates',()=>{{
  const root=document.getElementById('duplicates-content');
  const sim=ENH.similarity||[];
  if(!sim.length){{ root.innerHTML=emptyState('No near-duplicates flagged','Run the enhancement pass to populate similarity scores.'); return; }}
  const convRisks=sim.filter(s=>s.conversion_risk).length;
  const exact=sim.filter(s=>s.similarity>=0.92).length;
  const high=sim.filter(s=>s.similarity>=0.80&&s.similarity<0.92).length;
  root.innerHTML=`
    <div class="stats" style="grid-template-columns:repeat(4,1fr)">
      <div class="stat"><div class="v" style="color:var(--red)">${{convRisks}}</div><div class="l" data-tip="Blog/info competing against service/money page">Conversion Risks</div></div>
      <div class="stat"><div class="v" style="color:var(--red)">${{exact}}</div><div class="l">Near-Identical 92%+</div></div>
      <div class="stat"><div class="v" style="color:var(--yellow)">${{high}}</div><div class="l">Very Similar 80-92%</div></div>
      <div class="stat"><div class="v" style="color:var(--accent)">${{sim.length}}</div><div class="l">Total Pairs</div></div>
    </div>
    <p style="color:var(--muted);font-size:13px;margin-bottom:14px"><span class="b b-r">Conversion Risk</span> = a blog page competing against a service page for the same topic.</p>
    <div class="card" style="padding:0">
      <h3 style="padding:14px 18px 0">Pairs <button class="csv-btn" data-csv="similarity">Download CSV</button></h3>
      <div class="tw" style="border:none">
        <table id="sim-table">
          <thead><tr>
            <th class="sortable" data-sort="text">URL A</th><th>Type</th>
            <th class="sortable" data-sort="text">URL B</th><th>Type</th>
            <th class="sortable" data-sort="num">Sim</th><th>Action</th>
          </tr></thead>
          <tbody>${{sim.map(s=>{{
            const rowBg=s.conversion_risk?'background:rgba(239,68,68,0.05);':'';
            const ta=s.type_a||'blog', tb=s.type_b||'blog';
            return `<tr style="${{rowBg}}">
              <td class="url-cell" title="${{s.url_a}}" style="font-size:12px">${{s.url_a}}</td>
              <td><span class="b" style="background:${{(typeColor[ta]||'#6b7280')+'22'}};color:${{typeColor[ta]||'#6b7280'}}">${{ta}}</span></td>
              <td class="url-cell" title="${{s.url_b}}" style="font-size:12px">${{s.url_b}}</td>
              <td><span class="b" style="background:${{(typeColor[tb]||'#6b7280')+'22'}};color:${{typeColor[tb]||'#6b7280'}}">${{tb}}</span></td>
              <td style="color:${{s.conversion_risk?'#ef4444':s.similarity>=0.92?'#ef4444':'#eab308'}};font-weight:700">${{(s.similarity*100).toFixed(0)}}%</td>
              <td style="font-size:11px;color:${{s.conversion_risk?'var(--red)':'var(--muted)'}};font-weight:${{s.conversion_risk?'600':'400'}}">${{s.action}}</td></tr>`;
          }}).join('')}}</tbody>
        </table>
      </div>
    </div>`;
  makeSortable('sim-table');
}});

// ============================================================================
// THIN CONTENT TAB — categorized by content type, prioritized, sortable
// ============================================================================
registerLazy('thin',()=>{{
  const root=document.getElementById('thin-content');
  const groups=THIN_GROUPS||[];
  const total=groups.reduce((a,g)=>a+(g.count||0),0);
  if(!total){{ root.innerHTML=emptyState('No thin content flagged','All pages meet the word count threshold (or are correctly classified as intentionally thin).'); return; }}

  // Per-group sort state. Keys: groupIdx -> {{by:'words'|'url', dir:'asc'|'desc'}}
  const sortState={{}};
  // Default each group to sort by word count ascending (the most painful first)
  groups.forEach((g,i)=>{{ sortState[i]={{by:'words',dir:'asc'}}; }});

  const priorityColor={{1:'var(--red)',2:'var(--yellow)',3:'var(--accent)',4:'var(--muted)',5:'var(--muted)'}};
  const priorityLabel={{1:'P1 fix first',2:'P2',3:'P3',4:'P4',5:'P5 low priority'}};

  function sortPages(pages, by, dir){{
    const arr=pages.slice();
    arr.sort((a,b)=>{{
      let av,bv;
      if(by==='words'){{ av=a.word_count||0; bv=b.word_count||0; return dir==='asc'?av-bv:bv-av; }}
      av=(a.slug||a.url||'').toLowerCase();
      bv=(b.slug||b.url||'').toLowerCase();
      return dir==='asc'?av.localeCompare(bv):bv.localeCompare(av);
    }});
    return arr;
  }}

  // Expose handler globally so inline onclick can call it (avoids the
  // bubble-vs-stopPropagation race with the parent .card[onclick="this.classList.toggle('open')"]).
  window._tamThinSort=function(gi,by,evt){{
    if(evt){{ evt.stopPropagation(); evt.preventDefault(); }}
    const cur=sortState[gi];
    if(cur.by===by){{ cur.dir=cur.dir==='asc'?'desc':'asc'; }}
    else{{ cur.by=by; cur.dir='asc'; }}
    rerender();
  }};

  function renderGroup(g, i){{
    const st=sortState[i];
    const sorted=sortPages(g.pages, st.by, st.dir);
    const arrow=(active)=>active?(st.dir==='asc'?'↑':'↓'):'';
    const wordsActive=st.by==='words', urlActive=st.by==='url';
    const rows=sorted.map(d=>`
      <div style="display:grid;grid-template-columns:1fr 60px 2fr;gap:12px;padding:8px 0;border-bottom:1px solid var(--border);align-items:center">
        <a href="${{d.url}}" target="_blank" class="url-cell" title="${{d.url}}" style="font-size:12px">${{d.slug||stripUrl(d.url)}}</a>
        <span style="font-size:12px;color:${{(d.word_count||0)<100?'var(--red)':(d.word_count||0)<200?'var(--orange)':'var(--yellow)'}};font-weight:600;text-align:center">${{d.word_count||0}}w</span>
        <span style="font-size:12px;color:var(--muted)">${{d.recommendation||''}}</span>
      </div>`).join('');
    const pcol=priorityColor[g.priority]||'var(--muted)';
    return `<div class="card expand" onclick="this.classList.toggle('open')" style="border-left:3px solid ${{pcol}}">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
        <h3 style="margin:0;display:flex;align-items:center;gap:10px">
          <span class="b" style="background:${{pcol}}22;color:${{pcol}}">${{g.count}}</span>
          ${{g.label}}
          <span style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.5px">${{priorityLabel[g.priority]||''}}</span>
        </h3>
        <div style="display:flex;gap:6px;align-items:center">
          <span style="font-size:11px;color:var(--muted);text-transform:uppercase">Sort:</span>
          <button onclick="_tamThinSort(${{i}},'words',event)" style="padding:3px 10px;font-size:11px;cursor:pointer;border-radius:14px;border:1px solid var(--accent);color:var(--accent);background:${{wordsActive?'var(--accent-soft)':'transparent'}}">Words ${{arrow(wordsActive)}}</button>
          <button onclick="_tamThinSort(${{i}},'url',event)" style="padding:3px 10px;font-size:11px;cursor:pointer;border-radius:14px;border:1px solid var(--accent);color:var(--accent);background:${{urlActive?'var(--accent-soft)':'transparent'}}">URL ${{arrow(urlActive)}}</button>
          <span class="expand-arrow">▶</span>
        </div>
      </div>
      <div class="expand-body">${{rows}}</div>
    </div>`;
  }}

  function rerender(){{
    root.innerHTML=`
      <div class="stats" style="grid-template-columns:repeat(auto-fit,minmax(120px,1fr))">
        ${{groups.map(g=>{{
          const pcol=priorityColor[g.priority]||'var(--muted)';
          return `<div class="stat"><div class="v" style="color:${{pcol}}">${{g.count}}</div><div class="l">${{g.label}}</div></div>`;
        }}).join('')}}
      </div>
      <p style="font-size:12px;color:var(--muted);margin-bottom:14px">Grouped by content purpose, ordered by priority. Blogs and case studies must have substantive content (P1). Service / industry pages need conversion-grade depth (P2). Lower-priority groups are catch-all utility pages — review whether each really needs to be indexed.</p>
      ${{groups.map((g,i)=>renderGroup(g,i)).join('')}}`;
  }}

  rerender();
}});

// ============================================================================
// INTENT TAB — donut + side list
// ============================================================================
registerLazy('intent',()=>{{
  const root=document.getElementById('intent-content');
  if(!ENH.intent){{ root.innerHTML=emptyState('No intent data','Run the enhancement pass.'); return; }}
  const iC={{informational:'#6366f1',commercial:'#3b82f6',transactional:'#22c55e',navigational:'#9ca3af'}};
  const ibc=ENH.intent_by_cluster||[];
  const iurls=ENH.intent_urls||{{}};
  // Mixed clusters = at least 30% non-dominant — these often hide cannibalization
  const mixedCount=ibc.filter(c=>c.mix_score>=0.30).length;
  root.innerHTML=`<div class="row row-2-1">
      <div class="card"><h3>Search Intent Distribution <span data-tip="What kind of query each page targets — informational (learn), commercial (compare/research), transactional (buy), navigational (find a page).">ⓘ</span></h3><div id="intent-chart"></div></div>
      <div class="card" id="intent-summary" style="display:flex;flex-direction:column;justify-content:center;font-size:14px;line-height:2"></div>
    </div>
    ${{ibc.length?`<div class="card" style="padding:0">
      <h3 style="padding:14px 18px 0">Intent by Cluster <span data-tip="Each cluster's dominant intent + mix. Mix score >0.30 = the cluster is split between intents (often a cannibalization signal — e.g., commercial service page competing with informational blog posts).">ⓘ</span> <span class="b b-y" style="margin-left:8px">${{mixedCount}} mixed-intent clusters</span></h3>
      <div class="tw" style="border:none">
        <table id="intent-cluster-table"><thead><tr>
          <th class="sortable" data-sort="text">Cluster</th>
          <th class="sortable" data-sort="num">URLs</th>
          <th class="sortable" data-sort="text">Dominant intent</th>
          <th class="sortable" data-sort="num">Mix score</th>
          <th>Breakdown</th>
        </tr></thead><tbody>${{ibc.map(c=>{{
          const cells=['informational','commercial','transactional','navigational'].map(int=>{{
            const n=c[int]||0;if(!n) return '';
            const pct=(n/c.url_count*100);
            return `<span class="b" style="background:${{iC[int]}}22;color:${{iC[int]}};margin-right:4px">${{int.slice(0,4)}} ${{n}} <span style="opacity:0.7">(${{pct.toFixed(0)}}%)</span></span>`;
          }}).filter(Boolean).join('');
          const mixCol=c.mix_score>=0.40?'var(--red)':c.mix_score>=0.25?'var(--yellow)':'var(--muted)';
          return `<tr><td>${{c.cluster_name}}</td><td>${{c.url_count}}</td><td><span class="b" style="background:${{iC[c.dominant_intent]}}22;color:${{iC[c.dominant_intent]}}">${{c.dominant_intent}}</span></td><td style="color:${{mixCol}};font-weight:700">${{c.mix_score.toFixed(2)}}</td><td>${{cells}}</td></tr>`;
        }}).join('')}}</tbody></table>
      </div>
    </div>`:''}}
    ${{Object.keys(iurls).length?`<div class="card" style="padding:0">
      <h3 style="padding:14px 18px 0">Top URLs by Intent <span data-tip="Strongest signals per intent. Useful for sanity-checking the classifier and spotting URLs assigned to the wrong intent.">ⓘ</span></h3>
      <div style="padding:14px 18px">${{['informational','commercial','transactional','navigational'].map(int=>{{
        const list=iurls[int]||[];if(!list.length) return '';
        return `<details style="margin-bottom:10px"><summary style="cursor:pointer;padding:6px 0"><span class="b" style="background:${{iC[int]}}22;color:${{iC[int]}}">${{int}}</span> <strong style="margin-left:8px">${{list.length}} sample URLs</strong></summary>
          <table style="margin-top:8px"><thead><tr><th>URL</th><th>Confidence</th><th>Signals</th><th>Secondary intent</th></tr></thead><tbody>${{list.map(u=>`<tr><td style="font-family:var(--mono);font-size:11px">${{u.url}}</td><td>${{u.confidence}}</td><td>${{u.signals}}</td><td><span style="color:var(--muted);font-size:11px">${{u.secondary||'—'}}</span></td></tr>`).join('')}}</tbody></table>
        </details>`;
      }}).join('')}}</div></div>`:''}}`;
  const iL=Object.keys(ENH.intent),iV=Object.values(ENH.intent);
  Plotly.newPlot('intent-chart',[{{type:'pie',labels:iL,values:iV,hole:0.6,textinfo:'percent',marker:{{colors:iL.map(l=>iC[l]||'#6b7280')}},textfont:{{size:12,color:'#fff'}}}}],
    {{...PL,height:260,showlegend:false,margin:{{t:10,b:10,l:10,r:10}}}},{{responsive:true,displayModeBar:false}});
  const tot=iV.reduce((a,b)=>a+b,0);
  document.getElementById('intent-summary').innerHTML=iL.map(l=>{{
    const pct=(ENH.intent[l]/tot*100);
    return `<div style="display:flex;align-items:center;gap:12px"><div style="width:120px"><strong style="color:${{iC[l]||'#6b7280'}};font-size:24px">${{ENH.intent[l]}}</strong><span style="color:var(--muted);font-size:12px;margin-left:4px">${{l}}</span></div><div style="flex:1;background:var(--border);height:6px;border-radius:3px;overflow:hidden"><div style="background:${{iC[l]}};height:100%;width:${{pct.toFixed(1)}}%"></div></div><span style="color:var(--muted);font-size:11px;min-width:40px">${{pct.toFixed(0)}}%</span></div>`;
  }}).join('');
  if(document.getElementById('intent-cluster-table')) makeSortable('intent-cluster-table');
}});

// ============================================================================
// FRESHNESS TAB
// ============================================================================
registerLazy('freshness',()=>{{
  const root=document.getElementById('freshness-content');
  if(!ENH.freshness && !ENH.freshness_finding && !ENH.content_inventory){{ root.innerHTML=emptyState('No freshness data','Provide sitemap URLs (--sitemap-url) so the analyzer can read lastmod dates.'); return; }}
  const finding=ENH.freshness_finding;
  const inv=ENH.content_inventory||[];
  const fO=['Fresh (< 1 month)','Recent (1-3 months)','Aging (3-6 months)','Stale (6-12 months)','Decaying (12+ months)'];
  const fC={{'Fresh (< 1 month)':'#22c55e','Recent (1-3 months)':'#4ade80','Aging (3-6 months)':'#eab308','Stale (6-12 months)':'#f97316','Decaying (12+ months)':'#ef4444'}};
  let html='';
  if(finding){{
    html+=`<div class="card" style="border-left:3px solid var(--yellow);padding:18px 22px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px"><span class="b b-y">DATA QUALITY</span><h3 style="margin:0">${{finding.title}}</h3></div>
      <p style="font-size:14px;line-height:1.6;color:var(--text);margin:8px 0 14px">${{finding.summary}}</p>
      <div style="font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px">Evidence</div>
      <ul style="font-size:13px;line-height:1.7;padding-left:20px;margin-bottom:14px">${{(finding.evidence||[]).map(e=>`<li>${{e}}</li>`).join('')}}</ul>
      <div style="font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px">Recommendation for ${{SITE_NAME}}</div>
      <p style="font-size:13px;line-height:1.6;color:var(--text);margin:0;padding:10px 14px;background:var(--surface-alt);border-radius:4px">${{finding.recommendation}}</p>
    </div>`;
  }}
  if(ENH.freshness){{
    html+=`<div class="card"><h3>Content Age Distribution <span data-tip="Based on sitemap lastmod or HTML article:published_time. When the source dates are uniform (CMS deploy timestamp), all URLs collapse into the youngest bucket — this is a data quality signal, not actual freshness.">ⓘ</span></h3><div id="freshness-chart"></div></div>`;
  }}
  if(inv.length){{
    const total=inv.reduce((a,b)=>a+b.count,0);
    html+=`<div class="card" style="padding:0">
      <h3 style="padding:14px 18px 0">Content Inventory <span data-tip="What kinds of pages does this site publish? URL-pattern-based classification — useful when freshness data is unavailable to still understand publishing structure.">ⓘ</span> <span class="b b-m" style="margin-left:8px">${{total}} URLs total</span></h3>
      <div class="tw" style="border:none"><table style="border:none"><thead><tr><th>Category</th><th>URLs</th><th style="width:50%">Share</th></tr></thead><tbody>${{inv.map(r=>{{
        const pct=(r.count/total*100).toFixed(1);
        return `<tr><td>${{r.category}}</td><td><strong>${{r.count}}</strong></td><td><div style="display:flex;align-items:center;gap:10px"><div style="flex:1;background:var(--border);height:8px;border-radius:4px;overflow:hidden"><div style="background:var(--accent);height:100%;width:${{pct}}%"></div></div><span style="color:var(--muted);font-size:11px;min-width:46px">${{pct}}%</span></div></td></tr>`;
      }}).join('')}}</tbody></table></div></div>`;
  }}
  root.innerHTML=html||emptyState('No freshness data','Provide sitemap URLs with lastmod or article:published_time meta tags.');
  if(ENH.freshness && document.getElementById('freshness-chart')){{
    const fL=fO.filter(k=>ENH.freshness[k]),fV=fL.map(k=>ENH.freshness[k]||0);
    Plotly.newPlot('freshness-chart',[{{type:'bar',y:fL.slice().reverse(),x:fV.slice().reverse(),orientation:'h',
      marker:{{color:fL.slice().reverse().map(l=>fC[l])}},text:fV.slice().reverse(),textposition:'outside',textfont:{{color:'#9ca3af',size:12}}}}],
      {{...PL,height:240,margin:{{t:10,b:20,l:200,r:60}},xaxis:{{gridcolor:'#2a2d3a'}},yaxis:{{tickfont:{{size:13,color:'#e4e4e7'}}}}}},
      {{responsive:true,displayModeBar:false}});
  }}
}});

// ============================================================================
// BRAND VOICE TAB — radial gauge + table
// ============================================================================
registerLazy('brand',()=>{{
  const root=document.getElementById('brand-content');
  // Profile-only fallback: when per-URL scores aren't available but the LLM brand
  // profile is, render the profile so the tab still has substance.
  if(!ENH.brand && ENH.brand_profile){{
    const p=ENH.brand_profile;
    const tones=(p.tone||[]).map(t=>`<span class="b" style="background:var(--accent)22;color:var(--accent);margin-right:6px;margin-bottom:6px;display:inline-block">${{t}}</span>`).join('');
    const dos=(p.do||[]).map(d=>`<li>${{d}}</li>`).join('');
    const donts=(p.dont||[]).map(d=>`<li>${{d}}</li>`).join('');
    const exs=(p.example_phrases||[]).map(e=>`<blockquote style="margin:6px 0;padding:8px 14px;border-left:2px solid var(--accent);background:var(--surface-alt);font-style:italic;font-size:13px">"${{e}}"</blockquote>`).join('');
    const ws=p.writing_style||{{}};
    const styleRows=Object.entries(ws).map(([k,v])=>`<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border);font-size:13px"><span style="color:var(--muted);text-transform:capitalize">${{k.replace(/_/g,' ')}}</span><strong>${{v}}</strong></div>`).join('');
    root.innerHTML=`<div class="card" style="border-left:3px solid var(--accent);padding:18px 22px">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px"><span class="b b-b">PROFILE</span><h3 style="margin:0">${{p.brand_name||SITE_NAME}} Brand Voice</h3></div>
        <p style="color:var(--muted);font-size:13px;margin-bottom:14px">LLM-derived from the site's actual content (auto-generated when no PDF guideline is provided). This drives the per-cluster content recommendations in the Topic Clusters tab.</p>
        <div style="margin-bottom:18px"><h4 style="font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:var(--muted);margin-bottom:8px">Audience</h4>
          <p style="font-size:14px;line-height:1.6;margin:0">${{p.audience||'Not specified.'}}</p></div>
        <div style="margin-bottom:18px"><h4 style="font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:var(--muted);margin-bottom:8px">Tone descriptors</h4>
          <div>${{tones||'<span style="color:var(--muted)">none</span>'}}</div></div>
        <div class="row row-2-1" style="margin-bottom:18px">
          <div><h4 style="font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:var(--green);margin-bottom:8px">Do</h4><ul style="font-size:13px;line-height:1.7;padding-left:20px;margin:0">${{dos||'<li style="color:var(--muted)">none</li>'}}</ul></div>
          <div><h4 style="font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:var(--red);margin-bottom:8px">Don't</h4><ul style="font-size:13px;line-height:1.7;padding-left:20px;margin:0">${{donts||'<li style="color:var(--muted)">none</li>'}}</ul></div>
        </div>
        ${{exs?`<div style="margin-bottom:18px"><h4 style="font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:var(--muted);margin-bottom:8px">Example phrases (extracted from site)</h4>${{exs}}</div>`:''}}
        ${{styleRows?`<div><h4 style="font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:var(--muted);margin-bottom:8px">Writing style</h4>${{styleRows}}</div>`:''}}
      </div>
      <div class="card" style="padding:14px 18px"><h3 style="margin-top:0">Per-URL scoring not yet run</h3>
        <p style="color:var(--muted);font-size:13px;margin:0">To score every URL against this profile (which pages are most/least on-brand), enable per-URL brand voice scoring in the next pipeline run. The profile shown above already drives the Topic Clusters tab's per-cluster content recommendations (tone, angle, CTA style).</p></div>`;
    return;
  }}
  if(!ENH.brand){{ root.innerHTML=emptyState('No brand voice data','Pass --brand-voice <pdf> on the next run to enable this section.'); return; }}
  root.innerHTML=`<div class="row row-2-1">
    <div class="card"><h3>Brand Voice Distribution</h3><div id="brand-chart"></div></div>
    <div class="card" style="display:flex;flex-direction:column;justify-content:center;align-items:center"><div id="brand-gauge"></div></div>
  </div>
  <div class="card" style="padding:0"><h3 style="padding:14px 18px 0">Lowest Scoring Pages <button class="csv-btn" data-csv="brand">Download CSV</button></h3>
    <div class="tw" style="border:none"><table id="brand-table"><thead><tr>
      <th class="sortable" data-sort="text">URL</th><th class="sortable" data-sort="num">Score</th>
      <th class="sortable" data-sort="text">Rating</th><th>Tone Match</th><th>Violations</th>
    </tr></thead><tbody></tbody></table></div></div>`;

  // Distribution donut
  const bL=Object.keys(ENH.brand.distribution),bV=Object.values(ENH.brand.distribution);
  const bC={{'On-brand':'#22c55e','Partially aligned':'#eab308','Needs work':'#f97316','Off-brand':'#ef4444'}};
  Plotly.newPlot('brand-chart',[{{type:'pie',labels:bL,values:bV,hole:0.6,textinfo:'label+percent',
    marker:{{colors:bL.map(l=>bC[l]||'#6b7280')}},textfont:{{size:12}}}}],
    {{...PL,height:260,showlegend:false,margin:{{t:10,b:10,l:10,r:10}}}},{{responsive:true,displayModeBar:false}});

  // Radial gauge
  Plotly.newPlot('brand-gauge',[{{
    type:'indicator',mode:'gauge+number',value:ENH.brand.avg_score,
    number:{{font:{{size:42,color:'#e4e4e7'}}}},
    gauge:{{
      axis:{{range:[0,100],tickfont:{{color:'#9ca3af'}}}},
      bar:{{color:'#6366f1'}},
      bgcolor:'#0f1117', borderwidth:0,
      steps:[
        {{range:[0,25],color:'rgba(239,68,68,0.25)'}},
        {{range:[25,50],color:'rgba(249,115,22,0.25)'}},
        {{range:[50,75],color:'rgba(234,179,8,0.25)'}},
        {{range:[75,100],color:'rgba(34,197,94,0.25)'}}
      ],
      threshold:{{line:{{color:'#fff',width:2}},thickness:0.75,value:ENH.brand.avg_score}}
    }}
  }}],{{...PL,height:200,margin:{{t:30,b:10,l:30,r:30}}}},{{responsive:true,displayModeBar:false}});

  document.querySelector('#brand-table tbody').innerHTML=ENH.brand.bottom.map(b=>`<tr>
    <td class="url-cell" title="${{b.url}}" style="font-size:12px">${{b.url}}</td>
    <td style="font-weight:700;color:${{b.brand_score<25?'#ef4444':b.brand_score<50?'#f97316':'#eab308'}}">${{b.brand_score}}</td>
    <td><span class="b ${{b.rating==='Off-brand'?'b-r':b.rating==='Needs work'?'b-y':'b-b'}}">${{b.rating}}</span></td>
    <td style="font-size:11px;color:var(--muted)">${{b.tone_matches||'none'}}</td>
    <td style="font-size:11px;color:var(--muted)">${{b.violations||'none'}}</td>
  </tr>`).join('');
  makeSortable('brand-table');
}});

// ============================================================================
// COMPETITORS TAB
// ============================================================================
registerLazy('competitors',()=>{{
  const root=document.getElementById('competitors-content');
  if(!ENH.competitor){{ root.innerHTML=emptyState('No competitor data','Re-run with <code>--competitor &lt;domain&gt;</code> to populate this tab.'); return; }}
  const stats=ENH.comp_stats||{{advantages:0,shared:0,gaps:0}};
  const compRows=ENH.competitor.rows||[];
  const compNames=ENH.competitor.names||[];
  const compTh=compNames.map(n=>`<th class="sortable" data-sort="text">${{n}}</th>`).join('');
  const perComp=ENH.competitor.per_competitor||[];
  const perCompCards=perComp.map(p=>{{
    const topGaps=(p.top_gap_topics||[]).slice(0,3).map(t=>`<div style="font-size:11px;color:var(--muted);margin-top:2px;line-height:1.5">• ${{t}}</div>`).join('');
    return `<div class="card" style="padding:14px 16px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px"><strong style="font-size:13px;text-transform:capitalize">${{p.name}}</strong></div>
      <div style="display:flex;gap:14px;font-size:11px;margin-bottom:8px">
        <div><span style="color:var(--red);font-weight:700;font-size:18px">${{p.gaps}}</span> <span style="color:var(--muted)">gaps</span></div>
        <div><span style="color:var(--blue);font-weight:700;font-size:18px">${{p.shared}}</span> <span style="color:var(--muted)">shared</span></div>
        <div><span style="color:var(--green);font-weight:700;font-size:18px">${{p.advantages}}</span> <span style="color:var(--muted)">adv</span></div>
      </div>
      ${{topGaps?`<div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.5px;margin-top:6px">Top gaps</div>${{topGaps}}`:''}}
    </div>`;
  }}).join('');
  root.innerHTML=`<div class="stats" style="grid-template-columns:repeat(3,1fr)">
      <div class="stat"><div class="v" style="color:var(--green)">${{stats.advantages}}</div><div class="l">${{SITE_NAME}} Advantages</div></div>
      <div class="stat"><div class="v" style="color:var(--blue)">${{stats.shared}}</div><div class="l">Shared Topics</div></div>
      <div class="stat"><div class="v" style="color:var(--red)">${{stats.gaps}}</div><div class="l">Content Gaps</div></div>
    </div>
    ${{perCompCards?`<div style="margin-bottom:14px"><h3 style="margin-bottom:10px">Breakdown by Competitor <span data-tip="Per-competitor topic coverage. \\'Gaps\\' = topics this competitor covers that ${{SITE_NAME}} does not. \\'Adv\\' = topics ${{SITE_NAME}} owns that this competitor doesn\\'t cover.">ⓘ</span></h3>
      <div class="stats" style="grid-template-columns:repeat(${{Math.min(perComp.length,4)}},1fr);gap:12px">${{perCompCards}}</div></div>`:''}}
    <div class="card"><div id="comp-chart"></div></div>
    <input type="text" class="srch" id="comp-search" placeholder="Search topics...">
    <div class="card" style="padding:0">
      <h3 style="padding:14px 18px 0">Topic Coverage Matrix <button class="csv-btn" data-csv="competitor">Download CSV</button></h3>
      <div class="tw" style="border:none">
        <table id="comp-table"><thead><tr>
          <th class="sortable" data-sort="text">Topic</th>
          <th class="sortable" data-sort="text">${{SITE_NAME}}</th>
          ${{compTh}}
          <th class="sortable" data-sort="text">Status</th>
        </tr></thead><tbody></tbody></table>
      </div>
    </div>`;
  const cG={{}}; compRows.forEach(c=>{{cG[c.status]=(cG[c.status]||0)+1;}});
  Plotly.newPlot('comp-chart',[{{type:'bar',y:Object.keys(cG),x:Object.values(cG),orientation:'h',
    marker:{{color:Object.keys(cG).map(k=>k==='GAP'?'#ef4444':k==='ADVANTAGE'?'#22c55e':'#6366f1')}},
    text:Object.values(cG),textposition:'outside',textfont:{{color:'#9ca3af',size:11}}}}],
    {{...PL,height:140,margin:{{t:5,b:20,l:120,r:50}},yaxis:{{tickfont:{{size:12,color:'#e4e4e7'}}}},xaxis:{{gridcolor:'#2a2d3a'}}}},
    {{responsive:true,displayModeBar:false}});
  function renderComp(f=''){{
    const fl=f.toLowerCase(),rows=compRows.filter(c=>!fl||c.topic.toLowerCase().includes(fl));
    document.querySelector('#comp-table tbody').innerHTML=rows.map(c=>{{
      const compCells=compNames.map(n=>`<td>${{c.competitors&&c.competitors[n]?'Y':''}}</td>`).join('');
      const statusCls=c.status==='GAP'?'b-r':c.status==='ADVANTAGE'?'b-g':'b-b';
      return `<tr><td>${{c.topic}}</td><td>${{c.target?'Y':''}}</td>${{compCells}}<td><span class="b ${{statusCls}}">${{c.status}}</span></td></tr>`;
    }}).join('');
  }}
  renderComp();
  makeSortable('comp-table');
  document.getElementById('comp-search').addEventListener('input',debounce(e=>renderComp(e.target.value),150));
}});

// ============================================================================
// CONTENT IDEAS TAB
// ============================================================================
registerLazy('ideas',()=>{{
  const root=document.getElementById('ideas-content');
  if(!ENH.content_ideas||!ENH.content_ideas.length){{
    root.innerHTML=emptyState('No content ideas yet','Re-run with <code>--competitor &lt;domain&gt;</code>. Briefs are derived from gap topics.');
    return;
  }}
  const ideas=ENH.content_ideas;
  const stats=ENH.content_ideas_stats||{{total:ideas.length,p1:0,p2:0,p3:0}};
  root.innerHTML=`<div class="stats" style="grid-template-columns:repeat(4,1fr)">
      <div class="stat"><div class="v" style="color:var(--accent)">${{stats.total}}</div><div class="l">Total Briefs</div></div>
      <div class="stat"><div class="v" style="color:var(--red)">${{stats.p1}}</div><div class="l" data-tip="Validated by 2+ competitors — strongest demand signal">P1 (multi-validated)</div></div>
      <div class="stat"><div class="v" style="color:var(--yellow)">${{stats.p2}}</div><div class="l">P2</div></div>
      <div class="stat"><div class="v" style="color:var(--blue)">${{stats.p3}}</div><div class="l">P3</div></div>
    </div>
    <p style="color:var(--muted);font-size:13px;margin-bottom:14px">Hand-off-ready content briefs derived from competitor gap analysis. Click to expand. <button class="csv-btn" data-csv="ideas" style="margin-left:8px">Download all as CSV</button></p>
    <input type="text" class="srch" id="idea-search" placeholder="Search briefs by title, topic, or content type...">
    <div id="idea-list"></div>`;
  function renderIdeas(f=''){{
    const fl=f.toLowerCase();
    const rows=ideas.filter(i=>!fl||(i.title||'').toLowerCase().includes(fl)||(i.gap_topic||'').toLowerCase().includes(fl)||(i.content_type||'').toLowerCase().includes(fl));
    document.getElementById('idea-list').innerHTML=rows.map(i=>{{
      const pcls=i.priority==='P1'?'b-r':i.priority==='P2'?'b-y':'b-b';
      const ic=intentColor[i.intent]||'#6366f1';
      const kws=Array.isArray(i.suggested_keywords)?i.suggested_keywords:[];
      const qs=Array.isArray(i.key_questions)?i.key_questions:[];
      const safeTitle=(i.title||'').replace(/'/g,"\\\\'");
      const seoSrc=i.seo_data_source||'none';
      const sv=i.search_volume||'—';
      const kd=i.keyword_difficulty||'—';
      const pk=i.parent_keyword||'';
      const spoke=i.spoke_cluster||'';
      const spokeSim=i.spoke_similarity||'';
      return `<div class="card expand" onclick="this.classList.toggle('open')" style="cursor:pointer">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:16px">
          <div style="flex:1">
            <div style="display:flex;gap:8px;align-items:center;margin-bottom:6px;flex-wrap:wrap">
              <span class="b ${{pcls}}">${{i.priority}}</span>
              <span class="b" style="background:${{ic+'22'}};color:${{ic}}">${{i.content_type}}</span>
              <span class="b b-m">${{i.est_word_count}}w</span>
              <span style="font-size:11px;color:var(--muted)">covered by: ${{i.covered_by}}</span>
              <span style="font-size:11px;color:var(--accent);cursor:pointer" onclick="event.stopPropagation();copy('${{safeTitle}}')">⎘ copy title</span>
            </div>
            <strong style="font-size:14px;line-height:1.4">${{i.title}}</strong>
            <div style="font-size:12px;color:var(--muted);margin-top:4px">Gap topic: <em>${{i.gap_topic}}</em> · Audience: ${{i.target_audience}}</div>
            ${{spoke?`<div style="font-size:11px;color:var(--accent);margin-top:4px" data-tip="Closest existing cluster on your site. Link this new piece from that cluster's pillar page so it joins an existing topical hub instead of starting one from scratch.">▶ Spoke off existing cluster: <strong>${{spoke}}</strong>${{spokeSim?` <span style="color:var(--muted)">(similarity ${{spokeSim}})</span>`:''}}</div>`:'<div style="font-size:11px;color:var(--muted);margin-top:4px">▶ No matching existing cluster — this would start a new topical hub.</div>'}}
          </div>
          <span class="expand-arrow" style="margin-top:8px">▶</span>
        </div>
        <div class="expand-body">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px">
            <div>
              <h4 style="font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:var(--muted);margin-bottom:6px">Target keywords</h4>
              <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px">${{kws.map(k=>`<span class="b b-b">${{k}}</span>`).join('')}}</div>
              <h4 style="font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:var(--muted);margin-bottom:6px;display:flex;align-items:center;gap:8px">
                SEO data
                <span class="b b-m" style="font-size:9px;text-transform:none" data-tip="No keyword DB integration enabled. Wire Ahrefs / DataForSEO / GKP via the SEO API hook to populate volume + difficulty + parent keyword.">source: ${{seoSrc}}</span>
              </h4>
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px">
                <div><span style="color:var(--muted)">Volume:</span> <strong>${{sv}}</strong></div>
                <div><span style="color:var(--muted)">KD:</span> <strong>${{kd}}</strong></div>
                <div style="grid-column:1/-1"><span style="color:var(--muted)">Parent kw:</span> <strong>${{pk||'—'}}</strong></div>
              </div>
            </div>
            <div>
              <h4 style="font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:var(--muted);margin-bottom:6px">Key questions to answer</h4>
              <ul style="font-size:12px;line-height:1.7;padding-left:18px;color:var(--text)">${{qs.map(q=>`<li>${{q}}</li>`).join('')}}</ul>
            </div>
          </div>
        </div>
      </div>`;
    }}).join('');
  }}
  renderIdeas();
  document.getElementById('idea-search').addEventListener('input',debounce(e=>renderIdeas(e.target.value),150));
}});

// ============================================================================
// VECTOR MAP TAB — 2D embedding projection per URL (one dot = one URL)
// ============================================================================
registerLazy('vmap',()=>{{
  const root=document.getElementById('vmap-chart');
  const points=(VECTOR_MAP&&VECTOR_MAP.points)||[];
  if(!points.length){{ root.innerHTML=emptyState('No vector map data','Run a full pipeline (no --skip-pipeline) to build the embedding projection.'); return; }}

  // Group by cluster_id so we can color-code + show a legend
  const byCluster={{}};
  points.forEach(p=>{{
    const k=p.cluster_id;
    if(!byCluster[k]) byCluster[k]={{name:p.cluster_name||('Cluster '+k),x:[],y:[],urls:[],intent:[],ptype:[]}};
    byCluster[k].x.push(p.x); byCluster[k].y.push(p.y);
    byCluster[k].urls.push(p.url); byCluster[k].intent.push(p.intent||''); byCluster[k].ptype.push(p.page_type||'');
  }});

  const palette=['#6366f1','#8b5cf6','#3b82f6','#22c55e','#eab308','#ef4444','#f97316','#06b6d4','#a78bfa','#84cc16','#ec4899','#14b8a6','#f59e0b','#10b981','#6b7280'];
  const traces=Object.entries(byCluster).map(([cid,g],i)=>{{
    const isOrphan=parseInt(cid)===-1;
    const color=isOrphan?'#4b5563':palette[i%palette.length];
    return {{
      type:'scattergl',mode:'markers',name:g.name,
      x:g.x,y:g.y,
      text:g.urls.map((u,idx)=>{{ const slug=stripUrl(u); const intent=g.intent[idx]?` · ${{g.intent[idx]}}`:''; const pt=g.ptype[idx]?` · ${{g.ptype[idx]}}`:''; return `<b>${{g.name}}</b><br>${{slug}}${{pt}}${{intent}}`; }}),
      hovertemplate:'%{{text}}<extra></extra>',
      marker:{{size:isOrphan?5:8,color:color,line:{{width:0.5,color:'#0f1117'}},opacity:isOrphan?0.5:0.85}},
    }};
  }});
  Plotly.newPlot('vmap-chart',traces,{{
    ...PL,height:520,
    margin:{{t:10,b:10,l:10,r:10}},
    xaxis:{{showgrid:false,zeroline:false,showticklabels:false}},
    yaxis:{{showgrid:false,zeroline:false,showticklabels:false}},
    showlegend:true,legend:{{font:{{size:11,color:'#e4e4e7'}},bgcolor:'rgba(0,0,0,0)',orientation:'v'}},
    hovermode:'closest',
  }},{{responsive:true,displayModeBar:false}});
}});

// ============================================================================
// ASK THE AUDIT TAB — RAG Q&A (pre-rendered at build time)
// ============================================================================
registerLazy('ask',()=>{{
  const root=document.getElementById('ask-content');
  const examples=ASK_EXAMPLES||[];
  const intro=`<div class="card">
    <h3>Ask the Audit <span data-tip="Same FAISS index that drove cluster discovery during the audit is reused as a RAG retrieval store. The pipeline produces this side-effect-free.">ⓘ</span></h3>
    <p style="font-size:13px;color:var(--muted);margin-bottom:8px">During the audit we build a vector index of every page chunk for clustering. That same index doubles as a <strong>RAG retrieval store</strong> — meaning you can ask questions about your own content and get grounded answers with citations.</p>
    <p style="font-size:13px;color:var(--muted);margin-bottom:14px"><strong>One artifact, two jobs.</strong> Audit runs once a quarter; Q&amp;A is daily.</p>
    <div style="background:var(--surface-alt);border:1px solid var(--border);border-radius:8px;padding:12px;font-family:ui-monospace,SF Mono,Menlo,monospace;font-size:12px;color:var(--text)">
      <span style="color:var(--muted)">$</span> python -m src.site_chat <span style="color:var(--green)">"What does our site say about activation rate benchmarks?"</span>
    </div>
    <p style="font-size:11px;color:var(--muted);margin-top:8px">Add <code style="background:var(--surface-alt);padding:1px 6px;border-radius:3px">--json</code> for machine-readable output. Costs ~$0.001/question with Claude Haiku.</p>
  </div>`;

  if(!examples.length){{
    root.innerHTML=intro+emptyState('No pre-rendered examples','Re-run the pipeline with <code>--use-llm</code> and ANTHROPIC_API_KEY set to embed sample Q&amp;A in the dashboard.');
    return;
  }}

  function renderExample(ex,i){{
    const cites=(ex.citations||[]).map(c=>`<li><a href="${{c.url}}" target="_blank" style="font-size:12px">[${{c.n}}] ${{stripUrl(c.url)}}</a><div style="font-size:11px;color:var(--muted);margin-left:18px;font-style:italic">${{(c.snippet||'').replace(/[<>]/g,'')}}</div></li>`).join('');
    const answerHtml=(ex.answer||'').split(/\\n\\n+/).map(p=>`<p style="margin:0 0 10px 0">${{p.replace(/\\n/g,'<br>')}}</p>`).join('');
    return `<div class="card">
      <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px">Sample Q${{i+1}} — pre-rendered at build time</div>
      <div style="font-weight:600;font-size:15px;margin-bottom:10px;color:var(--text)">${{ex.q}}</div>
      <div style="font-size:13px;line-height:1.6;color:var(--text)">${{answerHtml}}</div>
      <div style="margin-top:12px;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px">Sources (${{ex.used_chunks||0}} chunks retrieved)</div>
      <ul style="padding-left:18px;margin:0">${{cites}}</ul>
    </div>`;
  }}

  root.innerHTML=intro+examples.map(renderExample).join('');
}});

// ============================================================================
// RECOMMEND AGENT TAB — pre-rendered latest run trace
// ============================================================================
registerLazy('agent',()=>{{
  const root=document.getElementById('agent-content');
  const intro=`<div class="card">
    <h3>Recommendation Agent <span data-tip="A real agent (not a function call) — Sonnet 4.6 with 10 tools over the audit data + RAG retrieval. Includes self-critique pass + a learning loop that records lessons to memory after every run.">ⓘ</span></h3>
    <p style="font-size:13px;color:var(--muted);margin-bottom:8px">Built on top of the audit, not inside it. The pipeline produces structured artifacts; this agent treats them as a toolset to answer real operator questions like <em>"What should we publish next month?"</em></p>
    <p style="font-size:13px;color:var(--muted);margin-bottom:14px">After each run, a self-critique pass writes lessons to <code>runs/&lt;site&gt;/agent_lessons.md</code>. Future runs read the latest 30 — so the agent literally gets sharper over time.</p>
    <div style="background:var(--surface-alt);border:1px solid var(--border);border-radius:8px;padding:12px;font-family:ui-monospace,SF Mono,Menlo,monospace;font-size:12px;color:var(--text)">
      <span style="color:var(--muted)">$</span> python -m src.agent.recommend <span style="color:var(--green)">"What should we publish next month?"</span>
    </div>
    <p style="font-size:11px;color:var(--muted);margin-top:8px">Cost: ~$0.30-0.50/run with Claude Sonnet 4.6. Streams reasoning + tool calls live. Trace persisted to <code>runs/&lt;site&gt;/agent_runs/</code>.</p>
  </div>`;

  if(!AGENT_RUN){{
    root.innerHTML=intro+emptyState('No agent runs yet','Run <code>python -m src.agent.recommend "your question"</code> to capture a trace. The next dashboard render will show it here.');
    return;
  }}

  const r=AGENT_RUN;
  const final=r.final_recommendation||{{}};
  const actions=final.actions||[];
  const calls=r.tool_calls||[];

  // Action color by type
  const actionColors={{write:'var(--green)',refresh:'var(--yellow)',skip:'var(--muted)',investigate:'var(--accent)'}};

  function renderAction(a,i){{
    const color=actionColors[(a.action||'').toLowerCase()]||'var(--muted)';
    const label=(a.action||'').toUpperCase();
    const sources=(a.sources||[]).map(s=>`<code style="background:var(--surface-alt);padding:1px 5px;border-radius:3px;font-size:10px">${{s}}</code>`).join(' ');
    return `<div class="card" style="border-left:3px solid ${{color}}">
      <div style="display:flex;align-items:baseline;gap:10px;margin-bottom:6px;flex-wrap:wrap">
        <span class="b" style="background:${{color}}22;color:${{color}}">${{label}}</span>
        <strong style="font-size:14px">${{i+1}}. ${{a.title||'(no title)'}}</strong>
      </div>
      <div style="font-size:13px;color:var(--text);line-height:1.5;margin-bottom:8px">${{a.reason||''}}</div>
      ${{sources?`<div style="font-size:10px;color:var(--muted);margin-top:4px">Sources: ${{sources}}</div>`:''}}
    </div>`;
  }}

  function renderCall(c,i){{
    const args=JSON.stringify(c.arguments||{{}}).slice(0,150);
    const isFinal=c.name==='final_recommend';
    const isLesson=c.name==='note_lesson';
    const color=isFinal?'var(--green)':isLesson?'var(--yellow)':'var(--accent)';
    return `<div style="border-left:2px solid ${{color}};padding:6px 12px;margin-bottom:6px;font-size:12px;background:var(--surface-alt);border-radius:0 4px 4px 0">
      <div style="display:flex;justify-content:space-between"><strong style="color:${{color}}">${{i+1}}. ${{c.name}}</strong><span style="color:var(--muted);font-size:10px">${{(c.result_preview||'').length}} chars</span></div>
      <code style="font-size:10px;color:var(--muted);word-break:break-all">${{args}}</code>
    </div>`;
  }}

  const risksHtml=(final.risks||[]).map(r=>`<li>${{r}}</li>`).join('');

  root.innerHTML=intro+`
    <div class="card">
      <div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-bottom:8px">
        <strong>Latest run</strong>
        <span style="font-size:11px;color:var(--muted)">${{r.run_id}} · ${{r.model}} · ${{calls.length}} tool calls · ${{r.self_critique_lessons_captured||0}} lessons captured</span>
      </div>
      <div style="font-size:13px;color:var(--muted);margin-bottom:8px"><strong>Question:</strong> ${{r.question}}</div>
      <div style="font-size:13px;line-height:1.5;margin-bottom:6px"><strong>Summary:</strong> ${{final.summary||'(no summary)'}}</div>
      <div style="font-size:11px;color:var(--muted)">Confidence: <strong>${{(final.confidence||'unknown').toUpperCase()}}</strong></div>
    </div>
    <div style="display:grid;grid-template-columns:2fr 1fr;gap:14px">
      <div>
        <h3 style="font-size:13px;color:var(--muted);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:10px">Recommended Actions (${{actions.length}})</h3>
        ${{actions.map(renderAction).join('')||emptyState('No actions in this run')}}
        ${{risksHtml?`<div class="card" style="border-left:3px solid var(--orange)"><h3 style="margin-bottom:6px;color:var(--orange);font-size:12px">Risks &amp; caveats</h3><ul style="font-size:12px;line-height:1.7;padding-left:18px;color:var(--text)">${{risksHtml}}</ul></div>`:''}}
      </div>
      <div>
        <h3 style="font-size:13px;color:var(--muted);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:10px">Tool Trace</h3>
        ${{calls.map(renderCall).join('')}}
      </div>
    </div>`;
}});

// ============================================================================
// LESSONS TAB — read the agent_lessons.md ledger
// ============================================================================
registerLazy('lessons',()=>{{
  const root=document.getElementById('lessons-content');
  const intro=`<div class="card">
    <h3>Agent Lessons <span data-tip="Append-only markdown file at runs/<site>/agent_lessons.md. The latest 30 lessons get prepended to the agent's system prompt on every run, so it gets smarter over time.">ⓘ</span></h3>
    <p style="font-size:13px;color:var(--muted);margin-bottom:8px">After every recommendation run, the agent does a self-critique pass and writes lessons to memory. Operators can also append manual lessons via the feedback CLI.</p>
    <div style="background:var(--surface-alt);border:1px solid var(--border);border-radius:8px;padding:12px;font-family:ui-monospace,SF Mono,Menlo,monospace;font-size:11px;color:var(--text)">
      <div style="color:var(--muted)"># Reject a specific recommendation</div>
      <div><span style="color:var(--muted)">$</span> python -m src.agent.feedback --reject <span style="color:var(--green)">"What is PQL?"</span> --reason <span style="color:var(--green)">"already at /post/pql-guide"</span></div>
    </div>
    <p style="font-size:11px;color:var(--muted);margin-top:8px">The file is human-editable — fix wrong lessons or delete bad ones directly. The agent picks up your edits next run.</p>
  </div>`;

  if(!AGENT_LESSONS_MD||!AGENT_LESSONS_MD.trim()){{
    root.innerHTML=intro+emptyState('No lessons captured yet','Run the agent (<code>python -m src.agent.recommend</code>) — the self-critique pass will start populating the ledger.');
    return;
  }}

  // Render markdown crudely (we don't bundle a full markdown lib for file:// safety).
  // Convert ## -> h3, **bold** -> strong, _italic_ -> em, paragraphs by blank lines.
  function escape(s){{ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }}
  function md(s){{
    let out=escape(s);
    out=out.replace(/\\*\\*(.+?)\\*\\*/g,'<strong>$1</strong>');
    out=out.replace(/_([^_]+)_/g,'<em>$1</em>');
    out=out.replace(/`([^`]+)`/g,'<code style="background:var(--surface-alt);padding:1px 5px;border-radius:3px;font-size:11px">$1</code>');
    return out;
  }}
  const lines=AGENT_LESSONS_MD.split('\\n');
  let html='';
  let i=0;
  // Skip the intro until we hit the first ## entry
  while(i<lines.length&&!lines[i].startsWith('## ')) i++;
  // Render each lesson as a card
  while(i<lines.length){{
    if(!lines[i].startsWith('## ')){{ i++; continue; }}
    const header=lines[i].slice(3);
    i++;
    let body='';
    while(i<lines.length&&!lines[i].startsWith('## ')){{
      body+=lines[i]+'\\n';
      i++;
    }}
    const headerMd=md(header);
    const bodyHtml=body.split(/\\n\\n+/).map(p=>p.trim()).filter(Boolean).map(p=>`<p style="margin:0 0 8px 0">${{md(p)}}</p>`).join('');
    html+=`<div class="card"><div style="font-size:12px;color:var(--accent);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px">${{headerMd}}</div>${{bodyHtml}}</div>`;
  }}
  if(!html) html=emptyState('No parseable lessons found','Check the raw file at runs/&lt;site&gt;/agent_lessons.md');
  root.innerHTML=intro+html;
}});

// ============================================================================
// MERGES TAB
// ============================================================================
registerLazy('merges',()=>{{
  const root=document.getElementById('merges-content');
  if(!ENH.merges||!ENH.merges.length){{ root.innerHTML=emptyState('No merge candidates','Cluster centroids are well-separated.'); return; }}
  const mergeCount=ENH.merges.filter(m=>m.recommendation==='MERGE').length;
  const reviewCount=ENH.merges.length-mergeCount;
  root.innerHTML=`<p style="color:var(--muted);margin-bottom:14px;font-size:14px">Clusters with high topic overlap that should be combined to strengthen topical authority. Same-name pairs (where the LLM cluster-namer converged on the same label across two cluster IDs) are the strongest merge signal.</p>
    <div class="stats" style="grid-template-columns:repeat(2,1fr);margin-bottom:14px">
      <div class="stat"><div class="v" style="color:var(--red)">${{mergeCount}}</div><div class="l">MERGE candidates</div></div>
      <div class="stat"><div class="v" style="color:var(--yellow)">${{reviewCount}}</div><div class="l">REVIEW candidates</div></div>
    </div>
    <div class="card" style="padding:0"><h3 style="padding:14px 18px 0">Merge Candidates <button class="csv-btn" data-csv="merges">Download CSV</button></h3>
      <div class="tw" style="border:none"><table id="merge-table"><thead><tr>
        <th class="sortable" data-sort="text">Cluster A</th>
        <th class="sortable" data-sort="text">Cluster B</th>
        <th class="sortable" data-sort="num">Similarity</th>
        <th class="sortable" data-sort="num">Combined size</th>
        <th class="sortable" data-sort="text">Recommendation</th>
        <th>Reason</th>
      </tr></thead><tbody>${{ENH.merges.map(m=>{{
        const aSize=m.cluster_a_size||'';
        const bSize=m.cluster_b_size||'';
        const combined=m.combined_size||((m.cluster_a_size||0)+(m.cluster_b_size||0))||'';
        const aLabel=aSize?`${{m.cluster_a_name}} <span style="color:var(--muted);font-size:11px">(${{aSize}} URLs)</span>`:m.cluster_a_name;
        const bLabel=bSize?`${{m.cluster_b_name}} <span style="color:var(--muted);font-size:11px">(${{bSize}} URLs)</span>`:m.cluster_b_name;
        return `<tr>
          <td>${{aLabel}}</td>
          <td>${{bLabel}}</td>
          <td style="color:${{m.similarity>=0.85?'#ef4444':'#eab308'}};font-weight:700">${{(m.similarity*100).toFixed(0)}}%</td>
          <td><strong>${{combined||'—'}}</strong></td>
          <td><span class="b ${{m.recommendation==='MERGE'?'b-r':'b-y'}}">${{m.recommendation}}</span></td>
          <td style="font-size:11px;color:var(--muted)">${{m.reason||''}}</td>
        </tr>`;
      }}).join('')}}</tbody></table></div></div>`;
  makeSortable('merge-table');
}});

// ============================================================================
// URL EXPLORER
// ============================================================================
function renderUrlTable(filter=''){{
  const fl=filter.toLowerCase(),rows=URL_TABLE.filter(u=>!fl||u.url.toLowerCase().includes(fl)||(u.name&&u.name.toLowerCase().includes(fl))||((u.spoke_cluster||'').toLowerCase().includes(fl)));
  const ltd=rows.slice(0,200);
  const tbody=document.querySelector('#url-table tbody');
  tbody.innerHTML=ltd.map(u=>{{
    const spoke=u.spoke_cluster?`<span style="color:var(--accent)">${{u.spoke_cluster}}</span>`:'<span style="color:var(--muted);font-size:10px">—</span>';
    return `<tr>
      <td><a href="${{u.url}}" target="_blank" class="url-cell" title="${{u.url}}">${{stripUrl(u.url)}}</a></td>
      <td>${{u.cluster}}</td>
      <td>${{u.name||'<span style="color:var(--muted)">Unclustered</span>'}}</td>
      <td>${{spoke}}</td>
    </tr>`;
  }}).join('');
  if(rows.length>200) tbody.innerHTML+=`<tr><td colspan="4" style="color:var(--muted);text-align:center">Showing 200 of ${{rows.length}} — refine your search</td></tr>`;
}}

// ============================================================================
// BOOT
// ============================================================================
renderHero();
renderKeyFindings();
renderActionItems();
renderClusterTable();
renderCannib();
renderUrlTable();
makeSortable('cluster-table');
makeSortable('url-table');

document.getElementById('cluster-search').addEventListener('input',debounce(e=>renderClusterTable(e.target.value),150));
document.getElementById('cannib-search').addEventListener('input',debounce(e=>renderCannib(e.target.value),150));
document.getElementById('url-search').addEventListener('input',debounce(e=>renderUrlTable(e.target.value),150));

// Run lazy loaders for the active tab on first paint
runLazy('summary');

// Apply hash routing
applyHash();
</script>
</body>
</html>"""
