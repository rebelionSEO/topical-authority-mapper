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


def _js(obj) -> str:
    """JSON for an inline <script>; escapes '</' so data can't close the tag."""
    return json.dumps(obj).replace("</", "<\\/")


_EMPTY_VISUALS = {
    "urls": [], "clusters": {}, "pairs": [], "merges": [],
    "graph": {"nodes": [], "edges": [], "meta": {}},
    "overlap": {"threshold": 0.8, "clusters": []},
    "gaps": {"competitors": [], "rows": [], "counts": {}},
    "actions": [], "kpis": [], "findings": [],
}

# vis-network renders the force-directed Cluster Map. Pinned version, single CDN script.
_GRAPH_CDN = "https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"

# Views in the "More" menu: (tab id, label, one-line description). Order = menu order.
_MORE_TABS = [
    ("summary", "Health score", "Composite score and subscores"),
    ("clusters", "Topic clusters", "Treemap and full cluster table"),
    ("cannib", "Overlap by cluster", "Per-cluster page lists and verdicts"),
    ("duplicates", "Similar page pairs", "Every pair 80%+ alike"),
    ("thin", "Thin content", "Pages too short to rank"),
    ("intent", "Search intent", "What each page is trying to satisfy"),
    ("freshness", "Freshness", "How recently pages were updated"),
    ("brand", "Brand voice", "Tone alignment per page"),
    ("competitors", "Competitor table", "Topic coverage as a table"),
    ("ideas", "Content ideas", "Briefs generated from gaps"),
    ("merges", "Cluster merges", "Topics that may belong together"),
    ("vmap", "Vector map", "2D projection of page meaning"),
    ("ask", "Ask the audit", "Pre-rendered Q&A over your content"),
    ("agent", "Recommend agent", "Latest agent run trace"),
    ("lessons", "Agent lessons", "What the agent learned"),
]


_THEME_CSS = r"""
:root{
  --bg:#0a0c11; --bg-2:#0d1017; --surface:#121621; --surface-2:#171c29; --surface-alt:#0f131c;
  --border:#232a3a; --border-soft:#1a2030; --text:#e8eaf0; --muted:#8a93a6; --faint:#5b6478;
  --accent:#8b5cf6; --accent-soft:rgba(139,92,246,0.14);
  --red:#f04438; --amber:#f5a524; --green:#22c55e; --blue:#3b82f6;
  --yellow:var(--amber); --orange:var(--amber);
  --red-soft:rgba(240,68,56,0.13); --amber-soft:rgba(245,165,36,0.13); --green-soft:rgba(34,197,94,0.12); --blue-soft:rgba(59,130,246,0.14);
  --radius:14px; --radius-sm:10px;
  --shadow:0 1px 0 rgba(255,255,255,0.03) inset, 0 10px 30px -12px rgba(0,0,0,0.6);
  --font:'Inter',ui-sans-serif,system-ui,-apple-system,'Segoe UI',sans-serif;
  --mono:ui-monospace,'SF Mono',Menlo,monospace;
}
*{ margin:0; padding:0; box-sizing:border-box; }
html{ scroll-behavior:smooth; }
body{ font-family:var(--font); background:radial-gradient(1200px 600px at 70% -200px, rgba(139,92,246,0.08), transparent 60%), var(--bg); color:var(--text); line-height:1.55; font-size:14px; -webkit-font-smoothing:antialiased; font-feature-settings:'cv11','ss01'; min-height:100vh; }
button{ font-family:inherit; }
a{ color:var(--blue); text-decoration:none; }
a:hover{ text-decoration:underline; }

/* ---------- Top bar ---------- */
.topbar{ position:sticky; top:0; z-index:100; background:rgba(10,12,17,0.82); backdrop-filter:saturate(1.4) blur(14px); -webkit-backdrop-filter:saturate(1.4) blur(14px); border-bottom:1px solid var(--border-soft); }
.topbar-row{ display:flex; align-items:center; justify-content:space-between; gap:16px; padding:14px 32px 6px; }
.brand{ display:flex; align-items:center; gap:12px; min-width:0; }
.logo{ width:34px; height:34px; border-radius:10px; display:grid; place-items:center; background:linear-gradient(135deg,#8b5cf6,#3b82f6); box-shadow:0 6px 18px -6px rgba(139,92,246,0.7); flex:none; }
.brand-title{ font-size:15px; font-weight:700; letter-spacing:-0.01em; }
.brand-thin{ color:var(--muted); font-weight:500; }
.brand-sub{ font-size:12px; color:var(--muted); }
.sample-badge{ margin-left:8px; padding:4px 10px; border-radius:999px; font-size:10.5px; font-weight:700; letter-spacing:0.08em; color:#fde68a; background:rgba(245,165,36,0.12); border:1px solid rgba(245,165,36,0.45); white-space:nowrap; }
.top-actions{ display:flex; gap:8px; }
.ghost-btn{ font-size:12px; font-weight:500; color:var(--muted); padding:7px 12px; border-radius:9px; border:1px solid var(--border); background:transparent; cursor:pointer; transition:all .15s; white-space:nowrap; }
.ghost-btn:hover{ color:var(--text); border-color:#343c50; background:var(--surface); text-decoration:none; }

.tabs{ display:flex; align-items:center; gap:2px; padding:0 24px; overflow-x:auto; overflow-y:visible; scrollbar-width:none; }
.tabs::-webkit-scrollbar{ display:none; }
.nav-tab{ position:relative; padding:12px 14px 13px; font-size:13.5px; font-weight:500; color:var(--muted); cursor:pointer; background:none; border:none; white-space:nowrap; transition:color .15s; user-select:none; }
.nav-tab:hover{ color:var(--text); }
.nav-tab::after{ content:''; position:absolute; left:12px; right:12px; bottom:0; height:2px; border-radius:2px; background:var(--accent); transform:scaleX(0); transition:transform .2s ease; }
.nav-tab.active{ color:var(--text); }
.nav-tab.active::after{ transform:scaleX(1); }
.nbadge{ display:inline-block; padding:1px 7px; border-radius:999px; font-size:10.5px; font-weight:600; margin-left:5px; vertical-align:1px; }
.nbadge-r{ background:var(--red-soft); color:var(--red); }
.nbadge-b{ background:var(--blue-soft); color:#7fb0ff; }
.more{ position:relative; }
.caret{ font-size:10px; opacity:.7; }
.more-menu{ position:fixed; min-width:300px; max-height:70vh; overflow:auto; background:var(--surface-2); border:1px solid var(--border); border-radius:12px; padding:6px; box-shadow:0 24px 60px -12px rgba(0,0,0,0.75); opacity:0; transform:translateY(-6px); pointer-events:none; transition:all .16s ease; z-index:200; }
.more-menu.open{ opacity:1; transform:none; pointer-events:auto; }
.more-item{ display:flex; flex-direction:column; width:100%; text-align:left; background:none; border:none; color:var(--text); padding:8px 10px; border-radius:8px; cursor:pointer; }
.more-item b{ font-size:13px; font-weight:600; }
.more-item span{ font-size:11.5px; color:var(--muted); }
.more-item:hover,.more-item.active{ background:var(--accent-soft); }

/* ---------- Layout ---------- */
.tab-pane{ display:none; padding:28px 32px 40px; max-width:1560px; margin:0 auto; }
.tab-pane.active{ display:block; animation:fadeUp .35s ease both; }
@keyframes fadeUp{ from{ opacity:0; transform:translateY(6px);} to{ opacity:1; transform:none; } }
.view-head{ display:flex; justify-content:space-between; align-items:flex-end; gap:16px; margin-bottom:20px; }
.view-head h2{ font-size:22px; font-weight:700; letter-spacing:-0.02em; margin-bottom:4px; }
.view-head p{ color:var(--muted); font-size:14px; max-width:820px; }
.view-head p b{ color:var(--text); font-weight:600; }
.grid-2{ display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1.25fr); gap:16px; }
@media (max-width:1100px){ .grid-2{ grid-template-columns:1fr; } }

/* ---------- Overview ---------- */
.headline{ position:relative; padding:22px 26px; border-radius:var(--radius); background:linear-gradient(120deg, color-mix(in srgb, var(--c) 16%, transparent), transparent 55%), var(--surface); border:1px solid color-mix(in srgb, var(--c) 35%, var(--border)); box-shadow:var(--shadow); margin-bottom:16px; cursor:pointer; transition:transform .15s, border-color .15s; }
.headline:hover{ transform:translateY(-1px); border-color:color-mix(in srgb, var(--c) 60%, var(--border)); }
.hl-kicker{ display:inline-flex; align-items:center; gap:8px; font-size:11.5px; font-weight:700; letter-spacing:0.09em; text-transform:uppercase; color:var(--c); margin-bottom:6px; }
.hl-kicker i{ width:8px; height:8px; border-radius:50%; background:var(--c); box-shadow:0 0 0 4px color-mix(in srgb, var(--c) 25%, transparent); animation:pulse 2s infinite; }
@keyframes pulse{ 50%{ box-shadow:0 0 0 7px color-mix(in srgb, var(--c) 0%, transparent);} }
.hl-text{ font-size:24px; font-weight:700; letter-spacing:-0.02em; line-height:1.3; }
.hl-sub{ color:var(--muted); font-size:14px; margin-top:4px; }
.hl-go{ position:absolute; right:24px; top:50%; transform:translateY(-50%); font-size:13px; font-weight:600; color:var(--c); }
.findings{ display:flex; flex-wrap:wrap; gap:8px; margin:-2px 0 18px; }
.finding-chip{ display:inline-flex; align-items:center; gap:8px; padding:6px 12px; border-radius:999px; font-size:12.5px; color:var(--text); background:var(--surface-2); border:1px solid var(--border); cursor:pointer; transition:border-color .15s; }
.finding-chip:hover{ border-color:var(--c); }
.finding-chip i{ width:7px; height:7px; border-radius:50%; background:var(--c); }
.kpis{ display:grid; grid-template-columns:repeat(3,1fr); gap:16px; margin-bottom:16px; }
@media (max-width:900px){ .kpis{ grid-template-columns:1fr; } }
.kpi{ position:relative; text-align:left; padding:18px 20px 16px; border-radius:var(--radius); background:var(--surface); border:1px solid var(--border); cursor:pointer; color:var(--text); overflow:hidden; box-shadow:var(--shadow); transition:transform .15s, border-color .15s; }
.kpi::before{ content:''; position:absolute; inset:0 0 auto 0; height:3px; background:var(--c); }
.kpi::after{ content:''; position:absolute; right:-40px; top:-40px; width:140px; height:140px; border-radius:50%; background:radial-gradient(circle, color-mix(in srgb, var(--c) 22%, transparent), transparent 70%); }
.kpi:hover{ transform:translateY(-2px); border-color:color-mix(in srgb, var(--c) 55%, var(--border)); }
.kpi-label{ font-size:12.5px; color:var(--muted); font-weight:500; display:flex; align-items:center; gap:6px; }
.kpi-value{ font-size:46px; font-weight:800; letter-spacing:-0.03em; line-height:1.1; margin:6px 0 2px; color:var(--c); font-variant-numeric:tabular-nums; }
.kpi-sub{ font-size:12.5px; color:var(--muted); }
.kpi-cta{ position:absolute; right:18px; bottom:14px; font-size:12px; font-weight:600; color:var(--c); opacity:0; transform:translateX(-4px); transition:all .15s; }
.kpi:hover .kpi-cta{ opacity:1; transform:none; }
.qmark{ display:inline-grid; place-items:center; width:15px; height:15px; border-radius:50%; font-size:10px; font-weight:700; color:var(--muted); border:1px solid var(--border); }
.map-card{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); box-shadow:var(--shadow); overflow:hidden; }
.map-card-head{ display:flex; justify-content:space-between; align-items:center; gap:16px; padding:16px 20px 12px; border-bottom:1px solid var(--border-soft); }
.map-card-head h2{ font-size:15px; font-weight:650; }
.map-card-head p{ font-size:13px; color:var(--muted); }
.link-btn{ background:none; border:none; color:#b9a5ff; font-size:13px; font-weight:600; cursor:pointer; white-space:nowrap; }
.link-btn:hover{ color:#d6caff; }

/* ---------- Graph ---------- */
.graph-wrap{ position:relative; display:flex; flex-direction:column; }
.graph-toolbar{ display:flex; flex-wrap:wrap; align-items:center; gap:10px; padding:12px 16px; border-bottom:1px solid var(--border-soft); background:var(--surface); }
.slot-overview .graph-toolbar{ display:none; }
.slot-map .graph-wrap{ border:1px solid var(--border); border-radius:var(--radius); overflow:hidden; box-shadow:var(--shadow); }
.ctl{ display:flex; align-items:center; gap:8px; font-size:12px; color:var(--muted); }
select, .srch{ font-family:inherit; }
select{ background:var(--surface-2); color:var(--text); border:1px solid var(--border); border-radius:8px; padding:7px 28px 7px 10px; font-size:12.5px; outline:none; appearance:none; background-image:linear-gradient(45deg,transparent 50%,var(--muted) 50%),linear-gradient(135deg,var(--muted) 50%,transparent 50%); background-position:calc(100% - 14px) 50%, calc(100% - 9px) 50%; background-size:5px 5px; background-repeat:no-repeat; max-width:260px; }
select:focus{ border-color:var(--accent); }
.toggle{ display:inline-flex; align-items:center; gap:8px; font-size:12.5px; color:var(--text); cursor:pointer; user-select:none; }
.toggle input{ display:none; }
.toggle .track{ width:32px; height:18px; border-radius:999px; background:var(--border); position:relative; transition:background .2s; }
.toggle .track::after{ content:''; position:absolute; left:2px; top:2px; width:14px; height:14px; border-radius:50%; background:#fff; transition:transform .2s; }
.toggle input:checked + .track{ background:var(--red); }
.toggle input:checked + .track::after{ transform:translateX(14px); }
.graph-meta{ margin-left:auto; font-size:12px; color:var(--faint); }
.graph-stage{ position:relative; background:radial-gradient(900px 500px at 50% 45%, #121827, #0b0e15 70%); }
.graph-canvas{ width:100%; height:calc(100vh - 330px); min-height:520px; }
.slot-map .graph-canvas{ height:calc(100vh - 250px); min-height:560px; }
.graph-loading{ position:absolute; inset:0; display:flex; align-items:center; justify-content:center; gap:10px; color:var(--muted); font-size:13px; background:rgba(11,14,21,0.55); transition:opacity .3s; }
.graph-loading.done{ opacity:0; pointer-events:none; }
.spinner{ width:16px; height:16px; border-radius:50%; border:2px solid var(--border); border-top-color:var(--accent); animation:spin .8s linear infinite; }
@keyframes spin{ to{ transform:rotate(360deg);} }
.graph-legend{ position:absolute; left:14px; bottom:14px; display:flex; flex-direction:column; gap:8px; padding:12px 14px; background:rgba(18,22,33,0.86); backdrop-filter:blur(8px); border:1px solid var(--border); border-radius:12px; font-size:11.5px; color:var(--muted); pointer-events:none; max-width:calc(100% - 28px); }
.lg-row{ display:flex; flex-wrap:wrap; gap:6px 14px; align-items:center; }
.lg-title{ font-size:10px; text-transform:uppercase; letter-spacing:0.08em; color:var(--faint); font-weight:700; min-width:58px; }
.lg-i{ display:inline-flex; align-items:center; gap:6px; white-space:nowrap; }
.sw{ width:10px; height:10px; border-radius:50%; display:inline-block; }
.sw-ring{ width:11px; height:11px; border-radius:50%; display:inline-block; border:2.5px solid; background:#475066; }
.sw-line{ width:18px; height:0; border-top:2px solid; display:inline-block; }
.sw-dash{ width:18px; height:0; border-top:2px dashed; display:inline-block; }
.sw-diamond{ width:9px; height:9px; transform:rotate(45deg); display:inline-block; }
div.vis-tooltip{ font-family:var(--font) !important; background:#1b2131 !important; color:var(--text) !important; border:1px solid #2c3446 !important; border-radius:10px !important; padding:10px 12px !important; box-shadow:0 12px 30px -8px rgba(0,0,0,0.7) !important; font-size:12px !important; max-width:340px; white-space:normal !important; }
.g-tip b{ display:block; font-size:12.5px; margin-bottom:2px; color:var(--text); word-break:break-all; }
.g-tip span{ color:var(--muted); }

/* ---------- Cards / generic ---------- */
.card{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); padding:18px 20px; margin-bottom:16px; box-shadow:var(--shadow); }
.card h3{ font-size:13px; font-weight:650; color:var(--text); margin-bottom:10px; display:flex; align-items:center; justify-content:space-between; gap:10px; }
.card-head{ display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:6px; }
.card-head h3{ margin:0; }
.card-sub{ font-size:12.5px; color:var(--muted); margin-bottom:10px; }
.card h3 .csv-btn,.csv-btn{ font-size:11.5px; color:#c4b5fd; cursor:pointer; padding:4px 11px; border:1px solid rgba(139,92,246,0.45); border-radius:999px; background:transparent; font-weight:500; }
.csv-btn:hover{ background:var(--accent-soft); }
.row{ display:grid; gap:16px; }
.row-2{ grid-template-columns:1fr 1fr; }
.row-3{ grid-template-columns:1fr 1fr 1fr; }
.row-2-1{ grid-template-columns:2fr 1fr; }
@media (max-width:780px){ .row-2,.row-3,.row-2-1{ grid-template-columns:1fr; } .hero{ grid-template-columns:1fr; } .tab-pane{ padding:20px 16px; } .topbar-row{ padding:12px 16px 4px; } }

.stats{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:12px; margin-bottom:16px; }
.stat{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius-sm); padding:16px 14px; text-align:center; }
.stat .v{ font-size:28px; font-weight:750; line-height:1.1; letter-spacing:-0.02em; }
.stat .l{ font-size:11.5px; color:var(--muted); margin-top:4px; }

table{ width:100%; border-collapse:collapse; font-size:13px; }
th{ text-align:left; padding:10px 12px; background:var(--surface-2); color:var(--muted); font-weight:600; font-size:11.5px; position:sticky; top:0; z-index:1; user-select:none; border-bottom:1px solid var(--border); }
th.sortable{ cursor:pointer; }
th.sortable:hover{ color:var(--text); }
th.sortable::after{ content:" ↕"; color:var(--faint); font-size:10px; }
th.sort-asc::after{ content:" ↑"; color:var(--accent); }
th.sort-desc::after{ content:" ↓"; color:var(--accent); }
td{ padding:10px 12px; border-bottom:1px solid var(--border-soft); vertical-align:top; }
tr:hover td{ background:rgba(139,92,246,0.04); }
tr.clickable{ cursor:pointer; }
.tw{ max-height:620px; overflow-y:auto; border:1px solid var(--border); border-radius:var(--radius-sm); }
.url-cell{ max-width:380px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; display:inline-block; vertical-align:bottom; }

.b{ display:inline-block; padding:2px 9px; border-radius:999px; font-size:11px; font-weight:600; }
.b-r{ background:var(--red-soft); color:var(--red); }
.b-y{ background:var(--amber-soft); color:var(--amber); }
.b-o{ background:var(--amber-soft); color:var(--amber); }
.b-g{ background:var(--green-soft); color:var(--green); }
.b-b{ background:var(--blue-soft); color:#7fb0ff; }
.b-m{ background:rgba(138,147,166,0.12); color:var(--muted); }
.pill{ display:inline-flex; align-items:center; gap:6px; padding:3px 10px; border-radius:999px; font-size:11.5px; font-weight:650; }
.pill::before{ content:''; width:6px; height:6px; border-radius:50%; background:currentColor; }
.pill-fix{ background:var(--red-soft); color:var(--red); }
.pill-update{ background:var(--amber-soft); color:var(--amber); }
.pill-ok{ background:var(--green-soft); color:var(--green); }
.pill-opportunity{ background:var(--blue-soft); color:#7fb0ff; }
.pill-none{ background:rgba(138,147,166,0.12); color:var(--muted); }

.srch{ width:100%; padding:10px 14px; background:var(--surface); border:1px solid var(--border); border-radius:10px; color:var(--text); font-size:13.5px; margin-bottom:12px; outline:none; transition:border-color .15s, box-shadow .15s; }
.srch.small{ width:240px; margin:0; padding:7px 12px; font-size:12.5px; }
.srch:focus{ border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-soft); }
.chips{ display:flex; flex-wrap:wrap; gap:6px; }
.chip{ padding:6px 12px; border-radius:999px; font-size:12px; font-weight:550; color:var(--muted); background:transparent; border:1px solid var(--border); cursor:pointer; transition:all .15s; }
.chip:hover{ color:var(--text); }
.chip.active{ color:var(--text); background:var(--surface-2); border-color:var(--c, var(--accent)); }
.chip i{ display:inline-block; width:7px; height:7px; border-radius:50%; background:var(--c, var(--accent)); margin-right:6px; }

.expand{ cursor:pointer; }
.expand-body{ display:none; margin-top:12px; padding-top:12px; border-top:1px solid var(--border-soft); }
.expand.open .expand-body{ display:block; }
.expand-arrow{ color:var(--muted); transition:transform 0.2s; display:inline-block; }
.expand.open .expand-arrow{ transform:rotate(90deg); }
.detail{ display:none; background:var(--surface); border:1px solid var(--accent); border-radius:var(--radius-sm); padding:16px; margin-bottom:12px; }
.detail.show{ display:block; }
.action-row{ display:grid; grid-template-columns:60px 1fr 80px 80px; gap:12px; padding:10px 0; border-bottom:1px solid var(--border-soft); align-items:center; font-size:13px; }
.action-row:last-child{ border-bottom:none; }
.priority{ font-weight:700; font-size:12px; }
.priority.p1{ color:var(--red); } .priority.p2{ color:var(--amber); } .priority.p3{ color:var(--blue); }
.kw{ color:var(--muted); font-size:12px; max-width:280px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.empty{ padding:48px 24px; text-align:center; color:var(--muted); border:1px dashed var(--border); border-radius:var(--radius); }
.empty .ico{ font-size:28px; margin-bottom:8px; opacity:0.4; }
.empty .msg{ font-size:14px; margin-bottom:6px; color:var(--text); font-weight:600; }
.empty .hint{ font-size:12.5px; }
.empty code{ background:var(--surface-2); padding:2px 6px; border-radius:4px; font-size:11px; }

[data-tip]{ position:relative; cursor:help; }
[data-tip]:hover::after{ content:attr(data-tip); position:absolute; bottom:calc(100% + 8px); left:50%; transform:translateX(-50%); background:#1b2131; color:var(--text); border:1px solid #2c3446; padding:8px 11px; border-radius:9px; font-size:11.5px; font-weight:400; letter-spacing:0; text-transform:none; white-space:normal; width:250px; z-index:300; line-height:1.45; box-shadow:0 12px 30px -8px rgba(0,0,0,0.7); text-align:left; }
.term{ border-bottom:1px dotted var(--muted); }

#toast{ position:fixed; bottom:24px; left:50%; transform:translateX(-50%) translateY(100px); background:var(--accent); color:#fff; padding:10px 18px; border-radius:10px; font-size:13px; font-weight:500; opacity:0; transition:all 0.25s; pointer-events:none; z-index:1000; box-shadow:0 6px 20px rgba(0,0,0,0.4); }
#toast.show{ opacity:1; transform:translateX(-50%) translateY(0); }

/* ---------- Side panel ---------- */
.scrim{ position:fixed; inset:0; background:rgba(5,7,11,0.45); opacity:0; pointer-events:none; transition:opacity .25s; z-index:400; }
.scrim.show{ opacity:1; pointer-events:auto; }
.drawer{ position:fixed; top:0; right:0; height:100vh; width:min(440px, 92vw); background:var(--surface-2); border-left:1px solid var(--border); box-shadow:-30px 0 60px -20px rgba(0,0,0,0.7); transform:translateX(105%); transition:transform .3s cubic-bezier(.2,.8,.2,1); z-index:401; overflow-y:auto; padding:26px 26px 32px; }
.drawer.open{ transform:none; }
.drawer-close{ position:absolute; top:16px; right:16px; width:32px; height:32px; border-radius:9px; border:1px solid var(--border); background:var(--surface); color:var(--muted); font-size:18px; cursor:pointer; }
.drawer-close:hover{ color:var(--text); }
.dr-back{ background:none; border:none; color:#b9a5ff; font-size:12.5px; font-weight:600; cursor:pointer; margin-bottom:10px; }
.dr-kicker{ font-size:11px; font-weight:700; letter-spacing:0.09em; text-transform:uppercase; color:var(--faint); margin-bottom:6px; }
.dr-title{ font-size:18px; font-weight:700; letter-spacing:-0.01em; line-height:1.35; word-break:break-word; padding-right:30px; }
.dr-badges{ display:flex; align-items:center; gap:10px; margin:10px 0 18px; }
.dr-link{ font-size:12.5px; font-weight:600; color:#7fb0ff; }
.dr-block{ margin-bottom:14px; }
.dr-label{ font-size:11px; font-weight:700; letter-spacing:0.08em; text-transform:uppercase; color:var(--muted); margin-bottom:5px; }
.dr-block p{ font-size:14px; line-height:1.55; }
.dr-action{ padding:14px 16px; border-radius:12px; background:color-mix(in srgb, var(--c) 10%, var(--surface)); border:1px solid color-mix(in srgb, var(--c) 35%, var(--border)); }
.dr-action .dr-label{ color:var(--c); }
.dr-facts{ margin:18px 0 10px; border-top:1px solid var(--border-soft); }
.dr-fact{ display:flex; justify-content:space-between; gap:16px; padding:9px 0; border-bottom:1px solid var(--border-soft); font-size:12.5px; }
.dr-fact span:first-child{ color:var(--muted); flex:none; }
.dr-fact span:last-child{ text-align:right; word-break:break-word; }
.dr-list{ margin-top:14px; }
.dr-list li{ list-style:none; font-size:12.5px; padding:6px 0; border-bottom:1px solid var(--border-soft); word-break:break-all; }
.dr-idea{ margin-top:16px; width:100%; padding:12px 14px; border-radius:12px; border:1px solid rgba(59,130,246,0.45); background:var(--blue-soft); color:#a9c8ff; font-weight:600; font-size:13px; cursor:pointer; text-align:left; }
.dr-idea:hover{ background:rgba(59,130,246,0.22); }
.dr-source{ margin-top:22px; font-size:11.5px; color:var(--faint); font-family:var(--mono); }

/* ---------- Overlap ---------- */
.legend-inline{ display:flex; flex-wrap:wrap; gap:14px; font-size:11.5px; color:var(--muted); margin-top:8px; }
.pair-row{ display:grid; grid-template-columns:minmax(0,1fr) auto auto; gap:12px; align-items:center; padding:10px 12px; border-radius:10px; cursor:pointer; transition:background .15s; }
.pair-row:hover{ background:var(--surface-2); }
.pair-row .slugs{ font-size:12.5px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.pair-row .sim{ font-weight:700; font-variant-numeric:tabular-nums; }

/* ---------- Gaps ---------- */
.gap-summary{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:12px; margin-bottom:16px; }
.gs-card{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius-sm); padding:14px 16px; }
.gs-name{ font-size:13px; font-weight:650; margin-bottom:8px; }
.gs-bar{ display:flex; height:8px; border-radius:999px; overflow:hidden; background:var(--border-soft); margin-bottom:8px; }
.gs-bar span{ height:100%; }
.gs-nums{ display:flex; gap:12px; font-size:11.5px; color:var(--muted); }
.gs-nums b{ font-size:15px; margin-right:3px; }
.gap-matrix{ overflow:auto; max-height:640px; border:1px solid var(--border-soft); border-radius:var(--radius-sm); }
.gm-row{ display:grid; align-items:center; border-bottom:1px solid var(--border-soft); cursor:pointer; transition:background .12s; }
.gm-row:hover{ background:rgba(139,92,246,0.05); }
.gm-head{ position:sticky; top:0; z-index:2; background:var(--surface-2); cursor:default; font-size:11.5px; font-weight:650; color:var(--muted); }
.gm-head:hover{ background:var(--surface-2); }
.gm-row > div{ padding:9px 10px; }
.gm-topic{ font-size:13px; font-weight:500; }
.gm-cell{ display:flex; justify-content:center; }
.cell{ width:100%; max-width:84px; height:26px; border-radius:7px; display:grid; place-items:center; font-size:11px; font-weight:700; }
.cell-gap{ background:var(--blue); color:#fff; box-shadow:0 0 14px -4px rgba(59,130,246,0.9); }
.cell-shared{ background:rgba(138,147,166,0.16); color:var(--muted); }
.cell-adv{ background:var(--green); color:#062b14; }
.cell-missing{ border:1px dashed rgba(59,130,246,0.55); color:#7fb0ff; }
.cell-empty{ background:rgba(255,255,255,0.02); }
.gm-idea{ font-size:11.5px; color:#7fb0ff; font-weight:600; white-space:nowrap; }

/* ---------- Action board ---------- */
.board{ display:grid; grid-template-columns:repeat(5,minmax(230px,1fr)); gap:14px; align-items:start; }
@media (max-width:1300px){ .board{ grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); } }
.lane{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); padding:16px; position:relative; overflow:hidden; box-shadow:var(--shadow); }
.lane::before{ content:''; position:absolute; inset:0 0 auto 0; height:3px; background:var(--c); }
.lane-head{ display:flex; align-items:baseline; justify-content:space-between; }
.lane-title{ display:flex; align-items:center; gap:8px; font-size:14px; font-weight:700; }
.lane-title i{ width:8px; height:8px; border-radius:50%; background:var(--c); }
.lane-count{ font-size:32px; font-weight:800; letter-spacing:-0.03em; color:var(--c); font-variant-numeric:tabular-nums; }
.lane-blurb{ font-size:12.5px; color:var(--muted); margin:2px 0 12px; min-height:36px; }
.lane-item{ display:block; width:100%; text-align:left; background:var(--surface-2); border:1px solid var(--border-soft); border-radius:10px; padding:9px 11px; margin-bottom:7px; cursor:pointer; color:var(--text); transition:border-color .15s, transform .15s; }
.lane-item[hidden]{ display:none; }
.lane-item:hover{ border-color:color-mix(in srgb, var(--c) 55%, var(--border)); transform:translateX(2px); }
.lane-item b{ display:block; font-size:12.5px; font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.lane-item span{ font-size:11.5px; color:var(--muted); }
.lane-more{ background:none; border:none; color:#b9a5ff; font-size:12px; font-weight:600; cursor:pointer; padding:4px 0; }
.lane-src{ margin-top:10px; font-size:10.5px; color:var(--faint); font-family:var(--mono); }
.lane-empty{ font-size:12.5px; color:var(--faint); padding:10px 0; }

/* ---------- Legacy views (More menu) ---------- */
.hero{ background:linear-gradient(135deg,var(--surface) 0%,var(--surface-2) 100%); border:1px solid var(--border); border-radius:var(--radius); padding:24px; margin-bottom:16px; display:grid; grid-template-columns:240px 1fr; gap:24px; align-items:center; }
.hero .score-block{ text-align:center; }
.hero .score-num{ font-size:72px; font-weight:800; line-height:1; }
.hero .score-num.green{ color:var(--green); } .hero .score-num.yellow{ color:var(--amber); } .hero .score-num.red{ color:var(--red); } .hero .score-num.unknown{ color:var(--muted); }
.hero .score-label{ font-size:10px; color:var(--muted); text-transform:uppercase; letter-spacing:1.2px; margin-top:4px; font-weight:600; }
.hero .score-delta{ display:inline-block; margin-top:6px; padding:2px 10px; border-radius:10px; font-size:11px; font-weight:600; }
.hero .delta-up{ background:var(--green-soft); color:var(--green); } .hero .delta-down{ background:var(--red-soft); color:var(--red); } .hero .delta-flat{ background:rgba(138,147,166,0.15); color:var(--muted); }
.subscore-grid{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:10px; }
.subscore{ background:var(--surface-alt); border:1px solid var(--border); border-radius:10px; padding:10px 12px; }
.subscore .label{ font-size:10px; color:var(--muted); text-transform:uppercase; letter-spacing:0.5px; }
.subscore .row{ display:flex; justify-content:space-between; align-items:baseline; margin:6px 0 4px; }
.subscore .val{ font-size:22px; font-weight:700; }
.subscore .val.green{ color:var(--green); } .subscore .val.yellow{ color:var(--amber); } .subscore .val.red{ color:var(--red); } .subscore .val.unknown{ color:var(--muted); }
.subscore .delta{ font-size:11px; color:var(--muted); } .subscore .delta.up{ color:var(--green); } .subscore .delta.down{ color:var(--red); }
.subscore .bar{ background:var(--border); height:4px; border-radius:2px; overflow:hidden; }
.subscore .bar-fill{ height:100%; transition:width 0.3s; }
.subscore .detail{ display:block; background:none; border:none; padding:0; margin:5px 0 0; font-size:10.5px; color:var(--muted); min-height:14px; }
.sparkline-wrap{ display:flex; align-items:center; gap:8px; margin-top:6px; justify-content:center; font-size:10px; color:var(--muted); }
.gauge-wrap{ position:relative; width:200px; height:120px; margin:0 auto; }

.footer{ padding:22px 32px 30px; text-align:center; font-size:11.5px; color:var(--faint); }

@media print{
  :root{ --bg:#fff; --surface:#fff; --surface-2:#f9fafb; --surface-alt:#f9fafb; --border:#e5e7eb; --border-soft:#eef0f3; --text:#1f2937; --muted:#6b7280; }
  body{ background:#fff; color:#1f2937; }
  .tabs,.top-actions,.csv-btn,.srch,#toast,.drawer,.scrim,.graph-toolbar{ display:none !important; }
  .topbar{ position:static; background:#fff; }
  .tab-pane{ display:block !important; padding:16px 0; break-after:page; animation:none; }
  .tab-pane:last-child{ break-after:auto; }
  .expand-body{ display:block !important; }
  .card,.hero,.stats,.subscore,.kpi,.lane{ break-inside:avoid; box-shadow:none; }
  table th{ background:#f3f4f6 !important; color:#374151 !important; }
}
"""


_VISUALS_JS = r"""
// ============================================================================
// VISUALS — Overview, Cluster Map, Overlap, Gaps, Actions, Explorer, side panel
// One color system: red = fix, amber = update, green = healthy, blue = opportunity.
// ============================================================================
const STATUS_COLOR={fix:'#f04438',update:'#f5a524',ok:'#22c55e',opportunity:'#3b82f6',none:'#5b6478'};
const KIND_COLOR={service:'#a78bfa',pillar:'#22d3ee',blog:'#94a3b8','case-study':'#f472b6',other:'#64748b'};
const KIND_LABEL={service:'Service page',pillar:'Pillar / hub page',blog:'Blog post','case-study':'Case study',other:'Other page'};
const PRIMARY_TABS=['overview','map','overlap','gaps','actions','explorer'];
function esc(s){ return String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function pctTxt(v){ return v==null?'—':Math.round(v*100)+'%'; }
function shortSlug(s,n){ n=n||34; s=String(s||''); return s.length>n?'…'+s.slice(-(n-1)):s; }

// ---------- Side panel ----------
let PANEL_CUR=null; const PANEL_BACK=[];
function openPanel(p, keepStack){
  if(!p) return;
  if(!keepStack) PANEL_BACK.length=0;
  PANEL_CUR=p; renderPanel(p);
  document.getElementById('drawer').classList.add('open');
  document.getElementById('drawer').setAttribute('aria-hidden','false');
  document.getElementById('scrim').classList.add('show');
}
function closePanel(){
  document.getElementById('drawer').classList.remove('open');
  document.getElementById('drawer').setAttribute('aria-hidden','true');
  document.getElementById('scrim').classList.remove('show');
}
function renderPanel(p){
  const col=STATUS_COLOR[p.status]||STATUS_COLOR.none;
  const whatLabel={fix:"What's wrong",update:"What's wrong",opportunity:'The opportunity',ok:'What we found',none:'What we found'}[p.status]||"What's wrong";
  const facts=(p.facts||[]).map(([k,v])=>`<div class="dr-fact"><span>${esc(k)}</span><span>${esc(v)}</span></div>`).join('');
  const list=(p.list||[]).length?`<div class="dr-list"><div class="dr-label">${esc(p.list_title)}</div><ul>${p.list.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`:'';
  document.getElementById('drawer-body').innerHTML=`
    ${PANEL_BACK.length?'<button class="dr-back" id="dr-back">← Back</button>':''}
    <div class="dr-kicker">${esc(p.kicker)}</div>
    <div class="dr-title">${esc(p.title)}</div>
    <div class="dr-badges"><span class="pill pill-${esc(p.status)}">${esc(p.status_label)}</span>${p.url?`<a class="dr-link" href="${esc(p.url)}" target="_blank" rel="noopener">Open page ↗</a>`:''}</div>
    <div class="dr-block"><div class="dr-label">${whatLabel}</div><p>${esc(p.what)}</p></div>
    ${p.why?`<div class="dr-block"><div class="dr-label">Why it matters</div><p>${esc(p.why)}</p></div>`:''}
    <div class="dr-block dr-action" style="--c:${col}"><div class="dr-label">Suggested action</div><p>${esc(p.action)}</p></div>
    ${facts?`<div class="dr-facts">${facts}</div>`:''}
    ${list}
    ${p.idea?'<button class="dr-idea" id="dr-idea">View the matching content idea →</button>':''}
    <div class="dr-source">Source: ${esc(p.source)}</div>`;
  const back=document.getElementById('dr-back');
  if(back) back.onclick=()=>{ const prev=PANEL_BACK.pop(); if(prev){ PANEL_CUR=prev; renderPanel(prev);} };
  const idea=document.getElementById('dr-idea');
  if(idea) idea.onclick=()=>{ PANEL_BACK.push(p); openPanel(p.idea,true); };
  document.getElementById('drawer').scrollTop=0;
}

// ---------- Navigation helpers ----------
let PENDING_OVERLAP_CID=null;
function goto(tab, opts){
  opts=opts||{};
  if(tab==='overlap' && opts.cid!=null) PENDING_OVERLAP_CID=opts.cid;
  activateTab(tab);
  if(tab==='overlap' && OVERLAP_READY && PENDING_OVERLAP_CID!=null){ selectOverlapCluster(PENDING_OVERLAP_CID); PENDING_OVERLAP_CID=null; }
}
function positionMoreMenu(){
  const btn=document.getElementById('more-btn'), menu=document.getElementById('more-menu');
  const r=btn.getBoundingClientRect();
  menu.style.top=(r.bottom+6)+'px';
  menu.style.left=Math.max(12, Math.min(r.left, window.innerWidth-320))+'px';
}
function initMoreMenu(){
  const btn=document.getElementById('more-btn'), menu=document.getElementById('more-menu');
  btn.addEventListener('click',e=>{ e.stopPropagation(); positionMoreMenu(); menu.classList.toggle('open'); });
  document.addEventListener('click',e=>{ if(!e.target.closest('#more-menu')) menu.classList.remove('open'); });
  window.addEventListener('resize',()=>menu.classList.remove('open'));
}

// ---------- Overview ----------
function animateCount(el,to){
  if(to==null){ el.textContent='—'; return; }
  const dur=900, t0=performance.now();
  function step(t){ const k=Math.min(1,(t-t0)/dur); el.textContent=Math.round(to*(1-Math.pow(1-k,3))); if(k<1) requestAnimationFrame(step); }
  requestAnimationFrame(step);
}
function renderOverview(){
  const f=VIS.findings||[], h=f[0];
  const hl=document.getElementById('headline');
  if(h){
    const kicker={fix:'Biggest issue',update:'Top issue',opportunity:'Biggest opportunity',ok:'All clear'}[h.status]||'Finding';
    hl.innerHTML=`<div class="headline" style="--c:${STATUS_COLOR[h.status]}" data-goto="${esc(h.tab)}" ${h.cid!=null?`data-cid="${h.cid}"`:''}>
        <div class="hl-kicker"><i></i>${kicker}</div>
        <div class="hl-text">${esc(h.text)}</div>
        ${h.sub?`<div class="hl-sub">${esc(h.sub)}</div>`:''}
        <div class="hl-go">See where →</div>
      </div>
      ${f.length>1?`<div class="findings">${f.slice(1).map(x=>`<button class="finding-chip" style="--c:${STATUS_COLOR[x.status]}" data-goto="${esc(x.tab)}"><i></i>${esc(x.text)}</button>`).join('')}</div>`:''}`;
  }
  const k=document.getElementById('kpis');
  k.innerHTML=(VIS.kpis||[]).map(x=>`<button class="kpi" style="--c:${STATUS_COLOR[x.status]}" data-goto="${esc(x.tab)}">
      <div class="kpi-label">${esc(x.label)} <span class="qmark" data-tip="${esc(x.tip)}">?</span></div>
      <div class="kpi-value" data-v="${x.value==null?'':x.value}">0</div>
      <div class="kpi-sub">${esc(x.sub)}</div>
      <div class="kpi-cta">Open →</div>
    </button>`).join('');
  k.querySelectorAll('.kpi-value').forEach(el=>animateCount(el, el.dataset.v===''?null:parseInt(el.dataset.v)));
}
document.addEventListener('click',e=>{
  const g=e.target.closest('[data-goto]'); if(!g) return;
  const cid=g.dataset.cid; goto(g.dataset.goto, cid!=null&&cid!==''?{cid:parseInt(cid)}:{});
});

// ---------- Cluster Map (vis-network) ----------
let NET=null, GNODES=null, GEDGES=null; const GNODE_BY_ID={}, GEDGE_BY_ID={};
function legendHTML(){
  const kinds=Object.keys(KIND_COLOR).filter(k=>VIS.graph.nodes.some(n=>n.kind===k));
  return `<div class="lg-row"><span class="lg-title">Topics</span>
      <span class="lg-i"><span class="sw" style="background:${STATUS_COLOR.fix}"></span>Fix</span>
      <span class="lg-i"><span class="sw" style="background:${STATUS_COLOR.update}"></span>Update</span>
      <span class="lg-i"><span class="sw" style="background:${STATUS_COLOR.ok}"></span>Healthy</span></div>
    <div class="lg-row"><span class="lg-title">Pages</span>${kinds.map(k=>`<span class="lg-i"><span class="${k==='service'||k==='pillar'?'sw-diamond':'sw'}" style="background:${KIND_COLOR[k]}"></span>${KIND_LABEL[k]}</span>`).join('')}</div>
    <div class="lg-row"><span class="lg-title">Rings</span>
      <span class="lg-i"><span class="sw-ring" style="border-color:${STATUS_COLOR.fix}"></span>Overlaps another page</span>
      <span class="lg-i"><span class="sw-ring" style="border-color:${STATUS_COLOR.update}"></span>Stale (6+ months)</span></div>
    <div class="lg-row"><span class="lg-title">Lines</span>
      <span class="lg-i"><span class="sw-line" style="border-color:${STATUS_COLOR.fix}"></span>Pages ${Math.round((VIS.graph.meta.threshold||0.8)*100)}%+ alike</span>
      <span class="lg-i"><span class="sw-dash" style="border-color:${STATUS_COLOR.fix}"></span>Topics to merge</span>
      <span class="lg-i"><span class="sw-line" style="border-color:rgba(139,92,246,0.6);border-top-width:1px"></span>Also relates to topic</span></div>`;
}
function tipEl(html){ const d=document.createElement('div'); d.className='g-tip'; d.innerHTML=html; return d; }
function wrapLabel(s){ const w=String(s).split(' '); const out=[]; let line=''; w.forEach(x=>{ if((line+' '+x).trim().length>18&&line){ out.push(line); line=x; } else line=(line+' '+x).trim(); }); if(line) out.push(line); return out.join('\n'); }
function graphMeta(visible){
  const m=VIS.graph.meta||{};
  let s=`${visible==null?m.url_nodes:visible} of ${m.url_total} pages shown`;
  if(m.similar_total>m.similar_edges) s+=` · strongest ${m.similar_edges} of ${m.similar_total} overlap lines`;
  document.getElementById('g-meta').textContent=s;
}
function buildGraph(){
  const el=document.getElementById('graph'), loading=document.getElementById('g-loading');
  const G=VIS.graph;
  if(!G.nodes.length){ el.innerHTML=emptyState('No pages to map','Run the pipeline to build clusters.'); loading.classList.add('done'); return; }
  if(typeof vis==='undefined'){ el.innerHTML=emptyState('Map library could not load','The Cluster Map needs one script from unpkg.com. Check the connection and reload.'); loading.classList.add('done'); return; }
  const t0=performance.now();
  document.getElementById('g-legend').innerHTML=legendHTML();
  // Seed positions: topics on a golden-angle spiral (largest in the middle), pages around their topic.
  const clusterNodes=G.nodes.filter(n=>n.type==='cluster').sort((a,b)=>b.size-a.size);
  // Stretched horizontally so the layout fills a wide screen.
  const center={}; clusterNodes.forEach((c,i)=>{ const r=150*Math.sqrt(i+0.3), a=i*2.39996; center[c.cid]={x:2.0*r*Math.cos(a), y:r*Math.sin(a)}; });
  const seen={};
  const nodes=G.nodes.map(n=>{
    GNODE_BY_ID[n.id]=n;
    if(n.type==='cluster'){
      const col=STATUS_COLOR[n.status]||STATUS_COLOR.none, c=center[n.cid];
      const ci=VIS.clusters[String(n.cid)]||{};
      return {id:n.id, x:c.x, y:c.y, label:wrapLabel(n.label), shape:'dot', size:14+Math.sqrt(n.size)*6.5, mass:3,
        color:{background:col, border:col, highlight:{background:col,border:'#ffffff'}, hover:{background:col,border:'#ffffff'}},
        borderWidth:2, borderWidthSelected:3,
        font:{color:'#e8eaf0', size:14, face:'Inter, system-ui, sans-serif', strokeWidth:5, strokeColor:'#0a0c11', multi:false},
        shadow:{enabled:true, color:col+'80', size:28, x:0, y:0},
        title:tipEl(`<b>${esc(n.label)}</b><span>${n.size} pages · ${esc((ci.panel||{}).status_label||'')}${ci.flagged?` · ${ci.flagged} overlapping pairs`:''}</span>`)};
    }
    const c=center[n.cid]||{x:0,y:0}, k=(seen[n.cid]=(seen[n.cid]||0)+1), a=k*2.39996, r=38+9*Math.sqrt(k);
    const fill=KIND_COLOR[n.kind]||KIND_COLOR.other, issue=n.status!=='ok';
    const ring=issue?(STATUS_COLOR[n.status]||fill):fill;
    const u=VIS.urls[n.ui]||{};
    return {id:n.id, x:c.x+r*Math.cos(a), y:c.y+r*Math.sin(a), shape:n.hub?'diamond':'dot', size:n.hub?10:5.5,
      color:{background:fill, border:ring, highlight:{background:fill,border:'#ffffff'}, hover:{background:fill,border:'#ffffff'}},
      borderWidth:issue?3:1, borderWidthSelected:4,
      title:tipEl(`<b>${esc(n.label)}</b><span>${esc(KIND_LABEL[n.kind]||'')} · ${esc(u.cluster||'')}${u.n_pairs?` · overlaps ${u.n_pairs} page${u.n_pairs>1?'s':''}`:''}${u.freshness?` · ${esc(u.freshness)}`:''}</span>`)};
  });
  const edges=G.edges.map((e,i)=>{
    const id='e'+i; GEDGE_BY_ID[id]=e;
    if(e.type==='member') return {id, from:e.from, to:e.to, width:1, length:50, color:{color:'rgba(138,147,166,0.16)', highlight:'rgba(232,234,240,0.55)', hover:'rgba(232,234,240,0.4)'}};
    if(e.type==='secondary') return {id, from:e.from, to:e.to, width:0.6, physics:false, color:{color:'rgba(139,92,246,0.20)', highlight:'rgba(139,92,246,0.8)', hover:'rgba(139,92,246,0.6)'}};
    if(e.type==='similar'){ const a=Math.min(0.95,0.35+(e.sim-0.8)*3.5); return {id, from:e.from, to:e.to, physics:false, width:1.2+(e.sim-0.8)*16, color:{color:`rgba(240,68,56,${a.toFixed(2)})`, highlight:'#ff6b5e', hover:'#ff6b5e'}, title:tipEl(`<b>${Math.round(e.sim*100)}% alike</b><span>${e.risk?'Involves a money page · ':''}click for details</span>`)}; }
    const col=STATUS_COLOR[e.status]||STATUS_COLOR.update;
    return {id, from:e.from, to:e.to, width:3, dashes:[10,8], length:240, color:{color:col, highlight:col, hover:col}, title:tipEl(`<b>Topics ${Math.round(e.sim*100)}% similar</b><span>Merge suggestion · click for details</span>`)};
  });
  GNODES=new vis.DataSet(nodes); GEDGES=new vis.DataSet(edges);
  NET=new vis.Network(el,{nodes:GNODES,edges:GEDGES},{
    autoResize:true,
    layout:{improvedLayout:false, randomSeed:7},
    physics:{solver:'forceAtlas2Based', forceAtlas2Based:{gravitationalConstant:-55, centralGravity:0.008, springLength:55, springConstant:0.09, damping:0.5, avoidOverlap:0.35},
      maxVelocity:60, minVelocity:0.8, timestep:0.45, stabilization:{enabled:true, iterations:240, updateInterval:40, fit:true}},
    interaction:{hover:true, tooltipDelay:90, hideEdgesOnDrag:true, zoomSpeed:0.7, multiselect:false},
    edges:{smooth:false, selectionWidth:1.5, hoverWidth:0.8},
    nodes:{font:{face:'Inter, system-ui, sans-serif'}},
  });
  NET.once('stabilizationIterationsDone',()=>{
    NET.setOptions({physics:false});
    loading.classList.add('done');
    NET.fit({animation:{duration:700, easingFunction:'easeInOutQuad'}});
    window.__graphReadyMs=Math.round(performance.now()-t0);
  });
  // Keep topic labels readable (~13px on screen) at any zoom level.
  const clusterIds=G.nodes.filter(n=>n.type==='cluster').map(n=>n.id);
  let lastScale=0;
  function fitLabels(){
    const s=NET.getScale(); if(Math.abs(s-lastScale)/Math.max(s,1e-6)<0.08) return; lastScale=s;
    const size=Math.max(10,Math.min(48,13/s));
    GNODES.update(clusterIds.map(id=>({id, font:{size, strokeWidth:size/3}})));
  }
  NET.on('afterDrawing',fitLabels);
  NET.on('click',p=>{
    if(p.nodes.length){ const n=GNODE_BY_ID[p.nodes[0]]; openPanel(n.type==='cluster'?(VIS.clusters[String(n.cid)]||{}).panel:(VIS.urls[n.ui]||{}).panel); return; }
    if(p.edges.length){ const e=GEDGE_BY_ID[p.edges[0]]; if(e.type==='similar') openPanel(VIS.pairs[e.pi].panel); else if(e.type==='merge') openPanel(VIS.merges[e.mi].panel); }
  });
  NET.on('hoverNode',()=>{ el.style.cursor='pointer'; }); NET.on('blurNode',()=>{ el.style.cursor='default'; });
  NET.on('hoverEdge',()=>{ el.style.cursor='pointer'; }); NET.on('blurEdge',()=>{ el.style.cursor='default'; });
  graphMeta();
}
function initGraphControls(){
  const sel=document.getElementById('g-cluster');
  const cl=Object.values(VIS.clusters||{}).filter(c=>c.cid!==-1);
  const rank={fix:0,update:1,ok:2,none:3};
  cl.sort((a,b)=>(rank[a.status]-rank[b.status])||(b.url_count-a.url_count));
  sel.innerHTML='<option value="all">All topics</option>'+cl.map(c=>`<option value="${c.cid}">${c.status==='fix'?'● ':c.status==='update'?'◐ ':''}${esc(c.name)} (${c.url_count})</option>`).join('');
  const kinds=Object.keys(KIND_COLOR).filter(k=>(VIS.graph.nodes||[]).some(n=>n.kind===k));
  document.getElementById('g-kind').innerHTML='<option value="all">All page types</option>'+kinds.map(k=>`<option value="${k}">${KIND_LABEL[k]}</option>`).join('');
  ['g-cluster','g-kind','g-issues'].forEach(id=>document.getElementById(id).addEventListener('change',()=>applyGraphFilter(true)));
  document.getElementById('g-fit').addEventListener('click',()=>{ sel.value='all'; document.getElementById('g-kind').value='all'; document.getElementById('g-issues').checked=false; applyGraphFilter(true); });
}
function applyGraphFilter(fit){
  if(!NET) return;
  const cid=document.getElementById('g-cluster').value, kind=document.getElementById('g-kind').value, issues=document.getElementById('g-issues').checked;
  const hidden={}, liveClusters=new Set(); let visibleUrls=0;
  VIS.graph.nodes.forEach(n=>{
    if(n.type!=='url') return;
    const show=(cid==='all'||String(n.cid)===cid)&&(kind==='all'||n.kind===kind)&&(!issues||n.status!=='ok');
    hidden[n.id]=!show; if(show){ liveClusters.add(n.cid); visibleUrls++; }
  });
  VIS.graph.nodes.forEach(n=>{
    if(n.type!=='cluster') return;
    const show=cid!=='all'?String(n.cid)===cid:(liveClusters.has(n.cid)||(issues&&(n.status==='fix'||n.status==='update')&&kind==='all'));
    hidden[n.id]=!show;
  });
  GNODES.update(VIS.graph.nodes.map(n=>({id:n.id, hidden:hidden[n.id]})));
  GEDGES.update(VIS.graph.edges.map((e,i)=>({id:'e'+i, hidden:!!(hidden[e.from]||hidden[e.to])})));
  graphMeta(visibleUrls);
  if(fit){ const ids=VIS.graph.nodes.filter(n=>!hidden[n.id]).map(n=>n.id); if(ids.length) NET.fit({nodes:ids, animation:{duration:550, easingFunction:'easeInOutQuad'}}); }
}
function placeGraph(slotId){
  const slot=document.getElementById(slotId), wrap=document.getElementById('graph-wrap');
  if(!slot||!wrap) return;
  if(wrap.parentElement!==slot) slot.appendChild(wrap);
  if(slotId==='slot-overview' && NET){
    const changed=document.getElementById('g-cluster').value!=='all'||document.getElementById('g-kind').value!=='all'||document.getElementById('g-issues').checked;
    if(changed){ document.getElementById('g-cluster').value='all'; document.getElementById('g-kind').value='all'; document.getElementById('g-issues').checked=false; applyGraphFilter(false); }
  }
  if(!NET){ buildGraph(); return; }
  setTimeout(()=>{ NET.redraw(); NET.fit({animation:{duration:450, easingFunction:'easeInOutQuad'}}); },40);
}

// ---------- Overlap ----------
let OVERLAP_READY=false;
function selectOverlapCluster(cid){
  const C=(VIS.overlap.clusters||[]); const c=C.find(x=>x.cid===cid)||C[0]; if(!c) return;
  document.getElementById('ov-cluster').value=String(c.cid);
  const n=c.slugs.length;
  document.getElementById('ov-sub').innerHTML=`${n} pages · average similarity <b>${pctTxt(c.avg_sim)}</b> across ${c.n_pairs} pairs · <b style="color:${c.flagged?STATUS_COLOR.fix:STATUS_COLOR.ok}">${c.flagged} pairs ${Math.round(VIS.overlap.threshold*100)}%+ alike</b>${c.risk?` · <b style="color:${STATUS_COLOR.fix}">${c.risk} touch a money page (marked !)</b>`:''}${c.truncated?' · showing the 25 most-overlapping pages':''}`;
  const labels=c.slugs.map((s,i)=>`${i+1}. ${shortSlug(s,30)}`);
  const z=c.z.map(r=>r.map(v=>v==null?null:Math.round(v*100)));
  const risk=new Set(c.risk_cells.map(([i,j])=>i+'_'+j));
  const text=c.z.map((r,i)=>r.map((v,j)=>(risk.has(i+'_'+j)||risk.has(j+'_'+i))?'!':''));
  const custom=c.z.map((r,i)=>r.map((v,j)=>`${esc(c.slugs[i])}<br>${esc(c.slugs[j])}`));
  const zmin=Math.min(50, ...z.flat().filter(v=>v!=null));
  const thr=Math.round(VIS.overlap.threshold*100), cut=(thr-zmin)/(100-zmin);
  const el=document.getElementById('ov-heatmap');
  Plotly.react(el,[{type:'heatmap', z, x:labels, y:labels, text, customdata:custom, texttemplate:'%{text}', textfont:{color:'#ffffff',size:12,family:'Inter'},
      zmin, zmax:100, xgap:2, ygap:2, hoverongaps:false,
      colorscale:[[0,'#151a27'],[Math.max(0,cut-0.001),'#3a3354'],[cut,'#f5a524'],[1,'#f04438']],
      colorbar:{thickness:10, outlinewidth:0, tickfont:{color:'#8a93a6',size:11}, ticksuffix:'%', len:0.9},
      hovertemplate:'%{customdata}<br><b>%{z}% similar</b><extra></extra>'}],
    {...PL, height:Math.min(760, 150+n*24), margin:{t:6,b:140,l:200,r:10},
      xaxis:{tickangle:-45, tickfont:{size:10.5,color:'#8a93a6'}, showgrid:false, zeroline:false},
      yaxis:{autorange:'reversed', tickfont:{size:10.5,color:'#8a93a6'}, showgrid:false, zeroline:false}},
    {responsive:true, displayModeBar:false});
  el.removeAllListeners&&el.removeAllListeners('plotly_click');
  el.on('plotly_click',ev=>{
    const pt=ev.points&&ev.points[0]; if(!pt) return;
    const i=pt.pointNumber[0], j=pt.pointNumber[1], k=c.pairs[i][j];
    if(k!=null) openPanel(VIS.pairs[k].panel);
    else if(c.z[i][j]!=null) openPanel({kicker:'Page pair', title:`${c.slugs[i]}  ↔  ${c.slugs[j]}`, status:'ok', status_label:'Healthy',
      what:`These pages read ${pctTxt(c.z[i][j])} alike, below the ${thr}% overlap threshold.`, why:'Related pages in one topic should be similar; this level is normal.',
      action:'No action needed. Link them to each other where it helps readers.', facts:[], list:[], source:'similarity_scores.csv (similarity)'});
  });
  const pairs=(VIS.pairs||[]).map((p,k)=>({p,k})).filter(x=>x.p.cid===c.cid);
  document.getElementById('ov-pairs-title').textContent=pairs.length?`Pairs to review in “${c.name}” (${pairs.length})`:`No pairs over ${thr}% in “${c.name}”`;
  document.getElementById('ov-pairs').innerHTML=pairs.map(({p,k})=>`<div class="pair-row" data-pair="${k}">
      <div class="slugs">${esc(p.panel.title)}</div>
      ${p.risk?'<span class="b b-r">Money page</span>':'<span></span>'}
      <span class="sim" style="color:${STATUS_COLOR.fix}">${pctTxt(p.sim)}</span></div>`).join('')||'<div class="lane-empty">Nothing above the threshold in this topic.</div>';
}
document.addEventListener('click',e=>{ const r=e.target.closest('[data-pair]'); if(r) openPanel(VIS.pairs[parseInt(r.dataset.pair)].panel); });
registerLazy('overlap',()=>{
  const C=VIS.overlap.clusters||[];
  if(!C.length){ document.getElementById('overlap-body').innerHTML=emptyState('No similarity data','similarity_scores.csv is missing or empty for this run.'); return; }
  const thr=Math.round(VIS.overlap.threshold*100);
  const pts=C.filter(c=>c.avg_sim!=null);
  // Label only the 3 most-flagged topics as offset callouts (rest on hover); callouts on the right half point left so they stay in frame.
  const xmax=Math.max(...pts.map(c=>c.url_count),1);
  const labels=pts.filter(c=>c.flagged).sort((a,b)=>b.flagged-a.flagged).slice(0,3).map((c,i)=>{ const right=c.url_count>xmax*0.6;
    return {x:c.url_count, y:Math.round(c.avg_sim*1000)/10, text:esc(shortSlug(c.name,26)), showarrow:true, arrowhead:0, arrowwidth:1, arrowcolor:'#5a6275',
      ax:right?-40:40, ay:[-34,34,-58][i], xanchor:right?'right':'left', font:{size:11,color:'#c9cedb',family:'Inter'}, bgcolor:'rgba(10,12,17,0.8)'}; });
  Plotly.newPlot('ov-scatter',[{type:'scatter', mode:'markers',
      x:pts.map(c=>c.url_count), y:pts.map(c=>Math.round(c.avg_sim*1000)/10),
      customdata:pts.map(c=>[c.name,c.flagged,c.risk,c.n_pairs,c.cid]),
      hovertemplate:'<b>%{customdata[0]}</b><br>%{x} pages · avg similarity %{y}%<br>%{customdata[1]} pairs '+thr+'%+ alike · %{customdata[2]} touch a money page<extra></extra>',
      marker:{size:pts.map(c=>12+Math.sqrt(c.flagged)*8), color:pts.map(c=>c.flagged?STATUS_COLOR.fix:STATUS_COLOR.ok),
        symbol:pts.map(c=>c.risk?'diamond':'circle'), opacity:0.9, line:{color:'#0a0c11',width:1.5}}}],
    {...PL, height:420, margin:{t:20,b:50,l:56,r:16},
      xaxis:{title:{text:'Pages in topic',font:{size:12}}, gridcolor:'#1c2231', zeroline:false, rangemode:'tozero'},
      yaxis:{title:{text:'Average similarity between its pages (%)',font:{size:12}}, gridcolor:'#1c2231', zeroline:false},
      shapes:[{type:'line', xref:'paper', x0:0, x1:1, y0:thr, y1:thr, line:{color:'rgba(240,68,56,0.5)', dash:'dot', width:1}}],
      annotations:[{xref:'paper', x:1, y:thr, xanchor:'right', yanchor:'bottom', text:thr+'% = pages read alike', showarrow:false, font:{size:11,color:'#f8877e'}}, ...labels]},
    {responsive:true, displayModeBar:false});
  document.getElementById('ov-scatter').on('plotly_click',ev=>{ const pt=ev.points&&ev.points[0]; if(pt) selectOverlapCluster(pt.customdata[4]); });
  const sel=document.getElementById('ov-cluster');
  sel.innerHTML=C.map(c=>`<option value="${c.cid}">${esc(c.name)} — ${c.flagged} flagged</option>`).join('');
  sel.addEventListener('change',()=>selectOverlapCluster(parseInt(sel.value)));
  OVERLAP_READY=true;
  selectOverlapCluster(PENDING_OVERLAP_CID!=null?PENDING_OVERLAP_CID:C[0].cid); PENDING_OVERLAP_CID=null;
});

// ---------- Gaps ----------
registerLazy('gaps',()=>{
  const G=VIS.gaps||{rows:[],competitors:[]}, root=document.getElementById('gaps-body');
  if(!G.rows.length){ root.innerHTML=emptyState('No competitor data','Re-run with <code>--competitor &lt;domain&gt;</code> to compare topic coverage.'); return; }
  const comps=G.competitors;
  document.getElementById('gap-summary').innerHTML=comps.map((name,ci)=>{
    let gap=0, shared=0, adv=0;
    G.rows.forEach(r=>{ const c=r.comps[ci]; if(c&&!r.you) gap++; else if(c&&r.you) shared++; else if(!c&&r.you) adv++; });
    const tot=Math.max(1,gap+shared+adv);
    return `<div class="gs-card"><div class="gs-name">vs ${esc(name)}</div>
      <div class="gs-bar"><span style="width:${gap/tot*100}%;background:${STATUS_COLOR.opportunity}"></span><span style="width:${shared/tot*100}%;background:#3a4256"></span><span style="width:${adv/tot*100}%;background:${STATUS_COLOR.ok}"></span></div>
      <div class="gs-nums"><span><b style="color:#7fb0ff">${gap}</b>gaps</span><span><b style="color:var(--muted)">${shared}</b>shared</span><span><b style="color:${STATUS_COLOR.ok}">${adv}</b>only you</span></div></div>`;
  }).join('');
  const counts=G.counts||{};
  const filters=[['all','All topics',G.rows.length,'#8b5cf6'],['GAP','Gaps',counts.GAP||0,STATUS_COLOR.opportunity],['SHARED','Shared',counts.SHARED||0,'#8a93a6'],['ADVANTAGE','Only you',counts.ADVANTAGE||0,STATUS_COLOR.ok]];
  let cur='all', q='';
  const fEl=document.getElementById('gap-filters');
  fEl.innerHTML=filters.map(([k,l,n,c])=>`<button class="chip${k==='all'?' active':''}" style="--c:${c}" data-gf="${k}"><i></i>${l} · ${n}</button>`).join('');
  const cols=`minmax(220px,2.2fr) 90px repeat(${comps.length},minmax(84px,1fr)) 110px`;
  function draw(){
    const rows=G.rows.map((r,i)=>({r,i})).filter(({r})=>(cur==='all'||r.status===cur)&&(!q||r.topic.toLowerCase().includes(q)));
    const head=`<div class="gm-row gm-head" style="grid-template-columns:${cols}"><div>Topic</div><div style="text-align:center">${esc(SITE_NAME)}</div>${comps.map(c=>`<div style="text-align:center">${esc(c)}</div>`).join('')}<div>Next step</div></div>`;
    const body=rows.map(({r,i})=>{
      const you=r.you?`<div class="cell ${r.status==='ADVANTAGE'?'cell-adv':'cell-shared'}">✓</div>`:'<div class="cell cell-missing">missing</div>';
      const cc=r.comps.map(c=>`<div class="gm-cell">${c?(r.you?'<div class="cell cell-shared">✓</div>':'<div class="cell cell-gap">has it</div>'):'<div class="cell cell-empty"></div>'}</div>`).join('');
      const nxt=r.status==='GAP'?(r.has_idea?'<span class="gm-idea">Brief ready →</span>':'<span class="gm-idea" style="color:var(--muted)">Create page</span>'):'<span style="font-size:11.5px;color:var(--faint)">—</span>';
      return `<div class="gm-row" style="grid-template-columns:${cols}" data-gap="${i}"><div class="gm-topic">${esc(r.topic)}</div><div class="gm-cell">${you}</div>${cc}<div>${nxt}</div></div>`;
    }).join('');
    document.getElementById('gap-matrix').innerHTML=head+(body||'<div class="lane-empty" style="padding:16px">No topics match.</div>');
  }
  fEl.addEventListener('click',e=>{ const b=e.target.closest('[data-gf]'); if(!b) return; cur=b.dataset.gf; fEl.querySelectorAll('.chip').forEach(x=>x.classList.toggle('active',x===b)); draw(); });
  document.getElementById('gap-search').addEventListener('input',debounce(e=>{ q=e.target.value.toLowerCase(); draw(); },120));
  document.getElementById('gap-matrix').addEventListener('click',e=>{ const r=e.target.closest('[data-gap]'); if(!r) return; const row=G.rows[parseInt(r.dataset.gap)]; openPanel(row.panel); });
  draw();
});

// ---------- Action board ----------
registerLazy('actions',()=>{
  const A=VIS.actions||[], root=document.getElementById('board');
  if(!A.length){ root.innerHTML=emptyState('No actions','Nothing to do in this run.'); return; }
  const SHOW=6;
  root.innerHTML=A.map((col,ci)=>{
    const c=STATUS_COLOR[col.status];
    const items=col.items.map((it,ii)=>`<button class="lane-item" data-ai="${ci}_${ii}" ${ii>=SHOW?'hidden':''}><b title="${esc(it.title)}">${esc(it.title)}</b><span>${esc(it.sub)}</span></button>`).join('');
    const more=col.items.length>SHOW?`<button class="lane-more" data-lane="${ci}">Show ${col.items.length-SHOW} more${col.count>col.items.length?` (top ${col.items.length} of ${col.count})`:''}</button>`:'';
    return `<div class="lane" style="--c:${c}"><div class="lane-head"><div class="lane-title"><i></i>${esc(col.label)}</div><div class="lane-count">${col.count}</div></div>
      <p class="lane-blurb">${esc(col.blurb)}</p>${items||'<div class="lane-empty">Nothing here.</div>'}${more}<div class="lane-src">${esc(col.source)}</div></div>`;
  }).join('');
  root.addEventListener('click',e=>{
    const it=e.target.closest('[data-ai]');
    if(it){ const [ci,ii]=it.dataset.ai.split('_').map(Number); openPanel(A[ci].items[ii].panel); return; }
    const m=e.target.closest('[data-lane]');
    if(m){ m.parentElement.querySelectorAll('.lane-item[hidden]').forEach(x=>x.hidden=false); m.remove(); }
  });
});

// ---------- Explorer ----------
let EXP_STATUS='all';
function renderExplorer(filter){
  const fl=(filter||'').toLowerCase();
  const rows=(VIS.urls||[]).map((u,i)=>({u,i})).filter(({u})=>(EXP_STATUS==='all'||u.status===EXP_STATUS)&&(!fl||u.url.toLowerCase().includes(fl)||String(u.cluster).toLowerCase().includes(fl)));
  const tb=document.querySelector('#url-table tbody');
  tb.innerHTML=rows.slice(0,250).map(({u,i})=>`<tr class="clickable" data-ui="${i}">
      <td><span class="url-cell" title="${esc(u.url)}">${esc(u.slug)}</span></td>
      <td><span class="b" style="background:${KIND_COLOR[u.kind]}22;color:${KIND_COLOR[u.kind]}">${esc(KIND_LABEL[u.kind])}</span></td>
      <td>${u.cid===-1?'<span style="color:var(--muted)">Unclustered</span>':esc(u.cluster)}</td>
      <td style="color:var(--muted)">${esc(u.intent||'—')}</td>
      <td style="color:var(--muted)">${esc(u.freshness||'—')}</td>
      <td><span class="pill pill-${u.status}">${esc(u.panel.status_label)}</span></td></tr>`).join('');
  if(rows.length>250) tb.innerHTML+=`<tr><td colspan="6" style="color:var(--muted);text-align:center">Showing 250 of ${rows.length}. Refine your search.</td></tr>`;
  document.getElementById('exp-count').textContent=`${rows.length} pages`;
}
function initExplorer(){
  const counts={all:VIS.urls.length, fix:0, update:0, ok:0}; VIS.urls.forEach(u=>{ if(counts[u.status]!=null) counts[u.status]++; });
  const f=[['all','All','#8b5cf6'],['fix','Fix',STATUS_COLOR.fix],['update','Update',STATUS_COLOR.update],['ok','Healthy',STATUS_COLOR.ok]];
  const el=document.getElementById('exp-filters');
  el.innerHTML=f.map(([k,l,c])=>`<button class="chip${k==='all'?' active':''}" style="--c:${c}" data-ef="${k}"><i></i>${l} · ${counts[k]}</button>`).join('');
  el.addEventListener('click',e=>{ const b=e.target.closest('[data-ef]'); if(!b) return; EXP_STATUS=b.dataset.ef; el.querySelectorAll('.chip').forEach(x=>x.classList.toggle('active',x===b)); renderExplorer(document.getElementById('url-search').value); });
  document.querySelector('#url-table tbody').addEventListener('click',e=>{ const r=e.target.closest('[data-ui]'); if(r) openPanel(VIS.urls[parseInt(r.dataset.ui)].panel); });
  renderExplorer('');
}

function initVisuals(){
  document.getElementById('drawer-close').addEventListener('click',closePanel);
  document.getElementById('scrim').addEventListener('click',closePanel);
  document.addEventListener('keydown',e=>{ if(e.key==='Escape'){ closePanel(); document.getElementById('more-menu').classList.remove('open'); } });
  initMoreMenu();
  renderOverview();
  initGraphControls();
  initExplorer();
}
"""


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
    visuals=None,
    sample_data=False,
):
    if visuals is None:
        visuals = _EMPTY_VISUALS
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
        actions.append({"priority": "P1", "action": f"Validate query and intent overlap in {critical_count} large topic clusters", "impact": "Unverified", "effort": "Review"})
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
    n_overlap = len(visuals.get("pairs", []))
    n_gaps = (visuals.get("gaps", {}).get("counts") or {}).get("GAP", 0)
    more_items = "".join(
        f'<button class="more-item" data-tab="{tid}"><b>{escape(label)}</b><span>{escape(desc)}</span></button>'
        for tid, label, desc in _MORE_TABS
    )
    sample_badge = (
        '<span class="sample-badge" data-tip="Synthetic data generated by scripts/generate_demo_data.py '
        'for a fictional brand. Not a real site or client.">SAMPLE DATA · fictional brand</span>'
        if sample_data else ""
    )
    sample_footer = " &mdash; Sample data for a fictional brand; every number is synthetic." if sample_data else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Topical Authority Map — {site_name}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<script src="{_GRAPH_CDN}"></script>
<style>{_THEME_CSS}</style>
</head>
<body>
<div id="toast"></div>

<header class="topbar">
  <div class="topbar-row">
    <div class="brand">
      <div class="logo"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round"><circle cx="12" cy="12" r="3"/><circle cx="4.5" cy="6" r="1.8"/><circle cx="19.5" cy="6" r="1.8"/><circle cx="12" cy="20.5" r="1.8"/><path d="M6 7l4 3.3M18 7l-4 3.3M12 15v3.7"/></svg></div>
      <div>
        <div class="brand-title">{site_name} <span class="brand-thin">· Topical Authority Map</span></div>
        <div class="brand-sub">{site_domain_safe} · {stats['total_urls']} pages analyzed · {today}</div>
      </div>
      {sample_badge}
    </div>
    <div class="top-actions">
      <a href="run_status.html" class="ghost-btn">Run status</a>
      <a href="javascript:window.print()" class="ghost-btn">Export PDF</a>
    </div>
  </div>
  <nav class="tabs" id="nav" role="tablist">
    <button class="nav-tab active" data-tab="overview">Overview</button>
    <button class="nav-tab" data-tab="map">Cluster Map</button>
    <button class="nav-tab" data-tab="overlap">Overlap <span class="nbadge nbadge-r">{n_overlap}</span></button>
    <button class="nav-tab" data-tab="gaps">Gaps <span class="nbadge nbadge-b">{n_gaps}</span></button>
    <button class="nav-tab" data-tab="actions">Actions</button>
    <button class="nav-tab" data-tab="explorer">Explorer</button>
    <div class="more"><button class="nav-tab more-btn" id="more-btn" aria-haspopup="true"><span id="more-label">More</span> <span class="caret">▾</span></button></div>
  </nav>
</header>
<div class="more-menu" id="more-menu" role="menu">{more_items}</div>

<!-- ==================== OVERVIEW ==================== -->
<section class="tab-pane active" id="tab-overview">
  <div id="headline"></div>
  <div class="kpis" id="kpis"></div>
  <div class="map-card">
    <div class="map-card-head">
      <div><h2>Your site as a map of topics</h2><p>Big circles are topics, small dots are pages. Red means fix, amber means update, green means healthy. Click anything for details.</p></div>
      <button class="link-btn" data-goto="map">Filter the map →</button>
    </div>
    <div class="graph-slot slot-overview" id="slot-overview">
      <div id="graph-wrap" class="graph-wrap">
        <div class="graph-toolbar">
          <label class="ctl">Topic <select id="g-cluster"></select></label>
          <label class="ctl">Page type <select id="g-kind"></select></label>
          <label class="toggle"><input type="checkbox" id="g-issues"><span class="track"></span>Only issues</label>
          <button class="ghost-btn" id="g-fit">Reset</button>
          <span class="graph-meta" id="g-meta"></span>
        </div>
        <div class="graph-stage">
          <div id="graph" class="graph-canvas"></div>
          <div class="graph-loading" id="g-loading"><div class="spinner"></div>Laying out pages…</div>
          <div class="graph-legend" id="g-legend"></div>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- ==================== CLUSTER MAP ==================== -->
<section class="tab-pane" id="tab-map">
  <div class="view-head"><div><h2>Cluster Map</h2><p>How your pages group into topics. Each topic sits at the center of its pages; <b>red lines</b> join pages that read 80%+ alike and <b>dashed lines</b> join topics that may belong together. Filter to one topic, one page type, or only the problems.</p></div></div>
  <div class="graph-slot slot-map" id="slot-map"></div>
</section>

<!-- ==================== OVERLAP ==================== -->
<section class="tab-pane" id="tab-overlap">
  <div class="view-head"><div><h2>Overlap</h2><p>Pages in the same topic whose text reads alike. This is <b>potential topic overlap, not confirmed cannibalization</b>: check which queries each page actually ranks for (Search Console) before merging anything.</p></div></div>
  <div id="overlap-body">
    <div class="grid-2">
      <div class="card">
        <h3>Which topics overlap the most <span class="qmark" data-tip="Similarity compares the meaning of two pages' text, from 0 to 100%. A dot's height is the average across every pair of pages in that topic.">?</span></h3>
        <p class="card-sub">Each dot is a topic. Further right means more pages; higher means its pages read more alike. Red dots have pairs above 80%; a diamond means one pair involves a money page. Click a dot.</p>
        <div id="ov-scatter"></div>
      </div>
      <div class="card">
        <div class="card-head"><h3>Page-by-page similarity</h3><select id="ov-cluster"></select></div>
        <p class="card-sub" id="ov-sub"></p>
        <div id="ov-heatmap"></div>
        <div class="legend-inline"><span><span class="sw" style="background:#3a3354"></span> under 80%: normal for related pages</span><span><span class="sw" style="background:#f5a524"></span> to <span class="sw" style="background:#f04438"></span> 80%+ alike: review</span><span><b style="color:#fff">!</b> money page involved</span></div>
      </div>
    </div>
    <div class="card"><h3 id="ov-pairs-title">Pairs to review</h3><div id="ov-pairs"></div></div>
  </div>
</section>

<!-- ==================== GAPS ==================== -->
<section class="tab-pane" id="tab-gaps">
  <div class="view-head"><div><h2>Competitor gaps</h2><p>Every topic you or a competitor covers. <b style="color:#7fb0ff">Blue cells</b> are gaps: a competitor has a page and you don't. Sorted by how many competitors cover the topic. Click a row for the matching content idea.</p></div></div>
  <div id="gaps-body">
    <div class="gap-summary" id="gap-summary"></div>
    <div class="card">
      <div class="card-head" style="margin-bottom:12px"><div class="chips" id="gap-filters"></div><input type="text" class="srch small" id="gap-search" placeholder="Search topics…"></div>
      <div class="gap-matrix" id="gap-matrix"></div>
    </div>
  </div>
</section>

<!-- ==================== ACTIONS ==================== -->
<section class="tab-pane" id="tab-actions">
  <div class="view-head"><div><h2>Action board</h2><p>Everything the audit found, sorted into five jobs. <b style="color:var(--red)">Red</b> fixes overlap, <b style="color:var(--amber)">amber</b> improves existing pages, <b style="color:#7fb0ff">blue</b> adds new ones. Counts come straight from the audit files; click any item for details.</p></div></div>
  <div class="board" id="board"></div>
</section>

<!-- ==================== TAB: SUMMARY (Health score, under More) ==================== -->
<div class="tab-pane" id="tab-summary">
  <div id="hero-mount"></div>
  <div class="row row-2" style="margin-bottom:14px">
    <div class="card">
      <h3>Key Findings</h3>
      <div id="key-findings" style="font-size:13px;line-height:1.85"></div>
    </div>
    <div class="card">
      <h3>Action Items <span data-tip="Auto-generated from issues found. Prioritized by impact and validated by data.">ⓘ</span></h3>
      <div id="action-items"></div>
    </div>
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
    <h3>Potential overlap by cluster <span data-tip="Shared topics are not proof of competing queries. Validate intent and search data before changing pages.">ⓘ</span></h3>
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
<section class="tab-pane" id="tab-explorer">
  <div class="view-head"><div><h2>Explorer</h2><p>Every page in the audit with its topic, type, <span class="term" data-tip="What the searcher wants: to learn (informational), compare options (commercial), buy (transactional) or find a specific page (navigational).">search intent</span> and status. Click a row for what to do with it.</p></div></div>
  <div class="card-head" style="margin-bottom:12px"><div class="chips" id="exp-filters"></div><span class="graph-meta" id="exp-count"></span></div>
  <input type="text" class="srch" id="url-search" placeholder="Search pages or topics…">
  <div class="card" style="padding:0">
    <h3 style="padding:14px 18px 4px">Pages <button class="csv-btn" data-csv="urls">Download CSV</button></h3>
    <div class="tw" style="border:none;border-radius:0 0 var(--radius) var(--radius)">
      <table id="url-table">
        <thead><tr>
          <th class="sortable" data-sort="text">Page</th>
          <th class="sortable" data-sort="text">Type</th>
          <th class="sortable" data-sort="text">Topic cluster</th>
          <th class="sortable" data-sort="text">Intent</th>
          <th class="sortable" data-sort="text">Freshness</th>
          <th class="sortable" data-sort="text">Status</th>
        </tr></thead>
        <tbody></tbody>
      </table>
    </div>
  </div>
</section>

<div class="scrim" id="scrim"></div>
<aside class="drawer" id="drawer" aria-hidden="true"><button class="drawer-close" id="drawer-close" aria-label="Close">×</button><div id="drawer-body"></div></aside>

<div class="footer">Topical Authority Map &mdash; {site_name} &mdash; {today}{sample_footer}</div>

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
const VIS={_js(visuals)};

// ============================================================================
// HELPERS
// ============================================================================
const SITE_PREFIXES=[
  'https://'+SITE_DOMAIN+'/','http://'+SITE_DOMAIN+'/',
  'https://www.'+SITE_DOMAIN.replace(/^www\\./,'')+'/','http://www.'+SITE_DOMAIN.replace(/^www\\./,'')+'/'
];
function stripUrl(u){{ if(!u||!SITE_DOMAIN)return u||''; for(const p of SITE_PREFIXES){{ if(u.indexOf(p)===0)return '/'+u.slice(p.length); }} return u; }}

// Plotly theme matching the dashboard palette (transparent so charts sit on their cards).
const PB='rgba(0,0,0,0)',PT='#8a93a6';
const PL={{paper_bgcolor:PB,plot_bgcolor:PB,
  font:{{family:'Inter, ui-sans-serif, system-ui, sans-serif',color:PT,size:12}},
  margin:{{t:10,b:30,l:40,r:10}},
  hoverlabel:{{bgcolor:'#1b2131',bordercolor:'#2c3446',font:{{family:'Inter, sans-serif',color:'#e8eaf0',size:12}}}},
  colorway:['#8b5cf6','#22d3ee','#f472b6','#a78bfa','#94a3b8','#3b82f6','#22c55e','#f5a524']}};

const typeColor={{'service':'#f04438','industry':'#f5a524','industry-hub':'#f5a524','local-landing':'#f5a524','blog':'#8b5cf6','tool-review':'#8b5cf6','webinar':'#3b82f6','case-study':'#22c55e','homepage':'#f04438','listing':'#8a93a6'}};
const intentColor={{'comparison':'#8b5cf6','howto':'#3b82f6','definition':'#22c55e','framework':'#f5a524','examples':'#f5a524','metrics':'#06b6d4','checklist':'#a78bfa','guide':'#8b5cf6'}};
const severityColor={{'critical':'#f04438','high':'#f5a524','moderate':'#22c55e'}};

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
  urls: ()=>VIS.urls.length?VIS.urls.map(u=>({{url:u.url,page_type:u.kind,cluster:u.cluster,intent:u.intent,freshness:u.freshness,status:u.status,overlapping_pages:u.n_pairs}})):URL_TABLE,
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
  if(!name||!document.getElementById('tab-'+name)) name='overview';
  document.querySelectorAll('.nav-tab[data-tab]').forEach(t=>t.classList.toggle('active',t.dataset.tab===name));
  // Secondary views live in the "More" menu; light up the More button when one is open.
  let moreLabel='More';
  document.querySelectorAll('.more-item').forEach(t=>{{ const on=t.dataset.tab===name; t.classList.toggle('active',on); if(on) moreLabel=t.querySelector('b').textContent; }});
  const inMore=!PRIMARY_TABS.includes(name);
  document.getElementById('more-btn').classList.toggle('active',inMore);
  document.getElementById('more-label').textContent=inMore?moreLabel:'More';
  document.getElementById('more-menu').classList.remove('open');
  document.querySelectorAll('.tab-pane').forEach(p=>p.classList.toggle('active',p.id==='tab-'+name));
  if(name==='overview') placeGraph('slot-overview');
  if(name==='map') placeGraph('slot-map');
  runLazy(name);
  // Resize only the visible tab's plots (avoids stale layout)
  setTimeout(()=>{{
    document.querySelectorAll('#tab-'+name+' .js-plotly-plot').forEach(el=>{{ try{{Plotly.Plots.resize(el);}}catch(e){{}} }});
  }},20);
  if(history.replaceState) history.replaceState(null,'','#tab='+name);
}}
document.querySelectorAll('.nav-tab[data-tab], .more-item').forEach(tab=>{{
  tab.addEventListener('click',()=>activateTab(tab.dataset.tab));
}});

// Parse hash on boot
function applyHash(){{
  const h=window.location.hash.replace('#','');
  if(!h) return;
  const params={{}}; h.split('&').forEach(p=>{{const [k,v]=p.split('='); params[k]=v;}});
  activateTab(params.tab||'overview');
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
    sparkHTML=`<svg width="${{w}}" height="${{h}}" viewBox="0 0 ${{w}} ${{h}}"><polyline fill="none" stroke="#8b5cf6" stroke-width="2" points="${{pts.join(' ')}}"/><circle cx="${{pts[pts.length-1].split(',')[0]}}" cy="${{pts[pts.length-1].split(',')[1]}}" r="2.5" fill="#8b5cf6"/></svg>`;
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
  const subColor={{green:'#22c55e',yellow:'#f5a524',red:'#f04438',unknown:'#8a93a6'}};
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
  const colors=TREEMAP.labels.map(name=>{{ const s=sevByName[name]; return s?(severityColor[s.sev]||'#8b5cf6'):'#3b82f6'; }});
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
    marker:{{colors,line:{{width:2,color:'#0a0c11'}},pad:{{t:2,l:2,r:2,b:2}}}},
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
    marker:{{color:CANNIB_CHART.values.slice().reverse().map(v=>v>=10?'#f04438':v>=6?'#f5a524':'#22c55e')}},
    text:CANNIB_CHART.values.slice().reverse(),textposition:'outside',textfont:{{color:'#8a93a6',size:11}},
  }}],{{...PL,height:Math.max(400,CANNIB_CHART.labels.length*26),margin:{{t:10,b:20,l:200,r:60}},
    xaxis:{{gridcolor:'#1c2231'}},yaxis:{{tickfont:{{size:12,color:'#e8eaf0'}}}}}},
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
            const ipc={{transactional:'#22c55e',commercial:'#3b82f6',navigational:'#8a93a6',informational:'#8b5cf6'}};
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
              <td style="color:${{s.conversion_risk?'#f04438':s.similarity>=0.92?'#f04438':'#f5a524'}};font-weight:700">${{(s.similarity*100).toFixed(0)}}%</td>
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
  const iC={{informational:'#8b5cf6',commercial:'#3b82f6',transactional:'#22c55e',navigational:'#8a93a6'}};
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
  const fC={{'Fresh (< 1 month)':'#22c55e','Recent (1-3 months)':'#4ade80','Aging (3-6 months)':'#f5a524','Stale (6-12 months)':'#f5a524','Decaying (12+ months)':'#f04438'}};
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
      marker:{{color:fL.slice().reverse().map(l=>fC[l])}},text:fV.slice().reverse(),textposition:'outside',textfont:{{color:'#8a93a6',size:12}}}}],
      {{...PL,height:240,margin:{{t:10,b:20,l:200,r:60}},xaxis:{{gridcolor:'#1c2231'}},yaxis:{{tickfont:{{size:13,color:'#e8eaf0'}}}}}},
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
  const bC={{'On-brand':'#22c55e','Partially aligned':'#f5a524','Needs work':'#f5a524','Off-brand':'#f04438'}};
  Plotly.newPlot('brand-chart',[{{type:'pie',labels:bL,values:bV,hole:0.6,textinfo:'label+percent',
    marker:{{colors:bL.map(l=>bC[l]||'#6b7280')}},textfont:{{size:12}}}}],
    {{...PL,height:260,showlegend:false,margin:{{t:10,b:10,l:10,r:10}}}},{{responsive:true,displayModeBar:false}});

  // Radial gauge
  Plotly.newPlot('brand-gauge',[{{
    type:'indicator',mode:'gauge+number',value:ENH.brand.avg_score,
    number:{{font:{{size:42,color:'#e8eaf0'}}}},
    gauge:{{
      axis:{{range:[0,100],tickfont:{{color:'#8a93a6'}}}},
      bar:{{color:'#8b5cf6'}},
      bgcolor:'#0a0c11', borderwidth:0,
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
    <td style="font-weight:700;color:${{b.brand_score<25?'#f04438':b.brand_score<50?'#f5a524':'#f5a524'}}">${{b.brand_score}}</td>
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
    marker:{{color:Object.keys(cG).map(k=>k==='GAP'?'#f04438':k==='ADVANTAGE'?'#22c55e':'#8b5cf6')}},
    text:Object.values(cG),textposition:'outside',textfont:{{color:'#8a93a6',size:11}}}}],
    {{...PL,height:140,margin:{{t:5,b:20,l:120,r:50}},yaxis:{{tickfont:{{size:12,color:'#e8eaf0'}}}},xaxis:{{gridcolor:'#1c2231'}}}},
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
      const ic=intentColor[i.intent]||'#8b5cf6';
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

  const palette=['#8b5cf6','#8b5cf6','#3b82f6','#22c55e','#f5a524','#f04438','#f5a524','#06b6d4','#a78bfa','#84cc16','#ec4899','#14b8a6','#f59e0b','#10b981','#6b7280'];
  const traces=Object.entries(byCluster).map(([cid,g],i)=>{{
    const isOrphan=parseInt(cid)===-1;
    const color=isOrphan?'#4b5563':palette[i%palette.length];
    return {{
      type:'scattergl',mode:'markers',name:g.name,
      x:g.x,y:g.y,
      text:g.urls.map((u,idx)=>{{ const slug=stripUrl(u); const intent=g.intent[idx]?` · ${{g.intent[idx]}}`:''; const pt=g.ptype[idx]?` · ${{g.ptype[idx]}}`:''; return `<b>${{g.name}}</b><br>${{slug}}${{pt}}${{intent}}`; }}),
      hovertemplate:'%{{text}}<extra></extra>',
      marker:{{size:isOrphan?5:8,color:color,line:{{width:0.5,color:'#0a0c11'}},opacity:isOrphan?0.5:0.85}},
    }};
  }});
  Plotly.newPlot('vmap-chart',traces,{{
    ...PL,height:520,
    margin:{{t:10,b:10,l:10,r:10}},
    xaxis:{{showgrid:false,zeroline:false,showticklabels:false}},
    yaxis:{{showgrid:false,zeroline:false,showticklabels:false}},
    showlegend:true,legend:{{font:{{size:11,color:'#e8eaf0'}},bgcolor:'rgba(0,0,0,0)',orientation:'v'}},
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
          <td style="color:${{m.similarity>=0.85?'#f04438':'#f5a524'}};font-weight:700">${{(m.similarity*100).toFixed(0)}}%</td>
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
function renderUrlTable(filter=''){{ renderExplorer(filter); }}

{_VISUALS_JS}

// ============================================================================
// BOOT
// ============================================================================
renderHero();
renderKeyFindings();
renderActionItems();
renderClusterTable();
renderCannib();
initVisuals();
makeSortable('cluster-table');
makeSortable('url-table');

document.getElementById('cluster-search').addEventListener('input',debounce(e=>renderClusterTable(e.target.value),150));
document.getElementById('cannib-search').addEventListener('input',debounce(e=>renderCannib(e.target.value),150));
document.getElementById('url-search').addEventListener('input',debounce(e=>renderUrlTable(e.target.value),150));

// Landing view is the Overview (KPIs + Cluster Map); hash routing can deep-link elsewhere.
if(window.location.hash) applyHash(); else activateTab('overview');
</script>
</body>
</html>"""
