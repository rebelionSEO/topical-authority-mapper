"""Composite Site Health Score + run-over-run deltas.

Computes a single 0-100 score and 5 traffic-light subscores from the pipeline outputs,
plus a delta vs the previous run snapshot.

Subscores:
  coverage      - breadth of topical clusters (more = stronger, capped)
  cannibalization - inverse of % clusters with conflicts (higher = healthier)
  freshness     - share of pages NOT stale (12+ months)
  brand         - average brand voice score (if present)
  competitive   - % of topics where target appears (advantages + shared / total)

Each subscore is 0-100 with a label: green (>=75), yellow (50-74), red (<50).
The composite is a weighted average. Weights live in WEIGHTS below.

CLI:
    python -m src.site_health        # compute, print, write output/site_health.json
"""

import argparse
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from typing import Optional

import pandas as pd

from src.config import SiteConfig, load_site_config, output_dir

logger = logging.getLogger(__name__)


WEIGHTS = {
    "coverage": 0.15,
    "cannibalization": 0.30,
    "freshness": 0.15,
    "brand": 0.15,
    "competitive": 0.25,
}


@dataclass
class Subscore:
    score: int  # 0-100
    label: str  # "green" | "yellow" | "red" | "unknown"
    detail: str  # one-line explanation


@dataclass
class HealthSnapshot:
    composite: int
    composite_label: str
    subscores: dict = field(default_factory=dict)
    deltas: dict = field(default_factory=dict)  # composite + per-subscore vs previous run
    sparkline: list = field(default_factory=list)  # last N composite scores, oldest first
    site_name: str = ""
    site_domain: str = ""

    def to_dict(self) -> dict:
        return {
            "composite": self.composite,
            "composite_label": self.composite_label,
            "subscores": {k: asdict(v) for k, v in self.subscores.items()},
            "deltas": self.deltas,
            "sparkline": self.sparkline,
            "site_name": self.site_name,
            "site_domain": self.site_domain,
        }


def _label(score: int) -> str:
    if score >= 75:
        return "green"
    if score >= 50:
        return "yellow"
    if score >= 0:
        return "red"
    return "unknown"


def _safe_int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _clamp(v: float, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, int(round(v))))


def _read_csv(path: str) -> Optional[pd.DataFrame]:
    if not os.path.exists(path):
        return None
    try:
        return pd.read_csv(path)
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return None


# ---------------------------------------------------------------------------
# Subscore calculators (each returns Subscore or None if data missing)
# ---------------------------------------------------------------------------

def _score_coverage(out: str) -> Optional[Subscore]:
    clusters = _read_csv(os.path.join(out, "clusters.csv"))
    url_map = _read_csv(os.path.join(out, "url_mapping.csv"))
    if clusters is None or url_map is None or clusters.empty:
        return None
    n_clusters = len(clusters)
    n_urls = len(url_map)
    # Sweet spot heuristic: ~1 cluster per 10-30 URLs is healthy
    target_min = max(n_urls // 30, 5)
    target_ideal = max(n_urls // 15, 10)
    if n_clusters >= target_ideal:
        score = 90
    elif n_clusters >= target_min:
        score = 60 + ((n_clusters - target_min) / max(target_ideal - target_min, 1)) * 30
    else:
        score = 30 * (n_clusters / max(target_min, 1))
    s = _clamp(score)
    return Subscore(score=s, label=_label(s), detail=f"{n_clusters} clusters across {n_urls} URLs")


def _score_cannibalization(out: str) -> Optional[Subscore]:
    clusters = _read_csv(os.path.join(out, "clusters.csv"))
    cannib = _read_csv(os.path.join(out, "cannibalization.csv"))
    if clusters is None or clusters.empty:
        return None
    n_clusters = len(clusters)
    n_cannib = len(cannib) if cannib is not None else 0
    pct_healthy = (n_clusters - n_cannib) / n_clusters if n_clusters else 1
    s = _clamp(pct_healthy * 100)
    return Subscore(score=s, label=_label(s), detail=f"{n_cannib} of {n_clusters} clusters cannibalized")


def _score_freshness(out: str) -> Optional[Subscore]:
    fresh = _read_csv(os.path.join(out, "content_freshness.csv"))
    if fresh is None or fresh.empty:
        return None
    total = len(fresh)
    stale = ((fresh["freshness"].astype(str).str.contains("Stale|Decaying", na=False)).sum())
    pct_healthy = (total - stale) / total if total else 1
    s = _clamp(pct_healthy * 100)
    return Subscore(score=s, label=_label(s), detail=f"{stale} of {total} pages 6+ months old")


def _score_brand(out: str) -> Optional[Subscore]:
    brand = _read_csv(os.path.join(out, "brand_voice_scores.csv"))
    if brand is None or brand.empty:
        return None
    avg = float(brand["brand_score"].mean())
    s = _clamp(avg)
    return Subscore(score=s, label=_label(s), detail=f"avg {avg:.0f}/100 across {len(brand)} pages")


def _score_competitive(out: str) -> Optional[Subscore]:
    """% of topics in the gap matrix where the target site appears (vs gaps where it doesn't)."""
    if not os.path.isdir(out):
        return None
    gap_files = [
        os.path.join(out, f) for f in os.listdir(out)
        if f.startswith("competitor_gap_") and f.endswith(".csv")
    ]
    if not gap_files:
        return None
    # De-dupe across competitors — a topic shared by 3 competitors should count as ONE topic,
    # not three. Build a set of unique (topic_lower, status_class) per topic.
    topic_status: dict = {}
    for path in gap_files:
        df = _read_csv(path)
        if df is None or df.empty or "status" not in df.columns or "keyword" not in df.columns:
            continue
        for _, row in df.iterrows():
            topic = str(row.get("keyword", "")).strip().lower()
            status = str(row.get("status", "")).upper()
            if not topic:
                continue
            # Classify each row into one of: target_only / shared / gap_only.
            # Match on word boundaries to avoid the "competitor covers" → matches COVER bug.
            import re as _re
            is_advantage = bool(_re.search(r"\bADVANTAGE\b", status))
            is_shared = bool(_re.search(r"\bSHARED\b", status)) or "BOTH COVER" in status
            is_gap = bool(_re.search(r"\bGAP\b", status))
            if is_shared:
                cls = "shared"
            elif is_advantage:
                cls = "advantage"
            elif is_gap:
                cls = "gap"
            else:
                continue
            # Promote "shared" or "advantage" over "gap" if a topic appears in multiple gap files
            # with different verdicts (target presence is global, not per-competitor).
            prev = topic_status.get(topic)
            if prev != "shared" and cls == "shared":
                topic_status[topic] = "shared"
            elif prev not in ("shared", "advantage") and cls == "advantage":
                topic_status[topic] = "advantage"
            elif prev is None:
                topic_status[topic] = cls

    total_topics = len(topic_status)
    if total_topics == 0:
        return None
    target_present = sum(1 for v in topic_status.values() if v in ("advantage", "shared"))
    pct = target_present / total_topics
    s = _clamp(pct * 100)
    return Subscore(score=s, label=_label(s), detail=f"covers {target_present} of {total_topics} unique topics vs competitors")


# ---------------------------------------------------------------------------
# Composite + deltas
# ---------------------------------------------------------------------------

def compute_health(site_config: Optional[SiteConfig] = None) -> HealthSnapshot:
    if site_config is None:
        site_config = load_site_config() or SiteConfig(name="Site", domain="")

    out = output_dir()
    raw = {
        "coverage": _score_coverage(out),
        "cannibalization": _score_cannibalization(out),
        "freshness": _score_freshness(out),
        "brand": _score_brand(out),
        "competitive": _score_competitive(out),
    }

    # Composite: weighted average over the subscores that exist
    weighted_sum = 0.0
    weight_total = 0.0
    for key, sub in raw.items():
        if sub is None:
            continue
        w = WEIGHTS.get(key, 0)
        weighted_sum += sub.score * w
        weight_total += w
    composite = _clamp(weighted_sum / weight_total) if weight_total > 0 else 0
    composite_label = _label(composite) if weight_total > 0 else "unknown"

    # Subscores dict — fill missing with placeholder
    subscores = {}
    for key, sub in raw.items():
        if sub is None:
            subscores[key] = Subscore(score=0, label="unknown", detail="no data — feature not enabled")
        else:
            subscores[key] = sub

    snapshot = HealthSnapshot(
        composite=composite,
        composite_label=composite_label,
        subscores=subscores,
        site_name=site_config.name,
        site_domain=site_config.domain,
    )

    # Deltas + sparkline from run history
    deltas, sparkline = _compute_history_context(site_config, snapshot)
    snapshot.deltas = deltas
    snapshot.sparkline = sparkline

    return snapshot


def _compute_history_context(site_config: SiteConfig, current: HealthSnapshot) -> tuple[dict, list]:
    """Read run history to compute deltas vs previous run + a sparkline of composite over time."""
    try:
        from src.run_history import load_history, DEFAULT_RUNS_ROOT
    except Exception:
        return {}, [current.composite]

    history = load_history(site_config.name, runs_root=DEFAULT_RUNS_ROOT)
    if not history:
        return {}, [current.composite]

    # Each history entry has totals; we don't have past health scores stored explicitly.
    # Sparkline: pull stored composite from each snapshot's site_health.json if present, else
    # use a coarse proxy from totals (1 - cannib/clusters) for backwards compat.
    sparkline: list = []
    for h in history:
        snap_dir = h.get("snapshot_dir")
        composite = None
        if snap_dir:
            health_path = os.path.join(snap_dir, "output", "site_health.json")
            if os.path.exists(health_path):
                try:
                    with open(health_path) as f:
                        composite = int(json.load(f).get("composite", 0))
                except (OSError, json.JSONDecodeError, ValueError):
                    composite = None
        if composite is None:
            totals = h.get("totals", {}) or {}
            clusters = _safe_int(totals.get("clusters"))
            cannib = _safe_int(totals.get("cannibalization"))
            composite = _clamp(((clusters - cannib) / clusters * 100) if clusters else 50)
        sparkline.append(composite)
    sparkline.append(current.composite)

    # Deltas vs the immediately previous run
    deltas: dict = {}
    if sparkline and len(sparkline) >= 2:
        deltas["composite"] = current.composite - sparkline[-2]

    # Per-subscore delta — only if previous run had a saved health.json with the same key
    if history:
        prev = history[-1]
        snap_dir = prev.get("snapshot_dir")
        if snap_dir:
            health_path = os.path.join(snap_dir, "output", "site_health.json")
            if os.path.exists(health_path):
                try:
                    with open(health_path) as f:
                        prev_health = json.load(f)
                    prev_subs = prev_health.get("subscores", {})
                    for key, cur_sub in current.subscores.items():
                        prev_score = prev_subs.get(key, {}).get("score")
                        if isinstance(prev_score, (int, float)):
                            deltas[key] = cur_sub.score - int(prev_score)
                except (OSError, json.JSONDecodeError):
                    pass

    return deltas, sparkline


def write_health(snapshot: HealthSnapshot) -> str:
    out = output_dir()
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, "site_health.json")
    with open(path, "w") as f:
        json.dump(snapshot.to_dict(), f, indent=2, default=str)
    return path


def main():
    parser = argparse.ArgumentParser(description="Compute site health composite score.")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    snap = compute_health()
    path = write_health(snap)
    if not args.quiet:
        print(f"\nSite Health: {snap.composite}/100 ({snap.composite_label.upper()})")
        for k, sub in snap.subscores.items():
            print(f"  {k:<18} {sub.score:>3}/100  [{sub.label.upper():<7}] {sub.detail}")
        if snap.deltas:
            d = snap.deltas.get("composite")
            if d is not None:
                arrow = "↑" if d > 0 else "↓" if d < 0 else "—"
                print(f"\nDelta vs previous run: {arrow} {abs(d)} points")
        print(f"\nWrote {path}")


if __name__ == "__main__":
    main()
