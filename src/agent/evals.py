"""Evals — 3 golden agent questions + per-tool unit tests.

Run all:
    python -m src.agent.evals

Run only the cheap (no LLM) tool unit tests:
    python -m src.agent.evals --tools-only

The 3 golden agent evals cost ~$1 total to run (Sonnet 4.6 × 3 questions).
"""

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass

from src.agent import recommend as agent
from src.agent import tools as tools_mod

logger = logging.getLogger(__name__)


@dataclass
class EvalResult:
    name: str
    passed: bool
    detail: str = ""


# ---------------------------------------------------------------------------
# Per-tool unit tests (no LLM cost — pure data + retrieval checks)
# ---------------------------------------------------------------------------

def test_get_content_ideas() -> EvalResult:
    res = tools_mod.get_content_ideas(limit=3)
    if "matches" not in res:
        return EvalResult("get_content_ideas", False, "no 'matches' key")
    return EvalResult("get_content_ideas", True, f"returned {len(res['matches'])} matches")


def test_check_cannibalization() -> EvalResult:
    res = tools_mod.check_cannibalization("marketing")
    if "match" not in res:
        return EvalResult("check_cannibalization", False, "no 'match' key")
    return EvalResult("check_cannibalization", True, f"match: {bool(res.get('match'))}")


def test_get_stale_pages() -> EvalResult:
    res = tools_mod.get_stale_pages(min_age_days=180, limit=3)
    if "matches" not in res:
        return EvalResult("get_stale_pages", False, "no 'matches' key")
    return EvalResult("get_stale_pages", True, f"returned {len(res['matches'])} stale pages")


def test_search_site_content() -> EvalResult:
    res = tools_mod.search_site_content("brand voice", k=3)
    if "matches" not in res:
        return EvalResult("search_site_content", False, "no 'matches' key")
    return EvalResult("search_site_content", True, f"returned {len(res['matches'])} chunks")


def test_get_health_subscores() -> EvalResult:
    res = tools_mod.get_health_subscores()
    has_composite = "composite" in res
    return EvalResult("get_health_subscores", has_composite, f"composite: {res.get('composite')}")


def test_get_competitor_gaps() -> EvalResult:
    res = tools_mod.get_competitor_gaps(limit=3)
    if "matches" not in res:
        return EvalResult("get_competitor_gaps", False, "no 'matches' key")
    return EvalResult("get_competitor_gaps", True, f"returned {len(res['matches'])} gaps")


def test_final_recommend_shape() -> EvalResult:
    res = tools_mod.final_recommend(
        summary="test", actions=[{"action": "write", "title": "t", "reason": "r"}], confidence="medium",
    )
    if not res.get("_terminal"):
        return EvalResult("final_recommend", False, "missing _terminal flag")
    return EvalResult("final_recommend", True, "shape OK")


TOOL_TESTS = [
    test_get_content_ideas,
    test_check_cannibalization,
    test_get_stale_pages,
    test_search_site_content,
    test_get_health_subscores,
    test_get_competitor_gaps,
    test_final_recommend_shape,
]


# ---------------------------------------------------------------------------
# Golden agent evals (use the LLM)
# ---------------------------------------------------------------------------

GOLDEN_QUESTIONS = [
    {
        "name": "publish_next_month",
        "question": "What should we publish next month? Recommend 3-5 specific actions.",
        "checks": [
            ("has_actions", lambda r: len(r.get("actions", [])) >= 3,
             "should produce at least 3 actions"),
            ("actions_have_sources", lambda r: all(
                a.get("sources") or a.get("reason") for a in r.get("actions", [])
            ), "every action must cite a source"),
        ],
    },
    {
        "name": "what_to_refresh",
        "question": "Which existing pages should we refresh first?",
        "checks": [
            ("mentions_refresh", lambda r: any(
                a.get("action") == "refresh" for a in r.get("actions", [])
            ), "at least one action should be 'refresh'"),
        ],
    },
    {
        "name": "biggest_content_risk",
        "question": "What's our biggest content risk right now?",
        "checks": [
            ("has_summary", lambda r: bool(r.get("summary")),
             "must produce a non-empty summary"),
        ],
    },
]


def run_golden_evals(site_slug: str = None) -> list[EvalResult]:
    out = []
    for ev in GOLDEN_QUESTIONS:
        print(f"\n→ Eval: {ev['name']}")
        print(f"  Q: {ev['question']}")
        try:
            result = agent.run_agent(question=ev["question"], site_slug=site_slug, on_event=None)
        except Exception as e:
            out.append(EvalResult(ev["name"], False, f"exception: {e}"))
            continue
        if result.get("error"):
            out.append(EvalResult(ev["name"], False, f"error: {result['error']}"))
            continue
        for check_name, check_fn, check_desc in ev["checks"]:
            try:
                ok = bool(check_fn(result))
            except Exception as e:
                ok = False
                check_desc = f"{check_desc} (raised: {e})"
            out.append(EvalResult(f"{ev['name']}::{check_name}", ok, check_desc))
    return out


def main():
    parser = argparse.ArgumentParser(description="Run agent evals.")
    parser.add_argument("--tools-only", action="store_true", help="Skip the LLM-based golden evals (no cost)")
    parser.add_argument("--site", help="Site slug for golden evals")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    print("=" * 60)
    print("AGENT EVAL SUITE")
    print("=" * 60)

    print("\n--- Tool unit tests ---")
    tool_results = [t() for t in TOOL_TESTS]
    for r in tool_results:
        marker = "✓" if r.passed else "✗"
        print(f"  {marker} {r.name}  ({r.detail})")
    n_pass = sum(r.passed for r in tool_results)
    print(f"  {n_pass}/{len(tool_results)} tool tests passed")

    if args.tools_only:
        return 0 if n_pass == len(tool_results) else 1

    print("\n--- Golden agent evals (uses LLM, ~$1 total) ---")
    golden_results = run_golden_evals(site_slug=args.site)
    for r in golden_results:
        marker = "✓" if r.passed else "✗"
        print(f"  {marker} {r.name}  ({r.detail})")
    g_pass = sum(r.passed for r in golden_results)
    print(f"  {g_pass}/{len(golden_results)} golden checks passed")

    total_pass = n_pass + g_pass
    total = len(tool_results) + len(golden_results)
    print(f"\nTotal: {total_pass}/{total} passed")
    return 0 if total_pass == total else 1


if __name__ == "__main__":
    sys.exit(main())
