"""Generate a Claude-Artifact-ready React + Recharts + Tailwind dashboard.

Output: output/dashboard_artifact.tsx — a single self-contained React component with
all data inlined as a JS const. Drop into Claude as an artifact and it renders as a
fully interactive dashboard.

Stack used (all bundled in Claude's artifact runtime):
  - React (function component + hooks)
  - Recharts (bar/pie/scatter)
  - Tailwind (utility classes)

Focused on the highest-signal tabs: Summary (health hero), Content Ideas,
Cannibalization, Competitors, Topic Clusters. Other enhancement tabs from the full
HTML dashboard are intentionally omitted to keep the artifact lean.
"""

import json
import logging
import os
from typing import Optional

import pandas as pd

from src.config import SiteConfig, load_site_config, output_dir

logger = logging.getLogger(__name__)


def _read_csv(path: str) -> Optional[pd.DataFrame]:
    if not os.path.exists(path):
        return None
    try:
        return pd.read_csv(path)
    except Exception:
        return None


def _read_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def _gather_data(site_config: SiteConfig) -> dict:
    out = output_dir()
    clusters = _read_csv(os.path.join(out, "clusters.csv"))
    url_map = _read_csv(os.path.join(out, "url_mapping.csv"))
    cannib = _read_csv(os.path.join(out, "cannibalization.csv"))
    ideas = _read_csv(os.path.join(out, "content_ideas.csv"))
    health = _read_json(os.path.join(out, "site_health.json"))

    # Cluster table: top 30 by URL count, joined with cannib status
    cluster_rows = []
    if clusters is not None and not clusters.empty:
        sizes = (url_map[url_map["main_cluster"] != -1]
                 .groupby("main_cluster").size().reset_index(name="urls")
                 if url_map is not None else pd.DataFrame())
        merged = clusters.merge(sizes, left_on="cluster_id", right_on="main_cluster", how="left")
        merged["urls"] = merged["urls"].fillna(0).astype(int)
        merged = merged.sort_values("urls", ascending=False).head(30)
        cannib_ids = set(cannib["cluster_id"].tolist()) if cannib is not None and not cannib.empty else set()
        for _, row in merged.iterrows():
            cluster_rows.append({
                "id": int(row["cluster_id"]),
                "name": str(row["cluster_name"]),
                "urls": int(row["urls"]),
                "keywords": str(row.get("keywords", ""))[:100],
                "cannibalized": int(row["cluster_id"]) in cannib_ids,
            })

    # Cannibalization detail (top 15)
    cannib_rows = []
    if cannib is not None and not cannib.empty:
        cs = cannib.sort_values("url_count", ascending=False).head(15)
        for _, row in cs.iterrows():
            urls = str(row.get("urls", "")).split(" | ")[:5]  # cap URLs per cluster for size
            cannib_rows.append({
                "id": int(row["cluster_id"]),
                "name": str(row["cluster_name"]),
                "count": int(row["url_count"]),
                "severity": "critical" if row["url_count"] >= 10 else "high" if row["url_count"] >= 6 else "moderate",
                "urls": [site_config.strip_url(u) for u in urls],
                "more": max(0, int(row["url_count"]) - 5),
            })

    # Content ideas (full list, capped at 30 for artifact size)
    idea_rows = []
    if ideas is not None and not ideas.empty:
        for _, row in ideas.head(30).iterrows():
            idea_rows.append({
                "priority": str(row["priority"]),
                "title": str(row["title"]),
                "topic": str(row["gap_topic"]),
                "type": str(row["content_type"]),
                "intent": str(row["intent"]),
                "audience": str(row["target_audience"]),
                "words": int(row["est_word_count"]),
                "covered_by": str(row["covered_by"]),
                "keywords": [k.strip() for k in str(row["suggested_keywords"]).split("|") if k.strip()],
                "questions": [q.strip() for q in str(row["key_questions"]).split("|") if q.strip()],
            })

    # Competitors: pull all competitor_gap_*.csv into a unified matrix
    competitor_names = []
    competitor_rows = []
    if os.path.isdir(out):
        # Build topic -> {target, competitors{name->bool}, status}
        per_topic: dict = {}
        for fname in sorted(os.listdir(out)):
            if not (fname.startswith("competitor_gap_") and fname.endswith(".csv")):
                continue
            stem = fname[len("competitor_gap_"):-len(".csv")]
            display = stem.replace("_", " ").title()
            competitor_names.append(display)
            df = _read_csv(os.path.join(out, fname))
            if df is None or df.empty:
                continue
            for _, row in df.iterrows():
                topic = str(row.get("keyword", "")).strip()
                status = str(row.get("status", "")).lower()
                if not topic:
                    continue
                rec = per_topic.setdefault(topic, {"topic": topic, "target": False, "competitors": {}, "status": ""})
                target_present = "advantage" in status or "shared" in status or "both cover" in status
                comp_present = "gap" in status or "shared" in status or "both cover" in status
                if target_present:
                    rec["target"] = True
                if comp_present:
                    rec["competitors"][display] = True
        for r in per_topic.values():
            covered_by_comp = any(r["competitors"].values())
            if r["target"] and not covered_by_comp:
                r["status"] = "ADVANTAGE"
            elif covered_by_comp and not r["target"]:
                r["status"] = "GAP"
            else:
                r["status"] = "SHARED"
            competitor_rows.append(r)

    # Stats summary
    n_urls = len(url_map) if url_map is not None else 0
    n_clusters = len(clusters) if clusters is not None else 0
    n_cannib = len(cannib) if cannib is not None else 0
    n_ideas = len(ideas) if ideas is not None else 0

    stats = {
        "urls": n_urls,
        "clusters": n_clusters,
        "cannib": n_cannib,
        "ideas": n_ideas,
        "p1_ideas": int((ideas["priority"] == "P1").sum()) if ideas is not None and not ideas.empty else 0,
    }

    return {
        "site": {"name": site_config.name, "domain": site_config.domain, "industry": site_config.industry},
        "stats": stats,
        "health": health,
        "clusters": cluster_rows,
        "cannib": cannib_rows,
        "ideas": idea_rows,
        "competitors": {"names": competitor_names, "rows": competitor_rows},
    }


# ---------------------------------------------------------------------------
# TSX template — placeholder substitution to avoid brace-escaping hell
# ---------------------------------------------------------------------------

_TSX_TEMPLATE = r"""import { useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  ScatterChart,
  Scatter,
  ZAxis,
  ReferenceLine,
} from "recharts";

const DATA = __DATA_PLACEHOLDER__;

const SEVERITY_COLOR = { critical: "#ef4444", high: "#eab308", moderate: "#22c55e" };
const PRIORITY_COLOR = { P1: "bg-red-500/15 text-red-400 border-red-500/30",
                          P2: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
                          P3: "bg-blue-500/15 text-blue-400 border-blue-500/30" };
const INTENT_COLOR = { comparison: "#a78bfa", howto: "#60a5fa", definition: "#34d399",
                        framework: "#fb923c", examples: "#facc15", metrics: "#22d3ee",
                        checklist: "#c4b5fd", guide: "#818cf8" };
const HEALTH_COLOR = { green: "#22c55e", yellow: "#eab308", red: "#ef4444", unknown: "#9ca3af" };

function Sparkline({ values }) {
  if (!values || values.length < 2) return null;
  const w = 120, h = 28;
  const min = Math.min(...values), max = Math.max(...values);
  const rng = Math.max(max - min, 1);
  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1)) * (w - 4) + 2;
    const y = h - 2 - ((v - min) / rng) * (h - 4);
    return [x, y];
  });
  const polyPts = pts.map(([x, y]) => x.toFixed(1) + "," + y.toFixed(1)).join(" ");
  const last = pts[pts.length - 1];
  return (
    <svg width={w} height={h} viewBox={"0 0 " + w + " " + h}>
      <polyline fill="none" stroke="#818cf8" strokeWidth="2" points={polyPts} />
      <circle cx={last[0]} cy={last[1]} r="2.5" fill="#818cf8" />
    </svg>
  );
}

function Delta({ value }) {
  if (value == null) return null;
  if (value === 0) return <span className="text-gray-500 text-xs">— no change</span>;
  const up = value > 0;
  const cls = up ? "text-green-400" : "text-red-400";
  const arrow = up ? "▲" : "▼";
  return <span className={cls + " text-xs font-semibold"}>{arrow} {Math.abs(value)} vs last run</span>;
}

function HealthHero({ health }) {
  if (!health || health.composite == null) {
    return (
      <div className="rounded-xl border border-gray-700 bg-gray-800/50 p-12 text-center text-gray-400">
        <div className="text-3xl mb-2 opacity-40">∅</div>
        <div className="text-gray-200 mb-1">Site health not computed</div>
        <div className="text-xs">Run the pipeline to populate this view.</div>
      </div>
    );
  }
  const lbl = health.composite_label || "unknown";
  const color = HEALTH_COLOR[lbl] || HEALTH_COLOR.unknown;
  const subs = health.subscores || {};
  const deltas = health.deltas || {};
  const subLabels = {
    coverage: "Topic Coverage",
    cannibalization: "Cannibalization",
    freshness: "Freshness",
    brand: "Brand Voice",
    competitive: "Competitive",
  };
  return (
    <div className="rounded-xl border border-gray-700 bg-gradient-to-br from-gray-800 to-gray-900 p-6 mb-5">
      <div className="grid grid-cols-1 md:grid-cols-[240px_1fr] gap-6 items-center">
        <div className="text-center">
          <div className="text-7xl font-extrabold leading-none" style={{ color }}>{health.composite}</div>
          <div className="text-[10px] text-gray-400 uppercase tracking-widest mt-1 font-semibold">Site Health / 100</div>
          <div className="mt-2"><Delta value={deltas.composite} /></div>
          {health.sparkline && health.sparkline.length > 1 && (
            <div className="flex items-center gap-2 justify-center mt-2">
              <Sparkline values={health.sparkline} />
              <span className="text-[10px] text-gray-500">last {health.sparkline.length} runs</span>
            </div>
          )}
        </div>
        <div>
          <div className="text-[10px] text-gray-400 uppercase tracking-wider font-semibold mb-3">Subscores · weighted composite</div>
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
            {Object.entries(subLabels).map(([key, label]) => {
              const s = subs[key];
              if (!s) return null;
              const c = HEALTH_COLOR[s.label] || HEALTH_COLOR.unknown;
              const d = deltas[key];
              return (
                <div key={key} className="rounded-lg border border-gray-700 bg-gray-900/60 p-3">
                  <div className="text-[10px] text-gray-400 uppercase tracking-wide font-semibold">{label}</div>
                  <div className="flex justify-between items-baseline mt-1">
                    <div className="text-2xl font-bold" style={{ color: c }}>{s.score}</div>
                    {d != null && d !== 0 && (
                      <span className={d > 0 ? "text-green-400 text-xs font-semibold" : "text-red-400 text-xs font-semibold"}>
                        {d > 0 ? "▲" : "▼"} {Math.abs(d)}
                      </span>
                    )}
                  </div>
                  <div className="h-1 bg-gray-700 rounded mt-2 overflow-hidden">
                    <div className="h-full transition-all" style={{ width: s.score + "%", background: c }} />
                  </div>
                  <div className="text-[10.5px] text-gray-500 mt-1.5 leading-tight">{s.detail || ""}</div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCards({ stats }) {
  const cards = [
    { v: stats.urls, l: "URLs Analyzed", c: "text-indigo-400" },
    { v: stats.clusters, l: "Topic Clusters", c: "text-indigo-400" },
    { v: stats.cannib, l: "Cannibalization", c: "text-red-400" },
    { v: stats.ideas, l: "Content Briefs", c: "text-blue-400" },
    { v: stats.p1_ideas, l: "P1 Briefs", c: "text-yellow-400" },
  ];
  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-px bg-gray-700 rounded-lg overflow-hidden mb-5">
      {cards.map((c, i) => (
        <div key={i} className="bg-gray-800 p-4 text-center">
          <div className={"text-3xl font-bold " + c.c}>{c.v}</div>
          <div className="text-[10px] text-gray-400 uppercase tracking-wide mt-1">{c.l}</div>
        </div>
      ))}
    </div>
  );
}

function Quadrant({ clusters, cannib }) {
  if (!clusters || !clusters.length) return null;
  const cannibMap = {};
  cannib.forEach((c) => { cannibMap[c.id] = c; });
  const points = clusters.map((c) => {
    const cm = cannibMap[c.id];
    return {
      name: c.name,
      x: c.urls,
      y: cm ? cm.count : 0,
      sev: cm ? cm.severity : "ok",
    };
  });
  const maxX = Math.max(...points.map((p) => p.x), 1);
  const maxY = Math.max(...points.map((p) => p.y), 1);
  const colorBy = (sev) => SEVERITY_COLOR[sev] || "#22c55e";
  return (
    <ResponsiveContainer width="100%" height={280}>
      <ScatterChart margin={{ top: 10, right: 20, bottom: 30, left: 30 }}>
        <CartesianGrid stroke="#2a2d3a" strokeDasharray="3 3" />
        <XAxis type="number" dataKey="x" name="Pages" stroke="#9ca3af" tick={{ fontSize: 11 }}
               label={{ value: "Pages in cluster", position: "insideBottom", offset: -10, fill: "#9ca3af", fontSize: 11 }} />
        <YAxis type="number" dataKey="y" name="Cannibalized" stroke="#9ca3af" tick={{ fontSize: 11 }}
               label={{ value: "Cannibalized pages", angle: -90, position: "insideLeft", fill: "#9ca3af", fontSize: 11 }} />
        <ReferenceLine x={maxX / 2} stroke="#374151" strokeDasharray="3 3" />
        <ReferenceLine y={maxY / 2} stroke="#374151" strokeDasharray="3 3" />
        <Tooltip
          cursor={{ strokeDasharray: "3 3" }}
          contentStyle={{ background: "#1a1d27", border: "1px solid #374151", borderRadius: 6, fontSize: 12 }}
          formatter={(value, name) => [value, name === "x" ? "Pages" : "Cannibalized"]}
          labelFormatter={(_, payload) => payload && payload[0] ? payload[0].payload.name : ""}
        />
        <Scatter data={points}>
          {points.map((p, i) => <Cell key={i} fill={colorBy(p.sev)} />)}
        </Scatter>
      </ScatterChart>
    </ResponsiveContainer>
  );
}

function CannibBar({ cannib }) {
  if (!cannib || !cannib.length) {
    return <div className="text-center text-gray-500 py-8 text-sm">No cannibalization detected.</div>;
  }
  const data = cannib.slice().reverse().map((c) => ({ name: c.name, count: c.count, severity: c.severity }));
  const colorOf = (sev) => SEVERITY_COLOR[sev] || "#22c55e";
  return (
    <ResponsiveContainer width="100%" height={Math.max(280, data.length * 30)}>
      <BarChart data={data} layout="vertical" margin={{ top: 10, right: 50, left: 150, bottom: 10 }}>
        <CartesianGrid stroke="#2a2d3a" strokeDasharray="3 3" horizontal={false} />
        <XAxis type="number" stroke="#9ca3af" tick={{ fontSize: 11 }} />
        <YAxis type="category" dataKey="name" stroke="#e4e4e7" tick={{ fontSize: 11 }} width={140} />
        <Tooltip contentStyle={{ background: "#1a1d27", border: "1px solid #374151", borderRadius: 6, fontSize: 12 }} />
        <Bar dataKey="count" radius={[0, 4, 4, 0]}>
          {data.map((d, i) => <Cell key={i} fill={colorOf(d.severity)} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function CompetitorBar({ competitors }) {
  if (!competitors.rows || !competitors.rows.length) return null;
  const counts = { GAP: 0, SHARED: 0, ADVANTAGE: 0 };
  competitors.rows.forEach((r) => { counts[r.status] = (counts[r.status] || 0) + 1; });
  const data = [
    { name: "GAP", value: counts.GAP, fill: "#ef4444" },
    { name: "SHARED", value: counts.SHARED, fill: "#6366f1" },
    { name: "ADVANTAGE", value: counts.ADVANTAGE, fill: "#22c55e" },
  ];
  return (
    <ResponsiveContainer width="100%" height={130}>
      <BarChart data={data} layout="vertical" margin={{ top: 5, right: 40, left: 80, bottom: 10 }}>
        <CartesianGrid stroke="#2a2d3a" strokeDasharray="3 3" horizontal={false} />
        <XAxis type="number" stroke="#9ca3af" tick={{ fontSize: 11 }} />
        <YAxis type="category" dataKey="name" stroke="#e4e4e7" tick={{ fontSize: 11 }} width={70} />
        <Tooltip contentStyle={{ background: "#1a1d27", border: "1px solid #374151", borderRadius: 6, fontSize: 12 }} />
        <Bar dataKey="value" radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function Tab({ active, onClick, label, badge, badgeColor }) {
  return (
    <button
      onClick={onClick}
      className={"px-4 py-3 text-sm font-medium whitespace-nowrap transition-colors border-b-2 " +
        (active ? "text-indigo-400 border-indigo-400" : "text-gray-500 border-transparent hover:text-gray-200")}
    >
      {label}
      {badge != null && (
        <span className={"ml-1.5 px-1.5 py-0.5 rounded text-[10px] " + (badgeColor || "bg-indigo-500/15 text-indigo-400")}>
          {badge}
        </span>
      )}
    </button>
  );
}

function SummaryTab({ data }) {
  const findings = [];
  if (data.stats.cannib) findings.push({ label: "Critical", color: "bg-red-500/15 text-red-400", text: data.stats.cannib + " clusters cannibalized" });
  if (data.stats.p1_ideas) findings.push({ label: "Opportunity", color: "bg-blue-500/15 text-blue-400", text: data.stats.p1_ideas + " P1 content briefs ready (validated by 2+ competitors)" });
  if (data.stats.clusters) findings.push({ label: "Strength", color: "bg-green-500/15 text-green-400", text: data.stats.clusters + " topic clusters identified" });
  return (
    <div>
      <HealthHero health={data.health} />
      <StatCards stats={data.stats} />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-lg border border-gray-700 bg-gray-800 p-5">
          <div className="text-xs text-gray-400 uppercase tracking-wide font-semibold mb-3">Key Findings</div>
          <div className="space-y-2 text-sm">
            {findings.length ? findings.map((f, i) => (
              <div key={i}>
                <span className={"px-2 py-0.5 rounded text-[11px] font-semibold " + f.color}>{f.label}</span>
                <span className="ml-2 text-gray-200">{f.text}</span>
              </div>
            )) : <div className="text-gray-500 text-sm">No findings yet.</div>}
          </div>
        </div>
        <div className="rounded-lg border border-gray-700 bg-gray-800 p-5">
          <div className="text-xs text-gray-400 uppercase tracking-wide font-semibold mb-3">Topic Cluster Quadrant</div>
          <Quadrant clusters={data.clusters} cannib={data.cannib} />
          <div className="text-[10px] text-gray-500 mt-2 text-center">x: pages in cluster · y: cannibalized pages · top-right = consolidate first</div>
        </div>
      </div>
    </div>
  );
}

function ContentIdeasTab({ ideas }) {
  const [filter, setFilter] = useState("");
  const [expanded, setExpanded] = useState({});
  if (!ideas || !ideas.length) {
    return (
      <div className="rounded-xl border-2 border-dashed border-gray-700 p-12 text-center text-gray-400">
        <div className="text-3xl mb-2 opacity-40">∅</div>
        <div className="text-gray-200 mb-1">No content briefs yet</div>
        <div className="text-xs">Re-run the pipeline with <code className="bg-gray-800 px-1.5 py-0.5 rounded text-[11px]">--competitor</code>.</div>
      </div>
    );
  }
  const fl = filter.toLowerCase();
  const rows = ideas.filter((i) =>
    !fl || i.title.toLowerCase().includes(fl) || i.topic.toLowerCase().includes(fl) || i.type.toLowerCase().includes(fl)
  );
  const counts = { P1: 0, P2: 0, P3: 0 };
  ideas.forEach((i) => { counts[i.priority] = (counts[i.priority] || 0) + 1; });
  return (
    <div>
      <div className="grid grid-cols-4 gap-px bg-gray-700 rounded-lg overflow-hidden mb-4">
        <div className="bg-gray-800 p-4 text-center">
          <div className="text-3xl font-bold text-indigo-400">{ideas.length}</div>
          <div className="text-[10px] text-gray-400 uppercase tracking-wide mt-1">Total Briefs</div>
        </div>
        <div className="bg-gray-800 p-4 text-center">
          <div className="text-3xl font-bold text-red-400">{counts.P1}</div>
          <div className="text-[10px] text-gray-400 uppercase tracking-wide mt-1">P1</div>
        </div>
        <div className="bg-gray-800 p-4 text-center">
          <div className="text-3xl font-bold text-yellow-400">{counts.P2}</div>
          <div className="text-[10px] text-gray-400 uppercase tracking-wide mt-1">P2</div>
        </div>
        <div className="bg-gray-800 p-4 text-center">
          <div className="text-3xl font-bold text-blue-400">{counts.P3}</div>
          <div className="text-[10px] text-gray-400 uppercase tracking-wide mt-1">P3</div>
        </div>
      </div>
      <input
        type="text"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Search briefs by title, topic, or content type..."
        className="w-full px-4 py-2.5 rounded-lg bg-gray-800 border border-gray-700 text-gray-200 text-sm placeholder-gray-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none mb-3"
      />
      <div className="space-y-2.5">
        {rows.map((i, idx) => {
          const isOpen = !!expanded[idx];
          return (
            <div
              key={idx}
              onClick={() => setExpanded({ ...expanded, [idx]: !isOpen })}
              className="rounded-lg border border-gray-700 bg-gray-800 p-4 cursor-pointer hover:border-gray-600 transition-colors"
            >
              <div className="flex justify-between items-start gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                    <span className={"px-2 py-0.5 rounded text-[11px] font-semibold border " + PRIORITY_COLOR[i.priority]}>
                      {i.priority}
                    </span>
                    <span className="px-2 py-0.5 rounded text-[11px] font-semibold"
                          style={{ background: (INTENT_COLOR[i.intent] || "#6366f1") + "22", color: INTENT_COLOR[i.intent] || "#818cf8" }}>
                      {i.type}
                    </span>
                    <span className="px-2 py-0.5 rounded text-[11px] bg-gray-700 text-gray-400">{i.words}w</span>
                    <span className="text-[11px] text-gray-500">covered by: {i.covered_by}</span>
                  </div>
                  <div className="font-semibold text-gray-100 text-sm leading-snug">{i.title}</div>
                  <div className="text-[12px] text-gray-500 mt-1">
                    Gap topic: <em>{i.topic}</em> · Audience: {i.audience}
                  </div>
                </div>
                <span className={"text-gray-500 transition-transform " + (isOpen ? "rotate-90" : "")}>▶</span>
              </div>
              {isOpen && (
                <div className="mt-3 pt-3 border-t border-gray-700 grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <div className="text-[10px] text-gray-500 uppercase tracking-wide font-semibold mb-2">Target keywords</div>
                    <div className="flex flex-wrap gap-1.5">
                      {i.keywords.map((k, kIdx) => (
                        <span key={kIdx} className="px-2 py-0.5 rounded text-[11px] bg-blue-500/15 text-blue-400">{k}</span>
                      ))}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-gray-500 uppercase tracking-wide font-semibold mb-2">Key questions to answer</div>
                    <ul className="text-[12px] text-gray-300 space-y-1 list-disc pl-5">
                      {i.questions.map((q, qIdx) => <li key={qIdx}>{q}</li>)}
                    </ul>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function CannibTab({ cannib }) {
  const [expanded, setExpanded] = useState({});
  if (!cannib || !cannib.length) {
    return (
      <div className="rounded-xl border-2 border-dashed border-gray-700 p-12 text-center text-gray-400">
        <div className="text-3xl mb-2 opacity-40">∅</div>
        <div className="text-gray-200">No cannibalization detected — clean topical structure.</div>
      </div>
    );
  }
  return (
    <div>
      <div className="rounded-lg border border-gray-700 bg-gray-800 p-5 mb-4">
        <div className="text-xs text-gray-400 uppercase tracking-wide font-semibold mb-3">Cannibalization by cluster</div>
        <div className="overflow-y-auto" style={{ maxHeight: 500 }}>
          <CannibBar cannib={cannib} />
        </div>
      </div>
      <div className="space-y-2.5">
        {cannib.map((c, idx) => {
          const isOpen = !!expanded[idx];
          const sevColor = SEVERITY_COLOR[c.severity];
          const sevBg = c.severity === "critical" ? "bg-red-500/15 text-red-400" :
                        c.severity === "high" ? "bg-yellow-500/15 text-yellow-400" : "bg-green-500/15 text-green-400";
          return (
            <div
              key={idx}
              onClick={() => setExpanded({ ...expanded, [idx]: !isOpen })}
              className="rounded-lg border border-gray-700 bg-gray-800 p-4 cursor-pointer hover:border-gray-600"
              style={{ borderLeftWidth: 3, borderLeftColor: sevColor }}
            >
              <div className="flex justify-between items-center">
                <strong className="text-gray-100 text-sm">{c.name}</strong>
                <div className="flex items-center gap-2">
                  <span className={"px-2 py-0.5 rounded text-[11px] font-semibold " + sevBg}>
                    {c.count} URLs · {c.severity}
                  </span>
                  <span className={"text-gray-500 transition-transform " + (isOpen ? "rotate-90" : "")}>▶</span>
                </div>
              </div>
              {isOpen && (
                <div className="mt-3 pt-3 border-t border-gray-700">
                  <div className="text-[11px] text-gray-500 mb-2">Sample of competing URLs:</div>
                  <ul className="text-[12px] text-blue-400 space-y-1">
                    {c.urls.map((u, uIdx) => <li key={uIdx}>{u}</li>)}
                    {c.more > 0 && <li className="text-gray-500">…and {c.more} more</li>}
                  </ul>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function CompetitorsTab({ competitors, siteName }) {
  const [filter, setFilter] = useState("");
  if (!competitors.rows || !competitors.rows.length) {
    return (
      <div className="rounded-xl border-2 border-dashed border-gray-700 p-12 text-center text-gray-400">
        <div className="text-3xl mb-2 opacity-40">∅</div>
        <div className="text-gray-200 mb-1">No competitor data</div>
        <div className="text-xs">Re-run with <code className="bg-gray-800 px-1.5 py-0.5 rounded text-[11px]">--competitor &lt;domain&gt;</code>.</div>
      </div>
    );
  }
  const counts = { GAP: 0, SHARED: 0, ADVANTAGE: 0 };
  competitors.rows.forEach((r) => { counts[r.status] = (counts[r.status] || 0) + 1; });
  const fl = filter.toLowerCase();
  const rows = competitors.rows.filter((r) => !fl || r.topic.toLowerCase().includes(fl));
  return (
    <div>
      <div className="grid grid-cols-3 gap-px bg-gray-700 rounded-lg overflow-hidden mb-4">
        <div className="bg-gray-800 p-4 text-center">
          <div className="text-3xl font-bold text-green-400">{counts.ADVANTAGE}</div>
          <div className="text-[10px] text-gray-400 uppercase tracking-wide mt-1">{siteName} Advantages</div>
        </div>
        <div className="bg-gray-800 p-4 text-center">
          <div className="text-3xl font-bold text-blue-400">{counts.SHARED}</div>
          <div className="text-[10px] text-gray-400 uppercase tracking-wide mt-1">Shared Topics</div>
        </div>
        <div className="bg-gray-800 p-4 text-center">
          <div className="text-3xl font-bold text-red-400">{counts.GAP}</div>
          <div className="text-[10px] text-gray-400 uppercase tracking-wide mt-1">Content Gaps</div>
        </div>
      </div>
      <div className="rounded-lg border border-gray-700 bg-gray-800 p-4 mb-4">
        <CompetitorBar competitors={competitors} />
      </div>
      <input
        type="text"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Search topics..."
        className="w-full px-4 py-2.5 rounded-lg bg-gray-800 border border-gray-700 text-gray-200 text-sm placeholder-gray-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none mb-3"
      />
      <div className="rounded-lg border border-gray-700 overflow-hidden">
        <div className="max-h-[500px] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-900 sticky top-0">
              <tr>
                <th className="text-left px-3 py-2 text-[10px] text-gray-400 uppercase tracking-wide font-medium">Topic</th>
                <th className="text-center px-3 py-2 text-[10px] text-gray-400 uppercase tracking-wide font-medium">{siteName}</th>
                {competitors.names.map((n) => (
                  <th key={n} className="text-center px-3 py-2 text-[10px] text-gray-400 uppercase tracking-wide font-medium">{n}</th>
                ))}
                <th className="text-left px-3 py-2 text-[10px] text-gray-400 uppercase tracking-wide font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, idx) => {
                const statusCls = r.status === "GAP" ? "bg-red-500/15 text-red-400" :
                                  r.status === "ADVANTAGE" ? "bg-green-500/15 text-green-400" : "bg-blue-500/15 text-blue-400";
                return (
                  <tr key={idx} className="border-t border-gray-700 hover:bg-gray-700/30">
                    <td className="px-3 py-2 text-gray-200">{r.topic}</td>
                    <td className="px-3 py-2 text-center text-gray-400">{r.target ? "Y" : ""}</td>
                    {competitors.names.map((n) => (
                      <td key={n} className="px-3 py-2 text-center text-gray-400">{r.competitors && r.competitors[n] ? "Y" : ""}</td>
                    ))}
                    <td className="px-3 py-2"><span className={"px-2 py-0.5 rounded text-[11px] font-semibold " + statusCls}>{r.status}</span></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function ClustersTab({ clusters }) {
  const [filter, setFilter] = useState("");
  const [sortKey, setSortKey] = useState("urls");
  const [sortAsc, setSortAsc] = useState(false);
  if (!clusters || !clusters.length) {
    return <div className="text-gray-500 text-center py-12">No clusters.</div>;
  }
  const fl = filter.toLowerCase();
  const sortedRows = clusters
    .filter((c) => !fl || c.name.toLowerCase().includes(fl) || (c.keywords || "").toLowerCase().includes(fl))
    .slice()
    .sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey];
      if (typeof av === "number") return sortAsc ? av - bv : bv - av;
      return sortAsc ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
    });
  const SortHead = ({ k, label, num }) => (
    <th
      onClick={() => { if (sortKey === k) setSortAsc(!sortAsc); else { setSortKey(k); setSortAsc(false); } }}
      className="text-left px-3 py-2 text-[10px] text-gray-400 uppercase tracking-wide font-medium cursor-pointer hover:text-gray-200"
    >
      {label} {sortKey === k ? (sortAsc ? "↑" : "↓") : ""}
    </th>
  );
  return (
    <div>
      <input
        type="text"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Search clusters by name or keyword..."
        className="w-full px-4 py-2.5 rounded-lg bg-gray-800 border border-gray-700 text-gray-200 text-sm placeholder-gray-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none mb-3"
      />
      <div className="rounded-lg border border-gray-700 overflow-hidden">
        <div className="max-h-[600px] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-900 sticky top-0">
              <tr>
                <SortHead k="id" label="ID" />
                <SortHead k="name" label="Cluster" />
                <SortHead k="urls" label="URLs" num />
                <th className="text-left px-3 py-2 text-[10px] text-gray-400 uppercase tracking-wide font-medium">Keywords</th>
                <th className="text-left px-3 py-2 text-[10px] text-gray-400 uppercase tracking-wide font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {sortedRows.map((c) => (
                <tr key={c.id} className="border-t border-gray-700 hover:bg-gray-700/30">
                  <td className="px-3 py-2 text-gray-400">{c.id}</td>
                  <td className="px-3 py-2 text-gray-100 font-medium">{c.name}</td>
                  <td className="px-3 py-2 text-gray-300">{c.urls}</td>
                  <td className="px-3 py-2 text-gray-500 text-[12px] max-w-[280px] truncate" title={c.keywords}>{c.keywords}</td>
                  <td className="px-3 py-2">
                    {c.cannibalized
                      ? <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-red-500/15 text-red-400">Cannibalized</span>
                      : <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-green-500/15 text-green-400">OK</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default function TopicalAuthorityDashboard() {
  const [tab, setTab] = useState("summary");
  const TABS = [
    { id: "summary", label: "Summary" },
    { id: "ideas", label: "Content Ideas", badge: DATA.stats.ideas, color: "bg-indigo-500/15 text-indigo-400" },
    { id: "cannib", label: "Cannibalization", badge: DATA.stats.cannib, color: "bg-red-500/15 text-red-400" },
    { id: "competitors", label: "Competitors" },
    { id: "clusters", label: "Topic Clusters", badge: DATA.stats.clusters, color: "bg-indigo-500/15 text-indigo-400" },
  ];
  return (
    <div className="min-h-screen bg-gray-950 text-gray-100" style={{ fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" }}>
      <div className="bg-gray-900 border-b border-gray-700 px-6 py-4 flex justify-between items-center">
        <div>
          <h1 className="text-lg font-bold">Topical Authority Audit</h1>
          <div className="text-xs text-gray-400">{DATA.site.domain}</div>
        </div>
        <div className="text-xs text-gray-400 text-right">
          {DATA.site.name}{DATA.site.industry ? " · " + DATA.site.industry : ""}<br />
          {DATA.stats.urls} pages analyzed
        </div>
      </div>
      <div className="bg-gray-900 border-b border-gray-700 flex overflow-x-auto px-4 sticky top-0 z-10">
        {TABS.map((t) => (
          <Tab key={t.id} active={tab === t.id} onClick={() => setTab(t.id)} label={t.label} badge={t.badge} badgeColor={t.color} />
        ))}
      </div>
      <div className="p-6">
        {tab === "summary" && <SummaryTab data={DATA} />}
        {tab === "ideas" && <ContentIdeasTab ideas={DATA.ideas} />}
        {tab === "cannib" && <CannibTab cannib={DATA.cannib} />}
        {tab === "competitors" && <CompetitorsTab competitors={DATA.competitors} siteName={DATA.site.name} />}
        {tab === "clusters" && <ClustersTab clusters={DATA.clusters} />}
      </div>
      <div className="border-t border-gray-700 px-6 py-3 text-center text-[11px] text-gray-500">
        Topical Authority Mapper · {DATA.site.name}
      </div>
    </div>
  );
}
"""


def build_artifact_tsx(site_config: SiteConfig) -> str:
    """Render the dashboard_artifact.tsx contents for the current run."""
    data = _gather_data(site_config)
    return _TSX_TEMPLATE.replace("__DATA_PLACEHOLDER__", json.dumps(data, indent=2))


def generate_artifact(site_config: Optional[SiteConfig] = None) -> str:
    """Build and write the artifact file. Returns the file path."""
    if site_config is None:
        site_config = load_site_config() or SiteConfig(name="Site", domain="")
    tsx = build_artifact_tsx(site_config)
    out = output_dir()
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, "dashboard_artifact.tsx")
    with open(path, "w") as f:
        f.write(tsx)
    logger.info("Artifact written: %s (%d bytes)", path, len(tsx))
    return path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = generate_artifact()
    print(f"Artifact: {p}")
