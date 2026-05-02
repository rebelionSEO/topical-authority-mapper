"""Recommendation agent — Anthropic tool-use loop with self-critique + learning loop.

Orchestration:
  1. Build system prompt: base role + injected lessons + guardrails
  2. Send user question
  3. Loop: get model response → execute tool calls → send results back
  4. Terminate when `final_recommend` is called OR safety cap is hit
  5. Self-critique pass: model reviews its own work, can call `note_lesson`
  6. Persist trace + summary to memory

Run via:
    python -m src.agent.recommend "What should we publish next month?"
    python -m src.agent.recommend --site Wynter "What should we refresh first?"
"""

import argparse
import json
import logging
import os
import sys
import time
from typing import Optional

from src.agent import lessons as lessons_mod
from src.agent import memory as mem_mod
from src.agent import tools as tools_mod
from src.config import load_site_config

logger = logging.getLogger(__name__)


DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_TOOL_CALLS = 15
MAX_OUTPUT_TOKENS = 4000


SYSTEM_BASE = """You are a senior B2B SaaS content strategist + technical SEO auditor.
Your job is to answer the operator's question by gathering evidence from the audit
artifacts using your tools, then emitting a structured final recommendation.

Operating principles:
- Use tools to gather evidence; NEVER fabricate data, URLs, or numbers.
- Cite the data row each recommendation came from (e.g. "content_ideas.csv P1 row 3").
- If you're about to recommend a new piece, ALWAYS check_cannibalization() first AND
  search_site_content() to see if the topic is already partially covered.
- If a topic has cannibalization veto_recommend_new=true, do NOT recommend writing
  more content on it. Recommend refresh or consolidation instead.
- For refresh recommendations, use get_stale_pages with min_age_days >= 180.
- Keep your reasoning tight — each tool call should serve a specific purpose.
- Stop and call final_recommend when you have enough evidence (usually 4-8 tool calls).

Output style:
- Be specific. Generic advice ("write more about X") fails. Cite titles, URLs, scores.
- Surface contradictions in the data instead of hiding them.
- If the data is insufficient to answer, say so plainly.

After final_recommend, you'll get one self-critique turn — review your work and call
note_lesson() once per insight worth remembering for the next run."""


SELF_CRITIQUE_PROMPT = """Now review the recommendations you just made. Were any
based on shaky assumptions? Did any tool return surprising data you didn't fully
account for? Are there patterns in your reasoning you should remember next time?

If yes — call note_lesson() once per lesson, with category + the mistake + a concrete
behavior to follow next time. Be specific (vague lessons are useless).

If no lessons to capture, respond with the single word: DONE."""


def _build_system_prompt(site_slug: str) -> str:
    base = SYSTEM_BASE
    lessons_block = lessons_mod.lessons_for_prompt(site_slug, limit=30)
    if lessons_block:
        return f"{base}\n\n{lessons_block}\n\nApply these lessons consistently."
    return base


def _client():
    try:
        from src.llm_advisor import _client as _shared_client
        return _shared_client()
    except Exception as e:
        logger.error("Could not load Anthropic client: %s", e)
        return None


def _truncate(obj, max_chars: int = 1200) -> str:
    """Truncate JSON serialization for trace storage."""
    try:
        s = json.dumps(obj, default=str)
    except Exception:
        s = str(obj)
    return s if len(s) <= max_chars else s[:max_chars] + "…"


def run_agent(
    question: str,
    site_slug: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    max_tool_calls: int = MAX_TOOL_CALLS,
    on_event=None,
) -> dict:
    """Run the agent on one question. Returns the final recommendation + trace summary."""
    # Resolve site
    if not site_slug:
        cfg = load_site_config()
        site_slug = cfg.name if cfg else "site"

    # Reset per-run caches so fresh CSVs are read
    tools_mod.reset_cache()

    client = _client()
    if not client:
        return {"error": "Anthropic client unavailable. Set ANTHROPIC_API_KEY.", "actions": []}

    run = mem_mod.new_run(site_slug=site_slug, question=question, model=model)
    system_prompt = _build_system_prompt(site_slug)

    if on_event:
        on_event({"type": "start", "site": site_slug, "model": model, "question": question})

    messages = [{"role": "user", "content": question}]
    final = None
    tool_call_count = 0
    in_self_critique = False

    try:
        while True:
            response = client.messages.create(
                model=model,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=system_prompt,
                tools=tools_mod.TOOLS,
                messages=messages,
            )

            # Persist assistant turn
            messages.append({"role": "assistant", "content": response.content})

            tool_uses = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
            text_blocks = [b for b in response.content if getattr(b, "type", None) == "text"]

            if on_event:
                for tb in text_blocks:
                    on_event({"type": "thinking", "text": tb.text})

            # No tool calls + we already have final = end. Otherwise check self-critique state.
            if not tool_uses:
                if final and not in_self_critique:
                    # Model decided not to self-critique. Skip directly to end.
                    break
                if in_self_critique:
                    # Self-critique done (model said DONE or similar)
                    break
                # No tools + no final yet — model is stuck or chose not to use tools. End.
                break

            # Execute tool calls
            tool_results_block = []
            for tu in tool_uses:
                if tool_call_count >= max_tool_calls and not in_self_critique:
                    # Hit safety cap — force the agent to wrap up
                    tool_results_block.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": json.dumps({"error": f"tool call cap reached ({max_tool_calls}); call final_recommend now"}),
                        "is_error": True,
                    })
                    continue

                args = tu.input or {}
                if on_event:
                    on_event({"type": "tool_call", "name": tu.name, "arguments": args})

                result = tools_mod.call_tool(tu.name, args, site_slug=site_slug)

                # Track this tool call
                run.tool_calls.append({
                    "name": tu.name, "arguments": args, "result_preview": _truncate(result, 800),
                })
                tool_call_count += 1

                if on_event:
                    on_event({"type": "tool_result", "name": tu.name, "result": result})

                # Check for terminal tool
                if tu.name == "final_recommend":
                    final = result
                    run.final_recommendation = {
                        "summary": result.get("summary", ""),
                        "actions": result.get("actions", []),
                        "confidence": result.get("confidence", ""),
                        "risks": result.get("risks", []),
                    }
                if tu.name == "note_lesson" and in_self_critique and result.get("saved"):
                    run.self_critique_lessons_captured += 1

                tool_results_block.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps(result, default=str),
                })

            messages.append({"role": "user", "content": tool_results_block})

            # If the agent just called final_recommend, switch to self-critique mode
            if final and not in_self_critique:
                in_self_critique = True
                messages.append({"role": "user", "content": SELF_CRITIQUE_PROMPT})
                if on_event:
                    on_event({"type": "phase", "phase": "self-critique"})

        run.finished_at = time.time()
        trace_path = mem_mod.persist_run(run)
        if on_event:
            on_event({"type": "finished", "trace_path": trace_path,
                      "tool_calls": tool_call_count,
                      "lessons_captured": run.self_critique_lessons_captured})

        return {
            "summary": (final or {}).get("summary", "(no final recommendation produced)"),
            "actions": (final or {}).get("actions", []),
            "confidence": (final or {}).get("confidence", ""),
            "risks": (final or {}).get("risks", []),
            "tool_calls": tool_call_count,
            "lessons_captured": run.self_critique_lessons_captured,
            "trace_path": trace_path,
            "duration_sec": round(run.finished_at - run.started_at, 1),
        }

    except Exception as e:
        logger.exception("Agent run failed")
        run.error = str(e)
        run.finished_at = time.time()
        mem_mod.persist_run(run)
        return {"error": str(e), "actions": [], "tool_calls": tool_call_count}


def _print_event(evt: dict):
    t = evt.get("type")
    if t == "start":
        print(f"\n→ Agent started · site={evt['site']} · model={evt['model']}")
        print(f"  Question: {evt['question']}\n")
    elif t == "thinking":
        text = evt.get("text", "").strip()
        if text:
            print(f"  [reasoning] {text[:200]}{'…' if len(text) > 200 else ''}")
    elif t == "tool_call":
        args_preview = json.dumps(evt.get("arguments", {}))[:120]
        print(f"  → {evt['name']}({args_preview})")
    elif t == "tool_result":
        result = evt.get("result", {})
        if isinstance(result, dict):
            preview = json.dumps(result, default=str)[:160]
        else:
            preview = str(result)[:160]
        print(f"      ← {preview}")
    elif t == "phase":
        print(f"\n[phase: {evt['phase']}]")
    elif t == "finished":
        print(f"\n✓ Done · {evt['tool_calls']} tool calls · {evt['lessons_captured']} lessons captured")
        print(f"  Trace: {evt['trace_path']}")


def main():
    parser = argparse.ArgumentParser(description="Run the recommendation agent.")
    parser.add_argument("question", nargs="?", help="The question to ask. If omitted, reads from stdin.")
    parser.add_argument("--site", help="Override the site slug (defaults to cached SiteConfig.name).")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Model to use (default {DEFAULT_MODEL}).")
    parser.add_argument("--max-tool-calls", type=int, default=MAX_TOOL_CALLS)
    parser.add_argument("--quiet", action="store_true", help="Don't stream events; print only final result.")
    parser.add_argument("--json", action="store_true", help="Output as JSON.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    question = args.question or sys.stdin.read().strip()
    if not question:
        parser.error("No question provided.")

    on_event = None if args.quiet else _print_event
    result = run_agent(
        question=question, site_slug=args.site, model=args.model,
        max_tool_calls=args.max_tool_calls, on_event=on_event,
    )

    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return

    print()
    print("=" * 60)
    print("FINAL RECOMMENDATION")
    print("=" * 60)
    if result.get("error"):
        print(f"Error: {result['error']}")
        return
    print(f"\n{result.get('summary', '(none)')}\n")
    print(f"Confidence: {result.get('confidence', 'unknown')}")
    print()
    for i, a in enumerate(result.get("actions", []), 1):
        print(f"{i}. [{a.get('action', '?').upper()}] {a.get('title', '')}")
        print(f"     Reason: {a.get('reason', '')}")
        if a.get("sources"):
            print(f"     Sources: {', '.join(a['sources'])}")
        print()
    if result.get("risks"):
        print("Risks / caveats:")
        for r in result["risks"]:
            print(f"  - {r}")


if __name__ == "__main__":
    main()
