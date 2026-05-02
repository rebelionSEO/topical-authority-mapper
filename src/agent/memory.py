"""Agent memory — episodic log + per-run trace persistence.

Episodic log (runs/<site>/agent_log.jsonl):
  Append-only JSONL — one row per agent run. Each row records the question,
  the final recommendation summary, the lessons captured, and timestamps.
  Used to detect "you already greenlit X this week, don't re-recommend it"
  patterns + as the source of truth for the dashboard's Recommend tab history.

Per-run traces (runs/<site>/agent_runs/<timestamp>.json):
  Full structured trace of a single agent run — every tool call + result, the
  reasoning blocks, the final recommendation. Persisted for audit / replay.
"""

import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    name: str
    arguments: dict
    result_preview: str  # truncated JSON of the result


@dataclass
class AgentRun:
    run_id: str
    site_slug: str
    started_at: float
    finished_at: Optional[float] = None
    question: str = ""
    model: str = ""
    tool_calls: list = field(default_factory=list)  # list[ToolCall as dict]
    final_recommendation: Optional[dict] = None
    self_critique_lessons_captured: int = 0
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def _runs_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "../../runs"))


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_") or "site"


def _site_dir(site_slug: str) -> str:
    p = os.path.join(_runs_root(), _slugify(site_slug))
    os.makedirs(p, exist_ok=True)
    return p


def new_run(site_slug: str, question: str, model: str) -> AgentRun:
    """Start a new agent run with a timestamp-based run_id."""
    return AgentRun(
        run_id=datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S"),
        site_slug=site_slug,
        started_at=time.time(),
        question=question,
        model=model,
    )


def persist_run(run: AgentRun) -> str:
    """Write the full per-run trace + append a row to agent_log.jsonl. Returns trace path."""
    site_dir = _site_dir(run.site_slug)
    runs_dir = os.path.join(site_dir, "agent_runs")
    os.makedirs(runs_dir, exist_ok=True)
    trace_path = os.path.join(runs_dir, f"{run.run_id}.json")

    data = run.to_dict()
    try:
        with open(trace_path, "w") as f:
            json.dump(data, f, indent=2, default=str)
    except OSError as e:
        logger.warning("Could not persist agent run trace: %s", e)

    # Append summary row to the JSONL log
    log_path = os.path.join(site_dir, "agent_log.jsonl")
    summary = {
        "run_id": run.run_id,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "duration_sec": round((run.finished_at or run.started_at) - run.started_at, 2),
        "question": run.question,
        "model": run.model,
        "n_tool_calls": len(run.tool_calls),
        "n_lessons_captured": run.self_critique_lessons_captured,
        "final_summary": (run.final_recommendation or {}).get("summary", "")[:300] if run.final_recommendation else None,
        "error": run.error,
    }
    try:
        with open(log_path, "a") as f:
            f.write(json.dumps(summary) + "\n")
    except OSError as e:
        logger.warning("Could not append to agent_log.jsonl: %s", e)

    return trace_path


def recent_runs(site_slug: str, limit: int = 10) -> list[dict]:
    """Read the latest N rows from agent_log.jsonl (most recent first)."""
    log_path = os.path.join(_site_dir(site_slug), "agent_log.jsonl")
    if not os.path.exists(log_path):
        return []
    try:
        with open(log_path) as f:
            rows = [json.loads(line) for line in f if line.strip()]
    except (OSError, json.JSONDecodeError):
        return []
    return list(reversed(rows[-limit:]))


def load_run_trace(site_slug: str, run_id: str) -> Optional[dict]:
    """Load a full per-run trace by ID. Used by the dashboard for inspect/replay."""
    path = os.path.join(_site_dir(site_slug), "agent_runs", f"{run_id}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
