"""One-page executive summary HTML.

Light-mode, print-friendly, single self-contained file. Designed to be shared with
non-technical stakeholders — no charts library, no JS, prints clean.
"""

import json
import logging
import os
from datetime import datetime
from html import escape

import pandas as pd

from src.config import SiteConfig, load_site_config, output_dir
from src.site_health import HealthSnapshot, compute_health

logger = logging.getLogger(__name__)


_LABEL_COLOR = {
    "green": "#16a34a",
    "yellow": "#d97706",
    "red": "#dc2626",
    "unknown": "#9ca3af",
}


def _read_csv(path: str):
    if not os.path.exists(path):
        return None
    try:
        return pd.read_csv(path)
    except Exception:
        return None


def _delta_html(value):
    if value is None or value == 0:
        return '<span style="color:#9ca3af">—</span>'
    arrow = "▲" if value > 0 else "▼"
    color = "#16a34a" if value > 0 else "#dc2626"
    return f'<span style="color:{color};font-weight:600">{arrow} {abs(value)}</span>'


def _sparkline_svg(values: list, width: int = 120, height: int = 32) -> str:
    """Tiny inline SVG sparkline (no JS, prints fine)."""
    if not values:
        return ""
    if len(values) == 1:
        values = [values[0], values[0]]
    vmin, vmax = min(values), max(values)
    rng = max(vmax - vmin, 1)
    pts = []
    for i, v in enumerate(values):
        x = (i / max(len(values) - 1, 1)) * (width - 4) + 2
        y = height - 2 - ((v - vmin) / rng) * (height - 4)
        pts.append(f"{x:.1f},{y:.1f}")
    points = " ".join(pts)
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'style="vertical-align:middle">'
        f'<polyline fill="none" stroke="#4A7BF7" stroke-width="2" points="{points}"/>'
        f'<circle cx="{pts[-1].split(",")[0]}" cy="{pts[-1].split(",")[1]}" r="2.5" fill="#4A7BF7"/>'
        f'</svg>'
    )


def build_exec_summary_html(site_config: SiteConfig, health: HealthSnapshot) -> str:
    out = output_dir()
    site_name = escape(site_config.name)
    site_domain = escape(site_config.domain or "")
    today = datetime.now().strftime("%B %d, %Y")

    # Pull headline numbers
    clusters = _read_csv(os.path.join(out, "clusters.csv"))
    cannib = _read_csv(os.path.join(out, "cannibalization.csv"))
    skipped = _read_csv(os.path.join(out, "skipped_urls.csv"))
    url_map = _read_csv(os.path.join(out, "url_mapping.csv"))
    ideas = _read_csv(os.path.join(out, "content_ideas.csv"))

    n_urls = len(url_map) if url_map is not None else 0
    n_clusters = len(clusters) if clusters is not None else 0
    n_cannib = len(cannib) if cannib is not None else 0
    n_thin = (skipped[skipped["reason"].str.contains("thin", na=False)].shape[0]
              if skipped is not None and not skipped.empty else 0)
    n_ideas = len(ideas) if ideas is not None else 0
    n_p1 = (ideas[ideas["priority"] == "P1"].shape[0] if ideas is not None and not ideas.empty else 0)

    composite_color = _LABEL_COLOR[health.composite_label]
    composite_delta = _delta_html(health.deltas.get("composite") if health.deltas else None)
    spark = _sparkline_svg(health.sparkline) if health.sparkline else ""

    subscore_rows = ""
    sub_labels = {
        "coverage": "Topic Coverage",
        "cannibalization": "Cannibalization",
        "freshness": "Content Freshness",
        "brand": "Brand Voice",
        "competitive": "Competitive Position",
    }
    for key, label in sub_labels.items():
        sub = health.subscores.get(key)
        if not sub:
            continue
        color = _LABEL_COLOR.get(sub.label, "#9ca3af")
        delta = _delta_html(health.deltas.get(key)) if health.deltas else "—"
        bar_pct = max(0, min(sub.score, 100))
        subscore_rows += f"""
        <tr>
          <td style="padding:8px 12px;font-weight:500">{label}</td>
          <td style="padding:8px 12px">
            <div style="display:flex;align-items:center;gap:10px">
              <div style="background:#e5e7eb;border-radius:4px;height:8px;width:120px;overflow:hidden">
                <div style="background:{color};height:100%;width:{bar_pct}%"></div>
              </div>
              <strong style="color:{color};min-width:32px">{sub.score}</strong>
            </div>
          </td>
          <td style="padding:8px 12px;color:#6b7280;font-size:11px">{escape(sub.detail)}</td>
          <td style="padding:8px 12px;text-align:right">{delta}</td>
        </tr>"""

    # Top P1 ideas — up to 5
    top_ideas_html = ""
    if ideas is not None and not ideas.empty:
        top = ideas.head(5)
        for _, row in top.iterrows():
            top_ideas_html += f"""
            <li style="margin-bottom:10px">
              <strong>[{escape(str(row['priority']))}]</strong> {escape(str(row['title']))}
              <div style="font-size:11px;color:#6b7280;margin-top:2px">
                {escape(str(row['content_type']))} · ~{int(row['est_word_count'])}w · validated by {escape(str(row['covered_by']))}
              </div>
            </li>"""
    else:
        top_ideas_html = '<li style="color:#9ca3af;font-style:italic">No content ideas yet — re-run with --competitor.</li>'

    # Top cannibalized clusters
    top_cannib_html = ""
    if cannib is not None and not cannib.empty:
        for _, row in cannib.head(5).iterrows():
            sev = "Critical" if row["url_count"] >= 10 else "High" if row["url_count"] >= 6 else "Moderate"
            sev_color = "#dc2626" if sev == "Critical" else "#d97706" if sev == "High" else "#4A7BF7"
            top_cannib_html += f"""
            <li style="margin-bottom:6px">
              <strong>{escape(str(row['cluster_name']))}</strong>
              <span style="color:{sev_color};font-size:11px;margin-left:6px">{int(row['url_count'])} URLs · {sev}</span>
            </li>"""
    else:
        top_cannib_html = '<li style="color:#9ca3af;font-style:italic">No cannibalization detected — clean topical structure.</li>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{site_name} — Topical Authority One-Pager</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif;
    color: #1f2937; background: #fff; line-height: 1.5; padding: 32px;
    max-width: 880px; margin: 0 auto;
  }}
  .header {{ display:flex; justify-content:space-between; align-items:flex-end; border-bottom: 3px solid #4A7BF7; padding-bottom: 12px; margin-bottom: 24px; }}
  .header h1 {{ font-size: 22px; font-weight: 800; color: #111827; }}
  .header .meta {{ color: #6b7280; font-size: 12px; line-height: 1.6; text-align: right; }}

  .hero {{ display:grid; grid-template-columns: 200px 1fr; gap: 24px; align-items: center; margin-bottom: 28px; padding: 20px; border: 1px solid #e5e7eb; border-radius: 12px; background: #fafbff; }}
  .hero .score {{ text-align: center; }}
  .hero .score .num {{ font-size: 64px; font-weight: 800; color: {composite_color}; line-height: 1; }}
  .hero .score .label {{ font-size: 11px; color: #6b7280; text-transform: uppercase; letter-spacing: 1px; margin-top: 4px; font-weight: 600; }}
  .hero .meta-row {{ display:flex; gap: 24px; align-items: center; flex-wrap: wrap; margin-top: 8px; }}
  .hero .meta-row .item {{ font-size: 12px; color: #6b7280; }}
  .hero .meta-row .item strong {{ color: #1f2937; font-size: 15px; display: block; margin-bottom: 2px; }}
  .delta {{ font-size: 13px; }}
  .spark-wrap {{ display:flex; align-items:center; gap: 8px; }}

  h2 {{ font-size: 14px; font-weight: 700; color: #4A7BF7; text-transform: uppercase; letter-spacing: 0.6px; margin: 24px 0 10px; }}
  table.subscores {{ width: 100%; border-collapse: collapse; font-size: 13px; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden; }}
  table.subscores th {{ background: #f3f4f6; padding: 8px 12px; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; color: #6b7280; font-weight: 600; text-align: left; border-bottom: 1px solid #e5e7eb; }}
  table.subscores td {{ border-bottom: 1px solid #f3f4f6; }}
  table.subscores tr:last-child td {{ border-bottom: none; }}

  .row-2 {{ display:grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-top: 8px; }}
  .panel {{ border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; }}
  .panel h3 {{ font-size: 12px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 10px; font-weight: 600; }}
  .panel ul {{ list-style: none; padding: 0; font-size: 12px; }}

  .stats-strip {{ display:grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin: 12px 0 24px; }}
  .stats-strip .stat {{ border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; text-align: center; }}
  .stats-strip .stat .v {{ font-size: 22px; font-weight: 700; color: #1f2937; }}
  .stats-strip .stat .l {{ font-size: 10px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 4px; }}

  .footer {{ margin-top: 32px; padding-top: 12px; border-top: 1px solid #e5e7eb; color: #9ca3af; font-size: 10px; text-align: center; }}

  @media print {{
    body {{ padding: 16px; }}
    .hero {{ break-inside: avoid; }}
    .panel {{ break-inside: avoid; }}
  }}
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>{site_name} — Topical Authority Snapshot</h1>
    <div style="color:#6b7280;font-size:12px;margin-top:2px">{site_domain}</div>
  </div>
  <div class="meta">
    Generated {today}<br>
    {n_urls} pages analyzed
  </div>
</div>

<div class="hero">
  <div class="score">
    <div class="num">{health.composite}</div>
    <div class="label">Site Health / 100</div>
  </div>
  <div>
    <div style="font-size:14px;color:#1f2937;font-weight:600;margin-bottom:6px">
      Overall: <span style="color:{composite_color}">{health.composite_label.title()}</span>
      <span class="delta" style="margin-left:8px">{composite_delta}</span>
    </div>
    <div class="meta-row">
      <div class="spark-wrap">
        {spark}
        <span style="font-size:10px;color:#9ca3af">last {len(health.sparkline)} runs</span>
      </div>
    </div>
    <div style="margin-top:10px;font-size:12px;color:#6b7280;line-height:1.6">
      Composite of {len([s for s in health.subscores.values() if s.label != "unknown"])} subscores below.
      Higher is better. Green ≥ 75 · Yellow 50–74 · Red &lt; 50.
    </div>
  </div>
</div>

<div class="stats-strip">
  <div class="stat"><div class="v">{n_urls}</div><div class="l">URLs</div></div>
  <div class="stat"><div class="v">{n_clusters}</div><div class="l">Clusters</div></div>
  <div class="stat"><div class="v" style="color:#dc2626">{n_cannib}</div><div class="l">Cannibalized</div></div>
  <div class="stat"><div class="v" style="color:#d97706">{n_thin}</div><div class="l">Thin Pages</div></div>
  <div class="stat"><div class="v" style="color:#4A7BF7">{n_ideas}</div><div class="l">Content Ideas</div></div>
</div>

<h2>Subscores</h2>
<table class="subscores">
  <thead>
    <tr>
      <th style="width:25%">Area</th>
      <th style="width:30%">Score</th>
      <th>Detail</th>
      <th style="width:15%;text-align:right">vs last run</th>
    </tr>
  </thead>
  <tbody>{subscore_rows}</tbody>
</table>

<div class="row-2">
  <div class="panel">
    <h3>Top Cannibalized Clusters</h3>
    <ul>{top_cannib_html}</ul>
  </div>
  <div class="panel">
    <h3>Top Content Briefs ({n_p1} P1 total)</h3>
    <ul>{top_ideas_html}</ul>
  </div>
</div>

<div class="footer">
  Generated by Topical Authority Mapper · See dashboard.html for the full interactive view
</div>

</body>
</html>"""


def generate_exec_summary(site_config=None, health=None) -> str:
    """Build and write the exec summary HTML. Returns the file path."""
    if site_config is None:
        site_config = load_site_config() or SiteConfig(name="Site", domain="")
    if health is None:
        health = compute_health(site_config=site_config)

    html = build_exec_summary_html(site_config, health)
    path = os.path.join(output_dir(), "exec_summary.html")
    with open(path, "w") as f:
        f.write(html)
    logger.info("Exec summary written: %s", path)
    return path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = generate_exec_summary()
    print(f"Exec summary: {p}")
