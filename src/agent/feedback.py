"""Operator feedback CLI — append a lesson to the agent_lessons.md ledger.

The operator runs this AFTER reviewing an agent recommendation, to teach the
agent what to do differently next time.

Examples:
    # Reject a specific recommendation, with reason
    python -m src.agent.feedback --reject "What is PQL?" \\
        --reason "already covered at /post/pql-guide"

    # Generic correction
    python -m src.agent.feedback \\
        --category cannibalization \\
        --mistake "Recommended adding to a topic with 12 existing URLs" \\
        --lesson "Always veto new content when cannibalization >= 8 URLs"
"""

import argparse
import logging
import sys

from src.agent import lessons as lessons_mod
from src.config import load_site_config

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Add a lesson to the agent's learning ledger.")
    parser.add_argument("--site", help="Override site slug (defaults to cached SiteConfig.name)")

    # Two modes: explicit lesson, or 'reject + reason' shortcut
    parser.add_argument("--reject", help="A recommendation title that the operator rejects")
    parser.add_argument("--reason", help="Why the rejection (used to derive the lesson)")

    parser.add_argument("--category", default="general", help="Lesson category (cannibalization, audience, freshness, refresh, scope)")
    parser.add_argument("--mistake", help="What the agent got wrong")
    parser.add_argument("--lesson", help="Concrete behavior to follow next time")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    site = args.site
    if not site:
        cfg = load_site_config()
        site = cfg.name if cfg else "site"

    # Derive mistake + lesson from the --reject + --reason shortcut, if used
    if args.reject:
        if not args.reason:
            parser.error("--reject requires --reason")
        mistake = f"Recommended '{args.reject}' but operator rejected it."
        lesson = f"Reason: {args.reason}. Apply this lens before recommending similar items next run."
        category = args.category or "operator-rejection"
    else:
        if not (args.mistake and args.lesson):
            parser.error("Either use --reject + --reason, OR --mistake + --lesson")
        mistake = args.mistake
        lesson = args.lesson
        category = args.category

    path = lessons_mod.append_lesson(
        site_slug=site, category=category,
        mistake=mistake, lesson=lesson,
        source="operator-feedback",
    )
    print(f"✓ Appended lesson → {path}")


if __name__ == "__main__":
    main()
