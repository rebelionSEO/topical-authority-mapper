"""Agent tool registry.

10 typed Python functions exposed to the agent via the Anthropic tool-use API.
Each tool has:
  - name + description (the LLM uses these to decide when to call)
  - input_schema (JSON Schema — Anthropic validates before invocation)
  - a Python implementation that returns a JSON-serializable result

The terminal tool is `final_recommend` — when the agent calls it, the
orchestration loop ends and emits the structured recommendation to the operator.
The other terminal-ish tool is `note_lesson`, which never ends the loop but
appends to the learning ledger.
"""

import logging
import os
from typing import Optional

import pandas as pd

from src.agent import lessons as lessons_mod
from src.config import output_dir

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers — load CSVs once per agent run (cheap, in-memory cache)
# ---------------------------------------------------------------------------

_DATA_CACHE: dict = {}


def _load(name: str) -> pd.DataFrame:
    if name in _DATA_CACHE:
        return _DATA_CACHE[name]
    path = os.path.join(output_dir(), name)
    if not os.path.exists(path):
        df = pd.DataFrame()
    else:
        try:
            df = pd.read_csv(path)
        except Exception:
            df = pd.DataFrame()
    _DATA_CACHE[name] = df
    return df


def reset_cache():
    """Reset the CSV cache between runs."""
    _DATA_CACHE.clear()


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def get_content_ideas(
    priority: Optional[str] = None,
    intent: Optional[str] = None,
    audience: Optional[str] = None,
    limit: int = 10,
) -> dict:
    df = _load("content_ideas.csv")
    if df.empty:
        return {"matches": [], "note": "content_ideas.csv is empty (re-run with --competitor)"}
    out = df.copy()
    if priority:
        out = out[out["priority"].str.upper() == priority.upper()]
    if intent:
        out = out[out["intent"].str.lower() == intent.lower()]
    if audience:
        out = out[out["target_audience"].str.contains(audience, case=False, na=False)]
    out = out.head(limit)
    return {
        "matches": out[["priority", "title", "gap_topic", "content_type", "intent",
                         "target_audience", "est_word_count", "covered_by",
                         "spoke_cluster"]].fillna("").to_dict("records"),
        "total_matched": int(len(out)),
        "filters_applied": {"priority": priority, "intent": intent, "audience": audience, "limit": limit},
    }


def check_cannibalization(topic: str) -> dict:
    """Does this topic already have a cannibalization cluster on the site?
    Returns the matching cluster (with URL count + severity) or null."""
    df = _load("cannibalization.csv")
    if df.empty or not topic:
        return {"match": None, "note": "no cannibalization data" if df.empty else "empty topic"}
    needle = topic.lower()
    match = df[df["cluster_name"].str.lower().str.contains(needle, na=False)]
    if match.empty:
        # Also try keyword overlap via clusters.csv
        clusters = _load("clusters.csv")
        if not clusters.empty:
            kw_match = clusters[clusters["keywords"].str.lower().str.contains(needle, na=False)]
            if not kw_match.empty:
                cid = int(kw_match.iloc[0]["cluster_id"])
                cmatch = df[df["cluster_id"] == cid]
                if not cmatch.empty:
                    match = cmatch
    if match.empty:
        return {"match": None}
    row = match.iloc[0]
    return {
        "match": {
            "cluster_id": int(row["cluster_id"]),
            "cluster_name": row["cluster_name"],
            "url_count": int(row["url_count"]),
            "severity": "critical" if row["url_count"] >= 10 else "high" if row["url_count"] >= 6 else "moderate",
            "veto_recommend_new": int(row["url_count"]) >= 4,
        }
    }


def get_stale_pages(min_age_days: int = 180, limit: int = 10) -> dict:
    df = _load("content_freshness.csv")
    if df.empty:
        return {"matches": [], "note": "freshness data not available (no lastmod / no HTML scrape)"}
    stale = df[df["age_days"] >= min_age_days].sort_values("age_days", ascending=False).head(limit)
    return {
        "matches": stale[["url", "lastmod", "age_days", "freshness"]].to_dict("records"),
        "total_matched": int(len(stale)),
        "min_age_days": min_age_days,
    }


def search_site_content(query: str, k: int = 5) -> dict:
    """RAG: vector search across the site's content. Returns top-k chunks
    with URL + first 300 chars + similarity score."""
    if not query:
        return {"matches": [], "note": "empty query"}
    try:
        from src.retrieval import get_index
        idx = get_index()
        if idx is None:
            return {"matches": [], "note": "retrieval index unavailable"}
        chunks = idx.search_by_text(query, k=k)
        return {
            "matches": [
                {"url": c.url, "snippet": c.short(300), "similarity": round(c.score, 3),
                 "cluster_id": c.cluster_id}
                for c in chunks
            ],
            "query": query,
            "k": k,
        }
    except Exception as e:
        return {"matches": [], "note": f"retrieval failed: {e}"}


def get_brand_voice_score(url: str) -> dict:
    df = _load("brand_voice_scores.csv")
    if df.empty:
        return {"match": None, "note": "brand voice data unavailable"}
    match = df[df["url"].str.contains(url, case=False, na=False)]
    if match.empty:
        return {"match": None}
    row = match.iloc[0]
    return {
        "match": {
            "url": row["url"],
            "brand_score": int(row["brand_score"]),
            "rating": row["rating"],
            "tone_matches": row.get("tone_matches", ""),
            "violations": row.get("violations", ""),
            "recommend_review": int(row["brand_score"]) < 50,
        }
    }


def get_competitor_gaps(competitor: Optional[str] = None, limit: int = 15) -> dict:
    out = output_dir()
    if not os.path.isdir(out):
        return {"matches": [], "note": "no output dir"}
    targets = []
    if competitor:
        targets = [f"competitor_gap_{competitor.lower().replace(' ', '_')}.csv"]
    else:
        targets = [f for f in os.listdir(out) if f.startswith("competitor_gap_") and f.endswith(".csv")]
    rows = []
    for fname in targets:
        path = os.path.join(out, fname)
        if not os.path.exists(path):
            continue
        try:
            df = pd.read_csv(path)
        except Exception:
            continue
        if "status" not in df.columns:
            continue
        gaps = df[df["status"].str.contains("GAP", case=False, na=False)].head(limit)
        for _, r in gaps.iterrows():
            rows.append({"competitor": r.get("competitor", fname), "gap_topic": r.get("keyword", "")})
    return {"matches": rows[:limit], "total_competitors": len(targets)}


def get_health_subscores() -> dict:
    import json as _json
    path = os.path.join(output_dir(), "site_health.json")
    if not os.path.exists(path):
        return {"composite": None, "note": "site_health.json missing"}
    try:
        with open(path) as f:
            return _json.load(f)
    except Exception as e:
        return {"composite": None, "note": f"could not read site_health.json: {e}"}


def get_internal_link_targets(topic: str, k: int = 5) -> dict:
    """Find existing pages that should internally link TO a new piece on `topic`.
    Uses RAG to find semantically related existing content."""
    return search_site_content(topic, k=k)


def note_lesson(category: str, mistake: str, lesson: str, _site_slug: str = "") -> dict:
    """Append a learning to the agent_lessons.md ledger.
    Called by the agent's self-critique pass at end-of-run. NEVER terminates the loop."""
    if not _site_slug:
        return {"saved": False, "error": "site_slug not provided"}
    try:
        path = lessons_mod.append_lesson(
            site_slug=_site_slug,
            category=category,
            mistake=mistake,
            lesson=lesson,
            source="self-critique",
        )
        return {"saved": True, "path": path}
    except Exception as e:
        return {"saved": False, "error": str(e)}


def final_recommend(
    summary: str,
    actions: list,
    confidence: str = "medium",
    risks: Optional[list] = None,
) -> dict:
    """Terminal tool — emits the structured recommendation and ends the agent loop.

    actions: list of {action: 'write'|'refresh'|'skip', title, reason, sources}
    """
    return {
        "summary": summary,
        "actions": actions or [],
        "confidence": confidence,
        "risks": risks or [],
        "_terminal": True,
    }


# ---------------------------------------------------------------------------
# Tool registry — what gets passed to the Anthropic API
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "get_content_ideas",
        "description": "Pull rows from the content ideas backlog. Filter by priority (P1/P2/P3), intent (comparison/howto/definition/framework/examples/metrics/checklist/guide), or audience (substring match).",
        "input_schema": {
            "type": "object",
            "properties": {
                "priority": {"type": "string", "description": "P1, P2, or P3 (optional)"},
                "intent": {"type": "string", "description": "intent label (optional)"},
                "audience": {"type": "string", "description": "audience substring to match (optional)"},
                "limit": {"type": "integer", "default": 10, "description": "max rows to return"},
            },
        },
    },
    {
        "name": "check_cannibalization",
        "description": "Check whether a topic already has a cannibalization cluster on the site. Returns the cluster + a `veto_recommend_new` flag — if true, the agent should NOT recommend writing more content on this topic.",
        "input_schema": {
            "type": "object",
            "properties": {"topic": {"type": "string"}},
            "required": ["topic"],
        },
    },
    {
        "name": "get_stale_pages",
        "description": "Get pages older than min_age_days, sorted by age desc. Use for refresh recommendations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "min_age_days": {"type": "integer", "default": 180},
                "limit": {"type": "integer", "default": 10},
            },
        },
    },
    {
        "name": "search_site_content",
        "description": "RAG vector search across the site's existing content. Use to check whether a topic is already covered before recommending new content. Returns top-k matching chunks with similarity scores.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "k": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_brand_voice_score",
        "description": "Get a per-URL brand voice score. Use to flag pages for editor review (score < 50) or filter content authors.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "get_competitor_gaps",
        "description": "Pull competitor gap topics (topics competitors cover that the target site doesn't). Optionally filter by competitor name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "competitor": {"type": "string", "description": "(optional) competitor name"},
                "limit": {"type": "integer", "default": 15},
            },
        },
    },
    {
        "name": "get_health_subscores",
        "description": "Get the current site health composite + 5 subscores (coverage, cannibalization, freshness, brand, competitive). Use to ground recommendations in current state.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_internal_link_targets",
        "description": "Find existing pages that should internally link TO a new piece on the given topic. Uses RAG to find semantically related content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "k": {"type": "integer", "default": 5},
            },
            "required": ["topic"],
        },
    },
    {
        "name": "note_lesson",
        "description": "During the end-of-run self-critique pass, call this to record a lesson the agent should remember next time. Categories: cannibalization, audience, freshness, refresh, citation, scope. Be SPECIFIC — vague lessons aren't useful.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "mistake": {"type": "string", "description": "What went wrong this run"},
                "lesson": {"type": "string", "description": "Concrete behavior to follow next time"},
            },
            "required": ["category", "mistake", "lesson"],
        },
    },
    {
        "name": "final_recommend",
        "description": "TERMINAL TOOL. Emit the final recommendation and end the agent loop. Use when you've gathered enough evidence. Each action must cite the data row(s) it came from.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "1-2 sentence executive summary"},
                "actions": {
                    "type": "array",
                    "description": "List of recommended actions",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ["write", "refresh", "skip", "investigate"]},
                            "title": {"type": "string"},
                            "reason": {"type": "string", "description": "Why this action — cite data sources"},
                            "sources": {"type": "array", "items": {"type": "string"}, "description": "Data rows cited (e.g., 'content_ideas.csv:P1 row 3', 'cannibalization.csv:cluster 5')"},
                        },
                        "required": ["action", "title", "reason"],
                    },
                },
                "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                "risks": {"type": "array", "items": {"type": "string"}, "description": "Caveats or things the operator should double-check"},
            },
            "required": ["summary", "actions"],
        },
    },
]


# Map name -> Python implementation
HANDLERS = {
    "get_content_ideas": get_content_ideas,
    "check_cannibalization": check_cannibalization,
    "get_stale_pages": get_stale_pages,
    "search_site_content": search_site_content,
    "get_brand_voice_score": get_brand_voice_score,
    "get_competitor_gaps": get_competitor_gaps,
    "get_health_subscores": get_health_subscores,
    "get_internal_link_targets": get_internal_link_targets,
    "note_lesson": note_lesson,
    "final_recommend": final_recommend,
}


def call_tool(name: str, arguments: dict, site_slug: str = "") -> dict:
    """Invoke a tool by name. Special-cases note_lesson to inject site_slug."""
    fn = HANDLERS.get(name)
    if fn is None:
        return {"error": f"unknown tool: {name}"}
    try:
        # note_lesson needs site context
        if name == "note_lesson":
            return fn(_site_slug=site_slug, **arguments)
        return fn(**arguments)
    except TypeError as e:
        return {"error": f"bad arguments for {name}: {e}"}
    except Exception as e:
        logger.exception("Tool call failed: %s", name)
        return {"error": f"tool execution failed: {e}"}
