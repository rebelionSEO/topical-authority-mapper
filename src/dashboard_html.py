"""Tabbed HTML template for the Topical Authority dashboard."""

import json


def build_html(treemap_data, cannib_chart_data, cannib_detail, content_types,
               all_clusters, url_table, stats, thin_tools, thin_local, thin_other,
               top_cannib_summary, enhancements=None):
    if enhancements is None:
        enhancements = {}

    total_thin = stats['thin_tools'] + stats['thin_local'] + stats['thin_other']
    total_cannib_urls = sum(c["count"] for c in cannib_detail)
    critical_count = sum(1 for c in cannib_detail if c["severity"] == "critical")
    high_count = sum(1 for c in cannib_detail if c["severity"] == "high")
    has_comp = "competitor" in enhancements
    has_sim = "similarity" in enhancements
    has_intent = "intent" in enhancements
    has_fresh = "freshness" in enhancements
    has_brand = "brand" in enhancements
    has_merge = "merges" in enhancements

    # Action items for the summary tab
    actions = []
    actions.append({"priority": "P1", "action": f"Consolidate {critical_count} critical cannibalized clusters (10+ competing URLs each)", "impact": "High", "effort": "2 weeks"})
    actions.append({"priority": "P1", "action": f"Merge {len([s for s in enhancements.get('similarity',[]) if s.get('similarity',0)>=0.92])} near-duplicate page pairs (92%+ similarity)", "impact": "High", "effort": "1 week"})
    if has_fresh:
        stale = sum(v for k, v in enhancements["freshness"].items() if "Stale" in k or "Decaying" in k)
        actions.append({"priority": "P1", "action": f"Refresh {stale} stale/decaying pages (6+ months old)", "impact": "High", "effort": "3-4 weeks"})
    actions.append({"priority": "P2", "action": f"Expand {total_thin} thin content pages to 500+ words or noindex", "impact": "Medium", "effort": "3 weeks"})
    if has_comp:
        gaps = enhancements["comp_stats"]["gaps"]
        actions.append({"priority": "P2", "action": f"Create content for {gaps} competitor topic gaps", "impact": "Medium", "effort": "4 weeks"})
    actions.append({"priority": "P2", "action": f"Resolve {stats['noise']} unclustered orphan pages", "impact": "Medium", "effort": "1 week"})
    if has_brand:
        off = sum(v for k, v in enhancements["brand"]["distribution"].items() if k in ("Off-brand", "Needs work"))
        actions.append({"priority": "P3", "action": f"Align {off} off-brand pages with brand voice guidelines", "impact": "Low", "effort": "Ongoing"})
    actions.append({"priority": "P3", "action": "Diversify content types: add comparison pages and how-to guides", "impact": "Medium", "effort": "4 weeks"})

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Topical Authority Audit — Azarian Growth Agency</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
:root {{ --bg:#0f1117; --surface:#1a1d27; --border:#2a2d3a; --text:#e4e4e7; --muted:#9ca3af; --accent:#6366f1; --red:#ef4444; --green:#22c55e; --yellow:#eab308; --blue:#3b82f6; }}
*{{ margin:0; padding:0; box-sizing:border-box; }}
body{{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; background:var(--bg); color:var(--text); line-height:1.6; }}
/* Header */
.header{{ background:var(--surface); border-bottom:1px solid var(--border); padding:20px 32px; display:flex; justify-content:space-between; align-items:center; }}
.header h1{{ font-size:18px; font-weight:700; }}
.header .meta{{ font-size:12px; color:var(--muted); }}
/* Nav */
.nav{{ display:flex; background:#13151f; border-bottom:1px solid var(--border); position:sticky; top:0; z-index:100; overflow-x:auto; padding:0 16px; }}
.nav-tab{{ padding:12px 18px; font-size:13px; font-weight:500; color:var(--muted); cursor:pointer; border-bottom:2px solid transparent; white-space:nowrap; transition:all 0.15s; }}
.nav-tab:hover{{ color:var(--text); }}
.nav-tab.active{{ color:var(--accent); border-bottom-color:var(--accent); }}
.nbadge{{ display:inline-block; padding:1px 6px; border-radius:8px; font-size:10px; margin-left:4px; }}
.nbadge-r{{ background:rgba(239,68,68,0.15); color:var(--red); }}
.nbadge-b{{ background:rgba(99,102,241,0.15); color:var(--accent); }}
/* Tab content */
.tab-pane{{ display:none; padding:28px 32px; }}
.tab-pane.active{{ display:block; }}
/* Stats row */
.stats{{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:1px; background:var(--border); margin-bottom:24px; }}
.stat{{ background:var(--surface); padding:20px 16px; text-align:center; }}
.stat .v{{ font-size:32px; font-weight:700; }}
.stat .l{{ font-size:10px; color:var(--muted); text-transform:uppercase; letter-spacing:1px; margin-top:2px; }}
/* Cards */
.card{{ background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:20px; margin-bottom:16px; }}
.card h3{{ font-size:14px; color:var(--muted); text-transform:uppercase; letter-spacing:0.5px; margin-bottom:12px; }}
.row{{ display:grid; gap:16px; }}
.row-2{{ grid-template-columns:1fr 1fr; }}
.row-3{{ grid-template-columns:1fr 1fr 1fr; }}
.row-2-1{{ grid-template-columns:2fr 1fr; }}
/* Tables */
table{{ width:100%; border-collapse:collapse; font-size:13px; }}
th{{ text-align:left; padding:10px 12px; background:#111320; color:var(--muted); font-weight:500; text-transform:uppercase; font-size:11px; letter-spacing:0.5px; position:sticky; top:0; z-index:1; }}
td{{ padding:10px 12px; border-bottom:1px solid var(--border); vertical-align:top; }}
tr:hover td{{ background:rgba(99,102,241,0.05); }}
.tw{{ max-height:500px; overflow-y:auto; border:1px solid var(--border); border-radius:8px; }}
/* Badges */
.b{{ display:inline-block; padding:2px 8px; border-radius:10px; font-size:11px; font-weight:600; }}
.b-r{{ background:rgba(239,68,68,0.15); color:var(--red); }}
.b-y{{ background:rgba(234,179,8,0.15); color:var(--yellow); }}
.b-g{{ background:rgba(34,197,94,0.15); color:var(--green); }}
.b-b{{ background:rgba(59,130,246,0.15); color:var(--blue); }}
.b-m{{ background:rgba(156,163,175,0.1); color:var(--muted); }}
/* Search */
.srch{{ width:100%; padding:10px 14px; background:var(--surface); border:1px solid var(--border); border-radius:8px; color:var(--text); font-size:14px; margin-bottom:12px; outline:none; }}
.srch:focus{{ border-color:var(--accent); }}
/* Expandable */
.expand{{ cursor:pointer; }}
.expand-body{{ display:none; margin-top:12px; padding-top:12px; border-top:1px solid var(--border); }}
.expand.open .expand-body{{ display:block; }}
.expand-arrow{{ color:var(--muted); transition:transform 0.2s; display:inline-block; }}
.expand.open .expand-arrow{{ transform:rotate(90deg); }}
/* Detail panel */
.detail{{ display:none; background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:16px; margin-bottom:12px; }}
.detail.show{{ display:block; }}
/* Action items */
.action-row{{ display:grid; grid-template-columns:60px 1fr 80px 80px; gap:12px; padding:10px 0; border-bottom:1px solid var(--border); align-items:center; font-size:13px; }}
.action-row:last-child{{ border-bottom:none; }}
.priority{{ font-weight:700; font-size:12px; }}
.priority.p1{{ color:var(--red); }}
.priority.p2{{ color:var(--yellow); }}
.priority.p3{{ color:var(--blue); }}
a{{ color:var(--blue); text-decoration:none; }}
a:hover{{ text-decoration:underline; }}
.kw{{ color:var(--muted); font-size:12px; max-width:280px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
.footer{{ padding:16px 32px; text-align:center; font-size:11px; color:var(--muted); border-top:1px solid var(--border); }}
</style>
</head>
<body>

<div class="header">
  <div><h1>Topical Authority Audit</h1><span class="meta">azariangrowthagency.com</span></div>
  <div class="meta">April 2026 &mdash; {stats['total_urls']} pages analyzed</div>
</div>

<div class="nav" id="nav">
  <div class="nav-tab active" data-tab="summary">Summary &amp; Actions</div>
  <div class="nav-tab" data-tab="clusters">Topic Clusters <span class="nbadge nbadge-b">{stats['total_clusters']}</span></div>
  <div class="nav-tab" data-tab="cannib">Cannibalization <span class="nbadge nbadge-r">{stats['cannib_flags']}</span></div>
  <div class="nav-tab" data-tab="duplicates">Duplicates <span class="nbadge nbadge-r">{len(enhancements.get('similarity',[]))}</span></div>
  <div class="nav-tab" data-tab="thin">Thin Content <span class="nbadge nbadge-r">{total_thin}</span></div>
  <div class="nav-tab" data-tab="intent">Search Intent</div>
  <div class="nav-tab" data-tab="freshness">Freshness</div>
  <div class="nav-tab" data-tab="brand">Brand Voice</div>
  <div class="nav-tab" data-tab="competitors">Competitors</div>
  <div class="nav-tab" data-tab="merges">Cluster Merges</div>
  <div class="nav-tab" data-tab="explorer">URL Explorer</div>
</div>

<!-- ==================== TAB: SUMMARY ==================== -->
<div class="tab-pane active" id="tab-summary">
  <div class="stats">
    <div class="stat"><div class="v" style="color:var(--accent)">{stats['total_urls']}</div><div class="l">URLs Analyzed</div></div>
    <div class="stat"><div class="v" style="color:var(--accent)">{stats['total_clusters']}</div><div class="l">Topic Clusters</div></div>
    <div class="stat"><div class="v" style="color:var(--red)">{stats['cannib_flags']}</div><div class="l">Cannibalization</div></div>
    <div class="stat"><div class="v" style="color:var(--yellow)">{total_thin}</div><div class="l">Thin Pages</div></div>
    <div class="stat"><div class="v" style="color:var(--muted)">{stats['noise']}</div><div class="l">Orphan Pages</div></div>
  </div>

  <div class="row row-2" style="margin-bottom:20px">
    <div class="card">
      <h3>Key Findings</h3>
      <div style="font-size:13px;line-height:1.9;">
        <div><span class="b b-r">Critical</span> <strong>{stats['cannib_flags']}</strong> clusters with content cannibalization — pages competing against each other for the same keywords</div>
        <div><span class="b b-r">Critical</span> <strong>{len([s for s in enhancements.get('similarity',[]) if s.get('similarity',0)>=0.92])}</strong> near-duplicate page pairs (92%+ identical content)</div>
        <div><span class="b b-y">Warning</span> <strong>{total_thin}</strong> thin content pages under 300 words consuming crawl budget</div>
        {'<div><span class="b b-y">Warning</span> <strong>' + str(sum(v for k,v in enhancements["freshness"].items() if "Stale" in k or "Decaying" in k)) + '</strong> pages are 6+ months stale (75% of all content)</div>' if has_fresh else ''}
        {'<div><span class="b b-b">Info</span> <strong>' + str(enhancements["comp_stats"]["gaps"]) + '</strong> topic gaps vs competitors (NoGood + SingleGrain)</div>' if has_comp else ''}
        {'<div><span class="b b-b">Info</span> Brand voice avg score: <strong>' + str(enhancements["brand"]["avg_score"]) + '/100</strong> — only 4% of pages fully on-brand</div>' if has_brand else ''}
        <div><span class="b b-g">Strength</span> <strong>{stats['total_clusters']}</strong> topic clusters with strong ICP alignment (Legal, PE, Fintech, SaaS)</div>
      </div>
    </div>
    <div class="card">
      <h3>Content Type Distribution</h3>
      <div id="pie-summary"></div>
    </div>
  </div>

  <div class="card">
    <h3>Action Items</h3>
    <div>
      <div class="action-row" style="border-bottom:1px solid var(--border);font-weight:600;font-size:11px;color:var(--muted);text-transform:uppercase;">
        <div>Priority</div><div>Action</div><div>Impact</div><div>Effort</div>
      </div>
      {''.join(f'<div class="action-row"><div class="priority {a["priority"].lower()}">{a["priority"]}</div><div>{a["action"]}</div><div>{a["impact"]}</div><div style="color:var(--muted)">{a["effort"]}</div></div>' for a in actions)}
    </div>
  </div>
</div>

<!-- ==================== TAB: CLUSTERS ==================== -->
<div class="tab-pane" id="tab-clusters">
  <div class="card"><h3>Topic Cluster Map (top 30)</h3><div id="treemap"></div></div>
  <input type="text" class="srch" id="cluster-search" placeholder="Search clusters by name, keyword, or content type...">
  <div id="cluster-detail" class="detail">
    <h3 id="detail-title" style="font-size:16px;margin-bottom:8px;"></h3>
    <div class="row row-2" style="margin-bottom:8px;font-size:13px;">
      <div><strong>Keywords:</strong> <span id="detail-kw" style="color:var(--muted)"></span></div>
      <div><strong>Content Type:</strong> <span id="detail-type"></span></div>
      <div><strong>Angle:</strong> <span id="detail-angle" style="color:var(--muted)"></span></div>
      <div><strong>CTA Style:</strong> <span id="detail-cta" style="color:var(--muted)"></span></div>
    </div>
    <strong>URLs:</strong>
    <div id="detail-urls" style="max-height:200px;overflow-y:auto;"></div>
  </div>
  <div class="tw"><table id="cluster-table"><thead><tr><th>ID</th><th>Cluster</th><th>URLs</th><th>Keywords</th><th>Type</th><th>Status</th></tr></thead><tbody></tbody></table></div>
</div>

<!-- ==================== TAB: CANNIBALIZATION ==================== -->
<div class="tab-pane" id="tab-cannib">
  <div class="card"><h3>Cannibalization by cluster</h3><div id="cannib-bar"></div></div>
  <input type="text" class="srch" id="cannib-search" placeholder="Search cannibalized clusters...">
  <div id="cannib-list"></div>
</div>

<!-- ==================== TAB: DUPLICATES ==================== -->
<div class="tab-pane" id="tab-duplicates">
  <div class="stats" style="grid-template-columns:repeat(4,1fr)">
    <div class="stat"><div class="v" style="color:var(--red)" id="dup-conv">0</div><div class="l">Conversion Risks</div></div>
    <div class="stat"><div class="v" style="color:var(--red)" id="dup-exact">0</div><div class="l">Near-Identical (92%+)</div></div>
    <div class="stat"><div class="v" style="color:var(--yellow)" id="dup-high">0</div><div class="l">Very Similar (80-92%)</div></div>
    <div class="stat"><div class="v" style="color:var(--accent)" id="dup-total">0</div><div class="l">Total Flagged Pairs</div></div>
  </div>
  <p style="color:var(--muted);font-size:13px;margin-bottom:16px"><span class="b b-r">Conversion Risk</span> = a blog/info page competing against a service/money page for the same topic. The blog may outrank the service page, pushing users away from conversion.</p>
  <div class="tw"><table id="sim-table"><thead><tr><th>URL A</th><th>Type</th><th>URL B</th><th>Type</th><th>Similarity</th><th>Action</th></tr></thead><tbody></tbody></table></div>
</div>

<!-- ==================== TAB: THIN CONTENT ==================== -->
<div class="tab-pane" id="tab-thin">
  <div class="stats" style="grid-template-columns:repeat(3,1fr)">
    <div class="stat"><div class="v" style="color:var(--yellow)">{stats['thin_tools']}</div><div class="l">Tool Review Pages</div></div>
    <div class="stat"><div class="v" style="color:var(--red)">{stats['thin_local']}</div><div class="l">Local Landing Pages</div></div>
    <div class="stat"><div class="v" style="color:var(--muted)">{stats['thin_other']}</div><div class="l">Other Thin Pages</div></div>
  </div>
  <div id="thin-tools-card" class="card expand" onclick="this.classList.toggle('open')"><div style="display:flex;justify-content:space-between;align-items:center"><h3><span class="b b-y">{stats['thin_tools']}</span> Tool Review Pages</h3><span class="expand-arrow">&#9654;</span></div><div class="expand-body" id="thin-tools-body"></div></div>
  <div id="thin-local-card" class="card expand" onclick="this.classList.toggle('open')"><div style="display:flex;justify-content:space-between;align-items:center"><h3><span class="b b-r">{stats['thin_local']}</span> Local / City Landing Pages</h3><span class="expand-arrow">&#9654;</span></div><div class="expand-body" id="thin-local-body"></div></div>
  <div id="thin-other-card" class="card expand" onclick="this.classList.toggle('open')"><div style="display:flex;justify-content:space-between;align-items:center"><h3><span class="b b-m">{stats['thin_other']}</span> Other Thin Pages</h3><span class="expand-arrow">&#9654;</span></div><div class="expand-body" id="thin-other-body"></div></div>
</div>

<!-- ==================== TAB: INTENT ==================== -->
<div class="tab-pane" id="tab-intent">
  <div class="row row-2-1">
    <div class="card"><h3>Search Intent Distribution</h3><div id="intent-chart"></div></div>
    <div class="card" id="intent-summary" style="display:flex;flex-direction:column;justify-content:center;font-size:15px;line-height:2.4;"></div>
  </div>
</div>

<!-- ==================== TAB: FRESHNESS ==================== -->
<div class="tab-pane" id="tab-freshness">
  <div class="card"><h3>Content Age Distribution</h3><div id="freshness-chart"></div></div>
</div>

<!-- ==================== TAB: BRAND VOICE ==================== -->
<div class="tab-pane" id="tab-brand">
  <div class="row row-2-1">
    <div class="card"><h3>Brand Voice Alignment</h3><div id="brand-chart"></div></div>
    <div class="card" style="display:flex;flex-direction:column;justify-content:center;align-items:center;"><div style="font-size:56px;font-weight:800;color:var(--accent)" id="brand-avg">&mdash;</div><div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:1px">Avg Score / 100</div></div>
  </div>
  <div class="card"><h3>Lowest Scoring Pages</h3>
    <div class="tw"><table id="brand-table"><thead><tr><th>URL</th><th>Score</th><th>Rating</th><th>Tone Match</th><th>Violations</th></tr></thead><tbody></tbody></table></div>
  </div>
</div>

<!-- ==================== TAB: COMPETITORS ==================== -->
<div class="tab-pane" id="tab-competitors">
  <div class="stats" style="grid-template-columns:repeat(3,1fr)">
    <div class="stat"><div class="v" style="color:var(--green)" id="comp-adv">0</div><div class="l">Azarian Advantages</div></div>
    <div class="stat"><div class="v" style="color:var(--blue)" id="comp-shared">0</div><div class="l">Shared Topics</div></div>
    <div class="stat"><div class="v" style="color:var(--red)" id="comp-gaps">0</div><div class="l">Content Gaps</div></div>
  </div>
  <div class="card"><div id="comp-chart"></div></div>
  <input type="text" class="srch" id="comp-search" placeholder="Search topics...">
  <div class="tw"><table id="comp-table"><thead><tr><th>Topic</th><th>Azarian</th><th>NoGood</th><th>SingleGrain</th><th>Status</th></tr></thead><tbody></tbody></table></div>
</div>

<!-- ==================== TAB: MERGES ==================== -->
<div class="tab-pane" id="tab-merges">
  <p style="color:var(--muted);margin-bottom:16px;font-size:14px">Clusters with high semantic overlap that should be combined to strengthen topical authority.</p>
  <div class="tw"><table id="merge-table"><thead><tr><th>Cluster A</th><th>Cluster B</th><th>Similarity</th><th>Recommendation</th></tr></thead><tbody></tbody></table></div>
</div>

<!-- ==================== TAB: URL EXPLORER ==================== -->
<div class="tab-pane" id="tab-explorer">
  <input type="text" class="srch" id="url-search" placeholder="Search URLs...">
  <div class="tw"><table id="url-table"><thead><tr><th>URL</th><th>Cluster ID</th><th>Cluster Name</th><th>Secondary</th></tr></thead><tbody></tbody></table></div>
</div>

<div class="footer">Topical Authority Audit &mdash; Azarian Growth Agency &mdash; April 2026</div>

<script>
// === DATA ===
const TREEMAP={json.dumps(treemap_data)};
const CANNIB_CHART={json.dumps(cannib_chart_data)};
const CANNIB_DETAIL={json.dumps(cannib_detail)};
const CONTENT_TYPES={json.dumps(content_types)};
const ALL_CLUSTERS={json.dumps(all_clusters)};
const URL_TABLE={json.dumps(url_table)};
const THIN_TOOLS={json.dumps(thin_tools)};
const THIN_LOCAL={json.dumps(thin_local)};
const THIN_OTHER={json.dumps(thin_other)};
const ENH={json.dumps(enhancements)};

const PB='#1a1d27',PT='#9ca3af';
const PL={{paper_bgcolor:PB,plot_bgcolor:PB,font:{{color:PT,size:12}},margin:{{t:10,b:30,l:40,r:10}}}};

// === TAB NAVIGATION ===
document.querySelectorAll('.nav-tab').forEach(tab=>{{
  tab.addEventListener('click',()=>{{
    document.querySelectorAll('.nav-tab').forEach(t=>t.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(p=>p.classList.remove('active'));
    tab.classList.add('active');
    const pane=document.getElementById('tab-'+tab.dataset.tab);
    if(pane)pane.classList.add('active');
    // Trigger Plotly resize for charts
    window.dispatchEvent(new Event('resize'));
  }});
}});

// === SUMMARY TAB ===
Plotly.newPlot('pie-summary',[{{
  type:'pie',labels:Object.keys(CONTENT_TYPES),values:Object.values(CONTENT_TYPES),
  hole:0.5,textinfo:'label+percent',
  marker:{{colors:['#6366f1','#8b5cf6','#a78bfa','#c4b5fd','#3b82f6','#60a5fa']}},textfont:{{size:11}},
}}],{{...PL,height:280,showlegend:false,margin:{{t:5,b:5,l:5,r:5}}}},{{responsive:true}});

// === CLUSTERS TAB ===
Plotly.newPlot('treemap',[{{
  type:'treemap',labels:TREEMAP.labels,values:TREEMAP.values,
  parents:TREEMAP.labels.map(()=>''),
  text:TREEMAP.keywords.map(k=>k.split(',').slice(0,3).join(', ')),
  hovertemplate:'<b>%{{label}}</b><br>%{{value}} URLs<br>%{{text}}<extra></extra>',
  textinfo:'label+value',textfont:{{size:14,color:'#fff'}},
  marker:{{colorscale:'Viridis',colors:TREEMAP.values}},
}}],{{...PL,margin:{{t:10,b:10,l:10,r:10}},height:420}},{{responsive:true}});

function renderClusterTable(f=''){{
  const tb=document.querySelector('#cluster-table tbody'),fl=f.toLowerCase();
  const rows=ALL_CLUSTERS.filter(c=>!fl||c.name.toLowerCase().includes(fl)||c.keywords.toLowerCase().includes(fl)||c.content_type.toLowerCase().includes(fl));
  tb.innerHTML=rows.map(c=>`<tr style="cursor:pointer" onclick="showDetail(${{c.id}})"><td>${{c.id}}</td><td><strong>${{c.name}}</strong></td><td>${{c.urls}}</td><td class="kw">${{c.keywords}}</td><td><span class="b b-b">${{c.content_type||'-'}}</span></td><td>${{c.cannibalized?'<span class="b b-r">Cannibalized</span>':'<span class="b b-g">OK</span>'}}</td></tr>`).join('');
}}
renderClusterTable();
document.getElementById('cluster-search').addEventListener('input',e=>renderClusterTable(e.target.value));

function showDetail(id){{
  const c=ALL_CLUSTERS.find(x=>x.id===id);if(!c)return;
  const urls=URL_TABLE.filter(u=>u.cluster===id);
  document.getElementById('detail-title').textContent=`[${{c.id}}] ${{c.name}} — ${{c.urls}} URLs`;
  document.getElementById('detail-kw').textContent=c.keywords;
  document.getElementById('detail-type').textContent=c.content_type;
  document.getElementById('detail-angle').textContent=c.angle;
  document.getElementById('detail-cta').textContent=c.cta;
  document.getElementById('detail-urls').innerHTML=urls.map(u=>`<a href="${{u.url}}" target="_blank" style="display:block;padding:3px 0;font-size:13px">${{u.url}}</a>`).join('');
  document.getElementById('cluster-detail').classList.add('show');
}}

// === CANNIBALIZATION TAB ===
Plotly.newPlot('cannib-bar',[{{
  type:'bar',y:CANNIB_CHART.labels.slice().reverse(),x:CANNIB_CHART.values.slice().reverse(),orientation:'h',
  marker:{{color:CANNIB_CHART.values.slice().reverse().map(v=>v>=10?'#ef4444':v>=6?'#eab308':'#22c55e')}},
  text:CANNIB_CHART.values.slice().reverse(),textposition:'outside',textfont:{{color:'#9ca3af',size:11}},
}}],{{...PL,height:Math.max(400,CANNIB_CHART.labels.length*26),margin:{{t:10,b:20,l:200,r:60}},xaxis:{{gridcolor:'#2a2d3a'}},yaxis:{{tickfont:{{size:12,color:'#e4e4e7'}}}}}},{{responsive:true}});

const typeColor={{'service':'#ef4444','industry':'#f97316','industry-hub':'#f97316','local-landing':'#eab308','blog':'#6366f1','tool-review':'#8b5cf6','webinar':'#3b82f6','case-study':'#22c55e','homepage':'#ef4444','listing':'#9ca3af'}};
const roleIcon={{'money':'$','support':'~','content':''}};

function renderCannib(f=''){{
  const fl=f.toLowerCase();
  const items=CANNIB_DETAIL.filter(c=>!fl||c.name.toLowerCase().includes(fl)||c.analysis.toLowerCase().includes(fl));
  document.getElementById('cannib-list').innerHTML=items.map(c=>{{
    const convBorder=c.has_conversion_risk?'border-left:3px solid var(--red);':'';
    return `
    <div class="card expand" onclick="this.classList.toggle('open')" style="cursor:pointer;${{convBorder}}">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <div>
          <strong>${{c.name}}</strong>
          ${{c.has_conversion_risk?'<span class="b b-r" style="margin-left:8px">Conversion Risk</span>':''}}
        </div>
        <div><span class="b ${{c.severity==='critical'?'b-r':c.severity==='high'?'b-y':'b-g'}}">${{c.count}} URLs &middot; ${{c.severity}}</span> <span class="expand-arrow">&#9654;</span></div>
      </div>
      <div style="font-size:12px;color:var(--muted);margin-top:6px">${{c.analysis}}</div>
      ${{c.keywords?'<div style="margin-top:4px;font-size:11px;color:var(--muted)">Shared keywords: '+c.keywords.join(', ')+'</div>':''}}
      <div class="expand-body">
        <table style="font-size:12px">
          <thead><tr><th style="width:50%">URL</th><th style="width:12%">Page Type</th><th style="width:38%">Recommended Action</th></tr></thead>
          <tbody>
            ${{c.urls.map(u=>{{
              const tc=typeColor[u.type]||'#6b7280';
              const rowBg=u.role==='money'?'background:rgba(239,68,68,0.06);':'';
              return `<tr style="${{rowBg}}">
                <td><a href="${{u.url}}" target="_blank">${{u.slug}}</a></td>
                <td><span class="b" style="background:${{tc+'22'}};color:${{tc}}">${{u.type}}</span></td>
                <td style="color:${{u.role==='money'?'var(--red)':u.role==='support'?'var(--green)':'var(--muted)'}};font-weight:${{u.role==='money'?'600':'400'}}">${{u.action}}</td>
              </tr>`;
            }}).join('')}}
          </tbody>
        </table>
      </div>
    </div>`;
  }}).join('');
}}
renderCannib();
document.getElementById('cannib-search').addEventListener('input',e=>renderCannib(e.target.value));

// === DUPLICATES TAB ===
if(ENH.similarity){{
  const convRisks=ENH.similarity.filter(s=>s.conversion_risk).length;
  const exact=ENH.similarity.filter(s=>s.similarity>=0.92).length;
  const high=ENH.similarity.filter(s=>s.similarity>=0.80&&s.similarity<0.92).length;
  document.getElementById('dup-conv').textContent=convRisks;
  document.getElementById('dup-exact').textContent=exact;
  document.getElementById('dup-high').textContent=high;
  document.getElementById('dup-total').textContent=ENH.similarity.length;
  const typeColor={{'service':'#ef4444','industry':'#f97316','local-landing':'#eab308','blog':'#6366f1','tool-review':'#8b5cf6','webinar':'#3b82f6','case-study':'#22c55e','homepage':'#ef4444','listing':'#9ca3af'}};
  document.querySelector('#sim-table tbody').innerHTML=ENH.similarity.map(s=>{{
    const rowBg=s.conversion_risk?'background:rgba(239,68,68,0.05);':'';
    const ta=s.type_a||'blog', tb=s.type_b||'blog';
    return `<tr style="${{rowBg}}">
      <td style="font-size:12px">${{s.url_a}}</td>
      <td><span class="b" style="background:${{(typeColor[ta]||'#6b7280')+'22'}};color:${{typeColor[ta]||'#6b7280'}}">${{ta}}</span></td>
      <td style="font-size:12px">${{s.url_b}}</td>
      <td><span class="b" style="background:${{(typeColor[tb]||'#6b7280')+'22'}};color:${{typeColor[tb]||'#6b7280'}}">${{tb}}</span></td>
      <td style="color:${{s.conversion_risk?'#ef4444':s.similarity>=0.92?'#ef4444':'#eab308'}};font-weight:700">${{(s.similarity*100).toFixed(0)}}%</td>
      <td style="font-size:11px;color:${{s.conversion_risk?'var(--red)':'var(--muted)'}};font-weight:${{s.conversion_risk?'600':'400'}}">${{s.action}}</td></tr>`;
  }}).join('');
}}

// === THIN CONTENT TAB ===
function renderThin(data,id){{
  document.getElementById(id).innerHTML=data.map(d=>`
    <div style="display:grid;grid-template-columns:1fr 50px 2fr;gap:12px;padding:8px 0;border-bottom:1px solid var(--border);align-items:center">
      <a href="${{d.url}}" target="_blank" style="font-size:12px;word-break:break-all">${{d.url.replace('https://azariangrowthagency.com/','')}}</a>
      <span style="font-size:12px;color:var(--red);font-weight:600;text-align:center">${{d.word_count}}w</span>
      <span style="font-size:12px;color:var(--muted)">${{d.recommendation}}</span>
    </div>`).join('');
}}
renderThin(THIN_TOOLS,'thin-tools-body');
renderThin(THIN_LOCAL,'thin-local-body');
renderThin(THIN_OTHER,'thin-other-body');

// === INTENT TAB ===
if(ENH.intent){{
  const iL=Object.keys(ENH.intent),iV=Object.values(ENH.intent);
  const iC={{'informational':'#6366f1','commercial':'#3b82f6','transactional':'#22c55e','navigational':'#9ca3af'}};
  Plotly.newPlot('intent-chart',[{{type:'pie',labels:iL,values:iV,hole:0.5,textinfo:'label+percent',marker:{{colors:iL.map(l=>iC[l]||'#6b7280')}},textfont:{{size:13}}}}],{{...PL,height:350,showlegend:false,margin:{{t:10,b:10,l:10,r:10}}}},{{responsive:true}});
  const tot=iV.reduce((a,b)=>a+b,0);
  document.getElementById('intent-summary').innerHTML=iL.map(l=>`<div><span style="color:${{iC[l]}};font-weight:700;font-size:28px">${{ENH.intent[l]}}</span> <span style="color:var(--muted)">${{l}} (${{(ENH.intent[l]/tot*100).toFixed(0)}}%)</span></div>`).join('');
}}

// === FRESHNESS TAB ===
if(ENH.freshness){{
  const fO=['Fresh (< 1 month)','Recent (1-3 months)','Aging (3-6 months)','Stale (6-12 months)','Decaying (12+ months)'];
  const fL=fO.filter(k=>ENH.freshness[k]),fV=fL.map(k=>ENH.freshness[k]||0);
  const fC={{'Fresh (< 1 month)':'#22c55e','Recent (1-3 months)':'#4ade80','Aging (3-6 months)':'#eab308','Stale (6-12 months)':'#f97316','Decaying (12+ months)':'#ef4444'}};
  Plotly.newPlot('freshness-chart',[{{type:'bar',y:fL.slice().reverse(),x:fV.slice().reverse(),orientation:'h',
    marker:{{color:fL.slice().reverse().map(l=>fC[l])}},text:fV.slice().reverse(),textposition:'outside',textfont:{{color:'#9ca3af',size:12}},
  }}],{{...PL,height:250,margin:{{t:10,b:20,l:200,r:60}},xaxis:{{gridcolor:'#2a2d3a'}},yaxis:{{tickfont:{{size:13,color:'#e4e4e7'}}}}}},{{responsive:true}});
}}

// === BRAND VOICE TAB ===
if(ENH.brand){{
  document.getElementById('brand-avg').textContent=ENH.brand.avg_score;
  const bL=Object.keys(ENH.brand.distribution),bV=Object.values(ENH.brand.distribution);
  const bC={{'On-brand':'#22c55e','Partially aligned':'#eab308','Needs work':'#f97316','Off-brand':'#ef4444'}};
  Plotly.newPlot('brand-chart',[{{type:'pie',labels:bL,values:bV,hole:0.5,textinfo:'label+percent',marker:{{colors:bL.map(l=>bC[l]||'#6b7280')}},textfont:{{size:13}}}}],{{...PL,height:350,showlegend:false,margin:{{t:10,b:10,l:10,r:10}}}},{{responsive:true}});
  document.querySelector('#brand-table tbody').innerHTML=ENH.brand.bottom.map(b=>`<tr>
    <td style="font-size:12px">${{b.url.replace('https://azariangrowthagency.com/','/')}}</td>
    <td style="font-weight:700;color:${{b.brand_score<25?'#ef4444':b.brand_score<50?'#f97316':'#eab308'}}">${{b.brand_score}}</td>
    <td><span class="b ${{b.rating==='Off-brand'?'b-r':b.rating==='Needs work'?'b-y':'b-b'}}">${{b.rating}}</span></td>
    <td style="font-size:11px;color:var(--muted)">${{b.tone_matches||'none'}}</td>
    <td style="font-size:11px;color:var(--muted)">${{b.violations||'none'}}</td></tr>`).join('');
}}

// === COMPETITORS TAB ===
if(ENH.competitor){{
  document.getElementById('comp-adv').textContent=ENH.comp_stats.advantages;
  document.getElementById('comp-shared').textContent=ENH.comp_stats.shared;
  document.getElementById('comp-gaps').textContent=ENH.comp_stats.gaps;
  const cG={{}};ENH.competitor.forEach(c=>{{cG[c.status]=(cG[c.status]||0)+1;}});
  Plotly.newPlot('comp-chart',[{{type:'bar',y:Object.keys(cG),x:Object.values(cG),orientation:'h',
    marker:{{color:Object.keys(cG).map(k=>k.includes('GAP')?'#ef4444':k.includes('advantage')?'#22c55e':'#6366f1')}},
    text:Object.values(cG),textposition:'outside',textfont:{{color:'#9ca3af',size:11}},
  }}],{{...PL,height:130,margin:{{t:5,b:20,l:180,r:50}},yaxis:{{tickfont:{{size:12,color:'#e4e4e7'}}}},xaxis:{{gridcolor:'#2a2d3a'}}}},{{responsive:true}});
  function renderComp(f=''){{
    const fl=f.toLowerCase(),rows=ENH.competitor.filter(c=>!fl||c.topic.toLowerCase().includes(fl));
    document.querySelector('#comp-table tbody').innerHTML=rows.map(c=>`<tr>
      <td>${{c.topic}}</td><td>${{c.azarian?'Y':''}}</td><td>${{c.nogood?'Y':''}}</td><td>${{c.singlegrain?'Y':''}}</td>
      <td><span class="b ${{c.status.includes('GAP')?'b-r':c.status.includes('advantage')?'b-g':'b-b'}}">${{c.status}}</span></td></tr>`).join('');
  }}
  renderComp();
  document.getElementById('comp-search').addEventListener('input',e=>renderComp(e.target.value.toLowerCase()));
}}

// === MERGES TAB ===
if(ENH.merges){{
  document.querySelector('#merge-table tbody').innerHTML=ENH.merges.map(m=>`<tr>
    <td>${{m.cluster_a_name}}</td><td>${{m.cluster_b_name}}</td>
    <td style="color:${{m.similarity>=0.85?'#ef4444':'#eab308'}};font-weight:700">${{(m.similarity*100).toFixed(0)}}%</td>
    <td><span class="b ${{m.recommendation==='MERGE'?'b-r':'b-y'}}">${{m.recommendation}}</span></td></tr>`).join('');
}}

// === URL EXPLORER TAB ===
function renderUrlTable(f=''){{
  const fl=f.toLowerCase(),rows=URL_TABLE.filter(u=>!fl||u.url.toLowerCase().includes(fl)||(u.name&&u.name.toLowerCase().includes(fl)));
  const ltd=rows.slice(0,200);
  document.querySelector('#url-table tbody').innerHTML=ltd.map(u=>`<tr>
    <td style="max-width:400px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"><a href="${{u.url}}" target="_blank">${{u.url.replace('https://azariangrowthagency.com/','')}}</a></td>
    <td>${{u.cluster}}</td><td>${{u.name||'Unclustered'}}</td><td style="color:var(--muted)">${{u.secondary||''}}</td></tr>`).join('');
  if(rows.length>200)document.querySelector('#url-table tbody').innerHTML+=`<tr><td colspan="4" style="color:var(--muted);text-align:center">Showing 200 of ${{rows.length}}</td></tr>`;
}}
renderUrlTable();
document.getElementById('url-search').addEventListener('input',e=>renderUrlTable(e.target.value));
</script>
</body>
</html>"""
