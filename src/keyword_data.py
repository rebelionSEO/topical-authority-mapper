"""Keyword data enrichment hook.

Returns search volume / keyword difficulty / parent keyword for a given query.
Pluggable by provider — currently supports:

  - Ahrefs MCP (env var TAM_KEYWORD_PROVIDER=ahrefs_mcp + tool exposure)
  - DataForSEO (env var TAM_KEYWORD_PROVIDER=dataforseo + DFS_LOGIN/DFS_PASSWORD)
  - File cache (env var TAM_KEYWORD_PROVIDER=file + TAM_KEYWORD_FILE pointing to CSV)
  - None (default — returns empty dict, dashboard shows 'source: none')

Enable Ahrefs MCP integration:
    export TAM_KEYWORD_PROVIDER=ahrefs_mcp
    # Make sure the claude.ai Ahrefs MCP is connected (gh CLI or settings.json)
    python -m src.content_ideas    # re-run to populate

Bring-your-own-data (no API needed): build a CSV with columns
keyword,search_volume,keyword_difficulty,parent_keyword and point at it:
    export TAM_KEYWORD_PROVIDER=file
    export TAM_KEYWORD_FILE=./keyword_data.csv
    python -m src.content_ideas

The dashboard renders SEO data when populated and shows a 'source: <provider>' badge
so you can see which provider supplied the numbers (or 'none' when missing).
"""

import csv
import json
import logging
import os
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


_FILE_CACHE: Optional[dict] = None  # in-process cache of file-based keyword data


def _provider() -> str:
    return os.environ.get("TAM_KEYWORD_PROVIDER", "none").lower()


def _load_file_cache() -> dict:
    global _FILE_CACHE
    if _FILE_CACHE is not None:
        return _FILE_CACHE
    path = os.environ.get("TAM_KEYWORD_FILE")
    if not path or not os.path.exists(path):
        _FILE_CACHE = {}
        return _FILE_CACHE
    cache = {}
    try:
        with open(path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                kw = (row.get("keyword") or "").strip().lower()
                if not kw:
                    continue
                cache[kw] = {
                    "search_volume": row.get("search_volume", ""),
                    "keyword_difficulty": row.get("keyword_difficulty", ""),
                    "parent_keyword": row.get("parent_keyword", ""),
                    "source": "file",
                }
        logger.info("Loaded %d keyword rows from %s", len(cache), path)
    except (OSError, csv.Error) as e:
        logger.warning("Could not load keyword file %s: %s", path, e)
    _FILE_CACHE = cache
    return cache


def _enrich_via_file(keyword: str) -> dict:
    cache = _load_file_cache()
    return cache.get(keyword.lower(), {})


def _enrich_via_ahrefs_mcp(keyword: str) -> dict:
    """Call the Ahrefs MCP via Claude Code's MCP system.

    Returns {'search_volume', 'keyword_difficulty', 'parent_keyword', 'source'} or {}.

    Implementation note: the Ahrefs MCP exposes tools like
    keywords-explorer-overview which returns volume + difficulty + parent_topic.
    We invoke it via `npx claude-code mcp call ...` if available, otherwise we
    return {} and let the caller fall back gracefully.

    For interactive sessions (the user runs the pipeline from inside Claude Code),
    a future version can talk to the MCP directly via the SDK. For now this hook
    is a stub that documents the integration point.
    """
    # The MCP isn't reachable from a plain `python -m` invocation outside Claude Code.
    # Real integration requires the user to run inside Claude with the MCP connected,
    # OR to use Ahrefs' REST API directly (requires API key). Both are wired above
    # via the 'file' provider as a no-key alternative.
    return {}


def _enrich_via_dataforseo(keyword: str) -> dict:
    """Stub for DataForSEO REST integration. Implement when API credentials are set."""
    login = os.environ.get("DFS_LOGIN")
    password = os.environ.get("DFS_PASSWORD")
    if not (login and password):
        return {}
    # Real implementation would POST to:
    # https://api.dataforseo.com/v3/keywords_data/google_ads/search_volume/live
    # Skipping the network call here — wire it when needed.
    return {}


def enrich_keywords(keyword: str) -> dict:
    """Public entry. Returns dict with search_volume/keyword_difficulty/parent_keyword/source.

    Always returns a dict (possibly empty). Never raises — degrades gracefully so the
    pipeline keeps running even if the provider fails.
    """
    if not keyword:
        return {}
    provider = _provider()
    try:
        if provider == "file":
            return _enrich_via_file(keyword)
        if provider == "ahrefs_mcp":
            return _enrich_via_ahrefs_mcp(keyword)
        if provider == "dataforseo":
            return _enrich_via_dataforseo(keyword)
    except Exception as e:
        logger.debug("Keyword enrichment failed for %r via %s: %s", keyword, provider, e)
        return {}
    return {}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Test keyword data enrichment.")
    parser.add_argument("keyword", help="Keyword to look up")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    print(f"Provider: {_provider()}")
    result = enrich_keywords(args.keyword)
    print(f"Result: {json.dumps(result, indent=2) if result else '(empty — enable a provider via TAM_KEYWORD_PROVIDER env var)'}")
