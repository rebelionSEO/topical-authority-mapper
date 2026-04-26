#!/usr/bin/env python3
"""Build a static GitHub Pages site from the runs/ directory.

For each site found in runs/<site>/history.json, copies the latest snapshot's
dashboard.html, exec_summary.html, and dashboard_artifact.tsx into public/<site>/,
then generates a top-level public/index.html with one card per site (composite health
score, totals, last run date, links to both views).

Usage:
    python scripts/build_pages_index.py <runs_dir> <public_dir>

Example:
    python scripts/build_pages_index.py runs/ public/
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from html import escape


HEALTH_COLORS = {
    "green": "#22c55e",
    "yellow": "#eab308",
    "red": "#ef4444",
    "unknown": "#9ca3af",
}


def _read_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _gather_sites(runs_root: str) -> list[dict]:
    sites = []
    if not os.path.isdir(runs_root):
        return sites
    for slug in sorted(os.listdir(runs_root)):
        site_dir = os.path.join(runs_root, slug)
        if not os.path.isdir(site_dir):
            continue
        history = _read_json(os.path.join(site_dir, "history.json"))
        if not history or not isinstance(history, list):
            continue
        latest = history[-1]
        run_id = latest.get("run_id")
        if not run_id:
            continue

        snap_output = os.path.join(site_dir, run_id, "output")
        if not os.path.isdir(snap_output):
            continue

        health = _read_json(os.path.join(snap_output, "site_health.json"))
        sites.append({
            "slug": slug,
            "name": latest.get("site_name", slug),
            "domain": latest.get("site_domain", ""),
            "industry": latest.get("industry"),
            "run_id": run_id,
            "timestamp_utc": latest.get("timestamp_utc", ""),
            "totals": latest.get("totals", {}),
            "qa_summary": latest.get("qa_summary", {}),
            "competitors": latest.get("competitors", []),
            "health": health,
            "snap_output": snap_output,
            "history_count": len(history),
        })
    return sites


def _copy_site_assets(site: dict, public_root: str) -> dict:
    """Copy this site's renderable artifacts to public/<slug>/. Returns the relative paths copied."""
    dst_dir = os.path.join(public_root, site["slug"])
    os.makedirs(dst_dir, exist_ok=True)
    copied = {}
    for fname in ("dashboard.html", "exec_summary.html", "dashboard_artifact.tsx", "site_health.json", "qa_report.json"):
        src = os.path.join(site["snap_output"], fname)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(dst_dir, fname))
            copied[fname] = f"{site['slug']}/{fname}"
    return copied


def _site_card(site: dict, copied: dict) -> str:
    composite = site["health"].get("composite")
    label = site["health"].get("composite_label", "unknown")
    color = HEALTH_COLORS.get(label, HEALTH_COLORS["unknown"])
    score_html = f'<div class="score" style="color:{color}">{composite}</div>' if composite is not None else '<div class="score muted">—</div>'

    totals = site["totals"]
    n_urls = totals.get("urls", 0)
    n_clusters = totals.get("clusters", 0)
    n_cannib = totals.get("cannibalization", totals.get("cannib", 0))
    n_ideas = totals.get("content_ideas", 0)
    n_runs = site["history_count"]

    # Pretty-format the timestamp
    ts = site["timestamp_utc"]
    pretty_ts = ts
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        pretty_ts = dt.strftime("%b %d, %Y %H:%M UTC")
    except ValueError:
        pass

    dashboard_link = copied.get("dashboard.html")
    exec_link = copied.get("exec_summary.html")
    artifact_link = copied.get("dashboard_artifact.tsx")

    industry_html = f'<span class="industry">· {escape(site["industry"])}</span>' if site.get("industry") else ""
    competitor_html = ""
    if site.get("competitors"):
        comp_str = ", ".join(escape(c) for c in site["competitors"][:3])
        more = f" + {len(site['competitors']) - 3}" if len(site["competitors"]) > 3 else ""
        competitor_html = f'<div class="competitors">vs {comp_str}{more}</div>'

    qa = site.get("qa_summary", {}) or {}
    qa_html = ""
    if qa.get("critical") or qa.get("warn"):
        qa_html = f'<div class="qa">QA: <span class="qa-c">{qa.get("critical",0)}</span> critical · <span class="qa-w">{qa.get("warn",0)}</span> warn</div>'

    primary_link = dashboard_link or exec_link or "#"
    secondary_links = []
    if exec_link and exec_link != primary_link:
        secondary_links.append(f'<a href="{escape(exec_link)}">1-page summary</a>')
    if artifact_link:
        secondary_links.append(f'<a href="{escape(artifact_link)}" download>Claude artifact (.tsx)</a>')
    secondary_html = " · ".join(secondary_links)

    return f"""    <a href="{escape(primary_link)}" class="card">
      <div class="card-head">
        <div>
          <h2>{escape(site['name'])}</h2>
          <div class="domain">{escape(site['domain'])} {industry_html}</div>
        </div>
        {score_html}
      </div>
      <div class="totals">
        <span><b>{n_urls}</b> URLs</span>
        <span><b>{n_clusters}</b> clusters</span>
        <span><b>{n_cannib}</b> cannib.</span>
        <span><b>{n_ideas}</b> briefs</span>
      </div>
      {competitor_html}
      {qa_html}
      <div class="meta">
        <span>last run: {escape(pretty_ts)} · {n_runs} runs</span>
        <span>{secondary_html}</span>
      </div>
    </a>"""


def _render_index(sites: list[dict], cards_html: str) -> str:
    now = datetime.utcnow().strftime("%b %d, %Y %H:%M UTC")
    n = len(sites)
    empty_html = ""
    if not sites:
        empty_html = """
    <div class="empty">
      <h2>No sites yet</h2>
      <p>Add a YAML config under <code>examples/sites/</code> in the repo, then re-run the workflow.</p>
      <p>See <code>examples/sites/_README.md</code> for the schema.</p>
    </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Topical Authority Audits</title>
<style>
  *{{margin:0;padding:0;box-sizing:border-box;}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f1117;color:#e4e4e7;line-height:1.55;min-height:100vh;}}
  .header{{background:#1a1d27;border-bottom:1px solid #2a2d3a;padding:24px 32px;display:flex;justify-content:space-between;align-items:flex-end;}}
  .header h1{{font-size:22px;font-weight:800;}}
  .header .meta{{font-size:12px;color:#9ca3af;}}
  .container{{max-width:1100px;margin:0 auto;padding:24px 32px;}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px;margin-top:18px;}}
  .card{{background:#1a1d27;border:1px solid #2a2d3a;border-radius:12px;padding:18px;text-decoration:none;color:inherit;display:block;transition:all 0.15s;}}
  .card:hover{{border-color:#6366f1;transform:translateY(-2px);box-shadow:0 6px 20px rgba(0,0,0,0.4);}}
  .card-head{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px;gap:12px;}}
  .card-head h2{{font-size:16px;font-weight:700;color:#e4e4e7;}}
  .domain{{font-size:11px;color:#9ca3af;margin-top:2px;}}
  .industry{{color:#6366f1;}}
  .score{{font-size:38px;font-weight:800;line-height:1;}}
  .score.muted{{color:#6b7280;}}
  .totals{{display:flex;gap:14px;font-size:12px;color:#9ca3af;margin-bottom:6px;flex-wrap:wrap;}}
  .totals b{{color:#e4e4e7;font-weight:700;}}
  .competitors{{font-size:11px;color:#6b7280;margin-bottom:6px;}}
  .qa{{font-size:10.5px;color:#9ca3af;margin-bottom:6px;}}
  .qa-c{{color:#ef4444;font-weight:700;}}
  .qa-w{{color:#eab308;font-weight:700;}}
  .meta{{display:flex;justify-content:space-between;font-size:11px;color:#6b7280;border-top:1px solid #2a2d3a;padding-top:10px;margin-top:6px;}}
  .meta a{{color:#6366f1;text-decoration:none;margin-left:8px;}}
  .meta a:hover{{text-decoration:underline;}}
  .empty{{text-align:center;padding:60px 24px;color:#9ca3af;}}
  .empty h2{{color:#e4e4e7;margin-bottom:12px;}}
  .empty code{{background:#1a1d27;padding:2px 6px;border-radius:4px;font-size:12px;}}
  .footer{{text-align:center;padding:24px;font-size:11px;color:#6b7280;}}
</style>
</head>
<body>
  <div class="header">
    <div>
      <h1>Topical Authority Audits</h1>
      <div class="meta">{n} site{'s' if n != 1 else ''} tracked</div>
    </div>
    <div class="meta">Index built: {now}</div>
  </div>
  <div class="container">
    {empty_html}
    <div class="grid">
{cards_html}
    </div>
  </div>
  <div class="footer">Generated by topical-authority-mapper · refreshed weekly via GitHub Actions</div>
</body>
</html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("runs_root", help="Path to the runs/ directory")
    parser.add_argument("public_root", help="Path to the public/ output directory")
    args = parser.parse_args()

    os.makedirs(args.public_root, exist_ok=True)

    sites = _gather_sites(args.runs_root)
    cards_html_parts = []
    for site in sites:
        copied = _copy_site_assets(site, args.public_root)
        cards_html_parts.append(_site_card(site, copied))
    cards_html = "\n".join(cards_html_parts)

    index_html = _render_index(sites, cards_html)
    index_path = os.path.join(args.public_root, "index.html")
    with open(index_path, "w") as f:
        f.write(index_html)

    print(f"Built {index_path} with {len(sites)} site card(s)")
    for site in sites:
        print(f"  - {site['slug']}: {site['name']} ({site['domain']}), health {site['health'].get('composite', '—')}/100")
    return 0


if __name__ == "__main__":
    sys.exit(main())
