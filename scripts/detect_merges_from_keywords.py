"""Detect cluster-merge candidates from keyword Jaccard similarity.

The pipeline's centroid-based merge detection requires chunks_df (not cached),
so we approximate it from cluster keyword overlap which is the next-best signal.

Two clusters with the same name (e.g. "Marketing Leaders" appearing twice) or
with high keyword Jaccard are flagged as MERGE / REVIEW candidates.

Reads output/clusters.csv and output/url_mapping.csv. Writes
output/cluster_merge_suggestions.csv.
"""
from __future__ import annotations

import csv
import logging
import os
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def main() -> None:
    clusters_path = ROOT / "output" / "clusters.csv"
    url_map_path = ROOT / "output" / "url_mapping.csv"
    out_path = ROOT / "output" / "cluster_merge_suggestions.csv"

    with clusters_path.open() as f:
        clusters = list(csv.DictReader(f))

    with url_map_path.open() as f:
        url_rows = list(csv.DictReader(f))

    # cluster_id -> URL count
    sizes = Counter(r["main_cluster"] for r in url_rows if r.get("main_cluster") not in ("", "-1"))

    # cluster_id -> keyword set
    kw_sets: dict[str, set[str]] = {}
    for c in clusters:
        kws = {k.strip().lower() for k in (c["keywords"] or "").split(",") if k.strip()}
        kw_sets[c["cluster_id"]] = kws

    cluster_name = {c["cluster_id"]: c["cluster_name"] for c in clusters}

    candidates = []
    for a, b in combinations(clusters, 2):
        cid_a, cid_b = a["cluster_id"], b["cluster_id"]
        if cid_a == "-1" or cid_b == "-1":
            continue
        sim = jaccard(kw_sets[cid_a], kw_sets[cid_b])
        same_name = cluster_name[cid_a].strip().lower() == cluster_name[cid_b].strip().lower()
        if sim < 0.20 and not same_name:
            continue

        # Same name → automatic MERGE regardless of Jaccard (the LLM cluster-namer
        # converged to the same label, which is the strongest possible signal).
        # Promote similarity to 1.0 for ranking + red-flagging in the dashboard.
        if same_name:
            recommendation = "MERGE"
            reason = "duplicate cluster name — same topic split across cluster IDs"
            sim = 1.0
        elif sim >= 0.40:
            recommendation = "MERGE"
            reason = f"{round(sim*100)}% keyword overlap"
        elif sim >= 0.30:
            recommendation = "REVIEW for merge"
            reason = f"{round(sim*100)}% keyword overlap"
        else:
            recommendation = "REVIEW for merge"
            reason = f"{round(sim*100)}% keyword overlap"

        # Compute combined size as merged-cluster URL count
        combined_size = int(sizes.get(cid_a, 0)) + int(sizes.get(cid_b, 0))

        candidates.append({
            "cluster_a_id": cid_a,
            "cluster_a_name": cluster_name[cid_a],
            "cluster_a_size": int(sizes.get(cid_a, 0)),
            "cluster_b_id": cid_b,
            "cluster_b_name": cluster_name[cid_b],
            "cluster_b_size": int(sizes.get(cid_b, 0)),
            "similarity": round(sim, 4),
            "combined_size": combined_size,
            "recommendation": recommendation,
            "reason": reason,
        })

    # Sort: MERGE first, then by similarity desc
    candidates.sort(key=lambda r: (r["recommendation"] != "MERGE", -r["similarity"]))

    fieldnames = [
        "cluster_a_id", "cluster_a_name", "cluster_a_size",
        "cluster_b_id", "cluster_b_name", "cluster_b_size",
        "similarity", "combined_size", "recommendation", "reason",
    ]
    with out_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(candidates)

    merge_count = sum(1 for c in candidates if c["recommendation"] == "MERGE")
    logging.info("Wrote %d candidates (%d MERGE, %d REVIEW) to %s",
                 len(candidates), merge_count, len(candidates) - merge_count, out_path)
    if candidates[:5]:
        logging.info("Top 5:")
        for c in candidates[:5]:
            logging.info("  [%s] %s (%d) ⇄ %s (%d) — sim=%.2f — %s",
                         c["recommendation"], c["cluster_a_name"], c["cluster_a_size"],
                         c["cluster_b_name"], c["cluster_b_size"], c["similarity"], c["reason"])


if __name__ == "__main__":
    main()
