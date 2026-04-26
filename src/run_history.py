"""Per-site run history.

Each pipeline run gets archived to a timestamped directory so historical context isn't
lost when the next run overwrites output/. The current run remains at output/ for the
dashboard/report; the snapshot is a permanent record.

Layout:

    <runs_root>/<site_slug>/
        history.json            # ordered list of run metadata
        latest -> <run_id>/     # symlink to the most recent snapshot (best-effort)
        2026-04-26-1145/
            output/             # snapshot of all CSVs/HTML/PDF for this run
            site_config.json    # snapshot of cache/site_config.json
            brand_profile.json  # snapshot of cache/brand_profile.json (if exists)
            qa_report.json      # snapshot of QA findings
            metadata.json       # high-level totals + run context

Embeddings (cache/embeddings.pkl) are NOT snapshotted — they're large and regenerable.

The history index lets you quickly diff totals across runs without re-loading every
CSV. Use load_history(site_slug) to read it.
"""

import json
import logging
import os
import re
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from src.config import SiteConfig, cache_dir, output_dir

logger = logging.getLogger(__name__)


DEFAULT_RUNS_ROOT = os.path.abspath("./runs")
HISTORY_FILENAME = "history.json"
METADATA_FILENAME = "metadata.json"
LATEST_LINK = "latest"


@dataclass
class RunMetadata:
    run_id: str
    site_name: str
    site_domain: str
    timestamp_utc: str
    industry: Optional[str] = None
    competitors: list = field(default_factory=list)
    totals: dict = field(default_factory=dict)
    qa_summary: dict = field(default_factory=dict)
    snapshot_dir: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "site"


def generate_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M")


def _site_dir(runs_root: str, site_name: str) -> str:
    return os.path.join(runs_root, slugify(site_name))


def _safe_int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _load_int_count(path: str) -> int:
    """Count rows in a CSV (excluding header) without loading the whole file into memory."""
    if not os.path.exists(path):
        return 0
    try:
        with open(path, "r") as f:
            return max(sum(1 for _ in f) - 1, 0)
    except OSError:
        return 0


def _gather_totals() -> dict:
    """Pull headline numbers from the current output dir into a flat dict."""
    out = output_dir()
    totals = {
        "urls": _load_int_count(os.path.join(out, "url_mapping.csv")),
        "clusters": _load_int_count(os.path.join(out, "clusters.csv")),
        "cannibalization": _load_int_count(os.path.join(out, "cannibalization.csv")),
        "skipped": _load_int_count(os.path.join(out, "skipped_urls.csv")),
        "content_ideas": _load_int_count(os.path.join(out, "content_ideas.csv")),
    }
    # Number of competitor gap CSVs present
    if os.path.isdir(out):
        totals["competitors"] = sum(
            1 for f in os.listdir(out) if f.startswith("competitor_gap_") and f.endswith(".csv")
        )
    return totals


def _load_qa_summary(out: str) -> dict:
    qa_path = os.path.join(out, "qa_report.json")
    if not os.path.exists(qa_path):
        return {}
    try:
        with open(qa_path) as f:
            data = json.load(f)
        return data.get("summary", {}) or {}
    except (OSError, json.JSONDecodeError):
        return {}


def snapshot_run(
    site_config: SiteConfig,
    runs_root: str = DEFAULT_RUNS_ROOT,
    run_id: Optional[str] = None,
) -> RunMetadata:
    """Copy the current output dir + small cache files into a timestamped snapshot.

    Returns the RunMetadata that was appended to history.json.
    """
    out = output_dir()
    if not os.path.isdir(out):
        raise RuntimeError(f"Cannot snapshot: output dir does not exist ({out})")

    rid = run_id or generate_run_id()
    site_dir = _site_dir(runs_root, site_config.name)
    snap_dir = os.path.join(site_dir, rid)
    snap_output = os.path.join(snap_dir, "output")
    os.makedirs(snap_dir, exist_ok=True)

    # Copy output (overwrite-safe)
    if os.path.exists(snap_output):
        shutil.rmtree(snap_output)
    shutil.copytree(out, snap_output)

    # Copy small cache files (skip embeddings — too large, regenerable)
    cache = cache_dir()
    for fname in ("site_config.json", "brand_profile.json"):
        src = os.path.join(cache, fname)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(snap_dir, fname))

    # Snapshot QA report alongside (it may already be inside output/, but mirror at top
    # level for quick access)
    qa_src = os.path.join(out, "qa_report.json")
    if os.path.exists(qa_src):
        shutil.copy2(qa_src, os.path.join(snap_dir, "qa_report.json"))

    metadata = RunMetadata(
        run_id=rid,
        site_name=site_config.name,
        site_domain=site_config.domain,
        timestamp_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        industry=site_config.industry,
        competitors=list(site_config.competitors),
        totals=_gather_totals(),
        qa_summary=_load_qa_summary(out),
        snapshot_dir=snap_dir,
    )

    # Per-snapshot metadata
    with open(os.path.join(snap_dir, METADATA_FILENAME), "w") as f:
        json.dump(metadata.to_dict(), f, indent=2)

    # Append to history index
    history_path = os.path.join(site_dir, HISTORY_FILENAME)
    history = []
    if os.path.exists(history_path):
        try:
            with open(history_path) as f:
                history = json.load(f)
            if not isinstance(history, list):
                history = []
        except (OSError, json.JSONDecodeError):
            history = []
    history.append(metadata.to_dict())
    with open(history_path, "w") as f:
        json.dump(history, f, indent=2)

    # Update 'latest' symlink (best-effort; non-symlink filesystems just skip)
    latest_path = os.path.join(site_dir, LATEST_LINK)
    try:
        if os.path.islink(latest_path) or os.path.exists(latest_path):
            if os.path.islink(latest_path) or os.path.isfile(latest_path):
                os.remove(latest_path)
            else:
                shutil.rmtree(latest_path)
        os.symlink(rid, latest_path)
    except (OSError, NotImplementedError) as e:
        logger.debug("Could not create 'latest' symlink: %s", e)

    logger.info("Snapshot written: %s", snap_dir)
    return metadata


def load_history(site_name: str, runs_root: str = DEFAULT_RUNS_ROOT) -> list[dict]:
    """Return the full history list for a site, oldest-first. Empty list if none."""
    history_path = os.path.join(_site_dir(runs_root, site_name), HISTORY_FILENAME)
    if not os.path.exists(history_path):
        return []
    try:
        with open(history_path) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def latest_run(site_name: str, runs_root: str = DEFAULT_RUNS_ROOT) -> Optional[dict]:
    history = load_history(site_name, runs_root)
    return history[-1] if history else None


def diff_against_previous(site_name: str, runs_root: str = DEFAULT_RUNS_ROOT) -> Optional[dict]:
    """Return delta totals between the two most recent runs (latest - previous)."""
    history = load_history(site_name, runs_root)
    if len(history) < 2:
        return None
    prev, curr = history[-2], history[-1]
    delta = {}
    for key in set(prev.get("totals", {})) | set(curr.get("totals", {})):
        delta[key] = _safe_int(curr.get("totals", {}).get(key)) - _safe_int(prev.get("totals", {}).get(key))
    return {
        "from_run": prev.get("run_id"),
        "to_run": curr.get("run_id"),
        "delta": delta,
    }
