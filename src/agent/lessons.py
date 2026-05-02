"""Learning loop — append-only markdown ledger of lessons the agent picks up.

Two capture mechanisms feed this file:
  1. Self-critique step at the end of every agent run (the agent calls note_lesson)
  2. Operator feedback via src.agent.feedback CLI

On every subsequent run, the latest N lessons get prepended to the system prompt
so the agent literally gets sharper over time. Operators can edit/delete lessons
in the markdown file directly — full transparency.

File location: <runs_root>/<site_slug>/agent_lessons.md
"""

import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


LESSONS_FILE = "agent_lessons.md"
DEFAULT_INJECT_LIMIT = 30  # how many recent lessons to put in the system prompt
PER_LESSON_MAX_CHARS = 600  # truncate long lessons before injecting


@dataclass
class Lesson:
    timestamp: str       # ISO 8601
    category: str        # e.g. "cannibalization", "audience", "freshness"
    mistake: str
    lesson: str
    source: str          # "self-critique:run-#14" | "operator-feedback" | "manual-edit"

    def to_md(self) -> str:
        return (
            f"## {self.timestamp} · {self.category}\n"
            f"**Mistake:** {self.mistake}\n"
            f"**Lesson:** {self.lesson}\n"
            f"_Source: {self.source}_\n"
        )


def lessons_path(site_slug: str, runs_root: str) -> str:
    site_dir = os.path.join(runs_root, _slugify(site_slug))
    os.makedirs(site_dir, exist_ok=True)
    return os.path.join(site_dir, LESSONS_FILE)


def append_lesson(
    site_slug: str,
    category: str,
    mistake: str,
    lesson: str,
    source: str = "manual",
    runs_root: Optional[str] = None,
) -> str:
    """Append a single lesson to the site's learning ledger. Returns the file path."""
    runs_root = runs_root or os.path.abspath(os.path.join(os.path.dirname(__file__), "../../runs"))
    path = lessons_path(site_slug, runs_root)

    new = Lesson(
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        category=(category or "general").strip().lower(),
        mistake=(mistake or "").strip(),
        lesson=(lesson or "").strip(),
        source=(source or "manual").strip(),
    )
    if not new.mistake or not new.lesson:
        logger.warning("Skipped empty lesson (mistake or lesson missing)")
        return path

    # Initialize the file with a header on first write
    write_header = not os.path.exists(path)
    with open(path, "a") as f:
        if write_header:
            f.write(f"# Agent Lessons — {site_slug}\n\n")
            f.write("Append-only markdown ledger. Latest 30 lessons get injected into the agent's\n")
            f.write("system prompt on every run. Edit or delete lessons directly if they're wrong —\n")
            f.write("the agent will pick up your edits next run.\n\n")
        f.write(new.to_md())
        f.write("\n")
    logger.info("Appended lesson to %s (category=%s)", path, new.category)
    return path


def read_recent_lessons(
    site_slug: str,
    limit: int = DEFAULT_INJECT_LIMIT,
    runs_root: Optional[str] = None,
) -> list[Lesson]:
    """Read the most-recent N lessons from the ledger (oldest-first within the slice)."""
    runs_root = runs_root or os.path.abspath(os.path.join(os.path.dirname(__file__), "../../runs"))
    path = lessons_path(site_slug, runs_root)
    if not os.path.exists(path):
        return []

    try:
        with open(path) as f:
            content = f.read()
    except OSError:
        return []

    # Parse the markdown — split on the H2 header pattern
    blocks = re.split(r"\n## ", content)
    # First block is the file header — discard
    raw_entries = blocks[1:] if len(blocks) > 1 else []

    lessons: list[Lesson] = []
    for raw in raw_entries:
        # raw starts with "<timestamp> · <category>\n**Mistake:** ...\n**Lesson:** ...\n_Source: ..._"
        m = re.match(
            r"(?P<ts>[\d\-]+ [\d:]+)\s*·\s*(?P<cat>[^\n]+)\n"
            r"\*\*Mistake:\*\*\s*(?P<mis>.*?)\n"
            r"\*\*Lesson:\*\*\s*(?P<les>.*?)\n"
            r"_Source:\s*(?P<src>[^_]+)_",
            raw, re.DOTALL,
        )
        if not m:
            continue
        lessons.append(Lesson(
            timestamp=m.group("ts").strip(),
            category=m.group("cat").strip(),
            mistake=m.group("mis").strip(),
            lesson=m.group("les").strip(),
            source=m.group("src").strip(),
        ))

    # Take the most-recent N (file order is chronological append)
    return lessons[-limit:]


def lessons_for_prompt(site_slug: str, limit: int = DEFAULT_INJECT_LIMIT) -> str:
    """Format the recent lessons as a markdown block for the system prompt.
    Returns empty string if no lessons yet."""
    lessons = read_recent_lessons(site_slug, limit=limit)
    if not lessons:
        return ""
    out = ["# Prior lessons (read these before acting)"]
    for i, l in enumerate(lessons, start=1):
        m = l.mistake[:PER_LESSON_MAX_CHARS]
        s = l.lesson[:PER_LESSON_MAX_CHARS]
        out.append(f"{i}. [{l.category}] {s}  (After: {m})")
    return "\n".join(out)


def all_lessons(site_slug: str, runs_root: Optional[str] = None) -> list[Lesson]:
    """All lessons in the file, oldest-first. Used by the dashboard Lessons tab."""
    runs_root = runs_root or os.path.abspath(os.path.join(os.path.dirname(__file__), "../../runs"))
    return read_recent_lessons(site_slug, limit=10000, runs_root=runs_root)


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_") or "site"
