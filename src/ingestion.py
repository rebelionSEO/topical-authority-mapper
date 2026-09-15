"""Content extraction and chunking from URLs."""

import logging
import re
from typing import Optional
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser
from datetime import datetime, timezone
from bs4 import BeautifulSoup

import pandas as pd
import requests
import trafilatura
from src.crawl import create_session, fetch, normalize_url, read_sitemaps, USER_AGENT

from src.config import (
    BOILERPLATE_PHRASES,
    CHUNK_SIZE_WORDS,
    MAX_CHARS_PER_PAGE,
    MIN_WORDS_THRESHOLD,
    resolved_skip_patterns,
)

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": USER_AGENT}


def parse_sitemap(sitemap_url: str) -> list[str]:
    """
    Parse a sitemap XML and return all URLs.

    Handles both sitemap index files (pointing to child sitemaps)
    and regular sitemaps with <url> entries.
    """
    result = read_sitemaps([sitemap_url])
    from src.execution import note_stage
    note_stage("sitemap_discovery", "partial" if result.issues else "completed",
               urls=len(result.pages), documents=result.visited, issues=result.issues)
    return list(result.pages)


def should_skip_url(url: str) -> bool:
    """Check if URL matches patterns that should be skipped (default + per-site extras)."""
    url_lower = url.lower()
    return any(pattern in url_lower for pattern in resolved_skip_patterns())


def fetch_page(url: str, timeout: int = 15) -> Optional[str]:
    """Fetch raw HTML from a URL."""
    try:
        with create_session() as session:
            return fetch(session, url, timeout=timeout).text
    except (requests.RequestException, ValueError) as e:
        logger.warning("Failed to fetch %s: %s", url, e)
        return None


def extract_text(html: str) -> Optional[str]:
    """Extract main content text from HTML using trafilatura."""
    text = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=False,
        no_fallback=False,
    )
    return text


def clean_text(text: str) -> str:
    """Remove boilerplate, extra whitespace, and navigation artifacts."""
    text_lower = text.lower()
    for phrase in BOILERPLATE_PHRASES:
        if phrase in text_lower:
            # Remove lines containing boilerplate
            lines = text.split("\n")
            lines = [l for l in lines if phrase not in l.lower()]
            text = "\n".join(lines)

    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_thin_content(text: str) -> bool:
    """Check if page has too little meaningful content."""
    word_count = len(text.split())
    return word_count < MIN_WORDS_THRESHOLD


def truncate_text(text: str) -> str:
    """Truncate text to MAX_CHARS_PER_PAGE."""
    if len(text) > MAX_CHARS_PER_PAGE:
        text = text[:MAX_CHARS_PER_PAGE]
    return text


def chunk_text(text: str, url: str) -> list[dict]:
    """Split text into chunks of ~CHUNK_SIZE_WORDS words."""
    words = text.split()
    chunks = []
    chunk_id = 0

    for i in range(0, len(words), CHUNK_SIZE_WORDS):
        chunk_words = words[i : i + CHUNK_SIZE_WORDS]
        if len(chunk_words) < 50:  # skip very small trailing chunks
            if chunks:
                # Append to last chunk instead
                chunks[-1]["chunk_text"] += " " + " ".join(chunk_words)
                continue
        chunks.append({
            "url": url,
            "chunk_id": chunk_id,
            "chunk_text": " ".join(chunk_words),
        })
        chunk_id += 1

    return chunks


def _ingest_urls(urls: list[str], session) -> tuple[pd.DataFrame, list[str]]:
    """
    Main ingestion pipeline.

    Returns:
        - DataFrame with columns: url, chunk_id, chunk_text
        - List of skipped/failed URLs with reasons
    """
    all_chunks = []
    skipped = []
    records = []
    seen = set()
    fetched = set()
    robots = {}

    def allowed(url):
        from urllib.parse import urlsplit
        parsed = urlsplit(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in robots:
            parser = RobotFileParser(origin + "/robots.txt")
            try:
                response = fetch(session, parser.url)
                parser.parse(response.text.splitlines())
            except requests.HTTPError as exc:
                code = exc.response.status_code if exc.response is not None else 0
                parser.parse([] if code in (404, 410) else ["User-agent: *", "Disallow: /"])
            except (requests.RequestException, ValueError):
                parser.parse(["User-agent: *", "Disallow: /"])
            robots[origin] = parser
        return robots[origin].can_fetch(USER_AGENT, url)

    for raw_url in urls:
        url = normalize_url(raw_url)
        record = {"requested_url": raw_url, "url": url, "final_url": "", "status_code": None,
                  "canonical": "", "title": "", "h1": "", "robots": "", "indexability": "unknown",
                  "outcome": "skipped", "reason": "", "word_count": 0,
                  "fetched_at": datetime.now(timezone.utc).isoformat()}
        records.append(record)
        if not url:
            record["reason"] = "invalid_url"
            skipped.append(f"{raw_url} | Skipped: invalid HTTP(S) URL")
            continue
        if url in seen:
            record["reason"] = "duplicate_url"
            skipped.append(f"{url} | Skipped: duplicate URL")
            continue
        seen.add(url)

        # Check skip patterns
        if should_skip_url(url):
            record["reason"] = "skip_pattern"
            skipped.append(f"{url} | Skipped: matches skip pattern (legal/nav page)")
            logger.info("Skipping URL (pattern match): %s", url)
            continue

        # Fetch
        if not allowed(url):
            record.update(reason="robots_disallowed_or_unavailable", indexability="unknown")
            skipped.append(f"{url} | Skipped: robots disallowed or unavailable")
            continue
        try:
            response = fetch(session, url, timeout=15)
            final_url = normalize_url(response.url)
            record.update(final_url=final_url, status_code=response.status_code)
            if "html" not in response.headers.get("Content-Type", "text/html").lower():
                record["reason"] = "non_html"
                skipped.append(f"{url} | Skipped: non-HTML response")
                continue
            html = response.text
        except (requests.RequestException, ValueError) as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            record.update(status_code=status, outcome="failed", reason=str(exc))
            skipped.append(f"{url} | Failed: {exc}")
            continue
        soup = BeautifulSoup(html, "html.parser")
        canonical = soup.find("link", rel=lambda value: value and "canonical" in value)
        canonical_url = normalize_url(urljoin(final_url, canonical.get("href", ""))) if canonical else ""
        directives = [response.headers.get("X-Robots-Tag", "")]
        directives.extend(tag.get("content", "") for tag in soup.find_all("meta")
                          if tag.get("name", "").lower() in ("robots", "googlebot"))
        directive_text = ", ".join(directives).lower()
        record.update(canonical=canonical_url, robots=directive_text,
                      title=soup.title.get_text(" ", strip=True) if soup.title else "",
                      h1=soup.h1.get_text(" ", strip=True) if soup.h1 else "")
        noindex = bool(re.search(r"\b(noindex|none)\b", directive_text))
        record["indexability"] = "noindex" if noindex else "canonicalized" if canonical_url and canonical_url != final_url else "eligible"
        if noindex:
            record["reason"] = "noindex"
            skipped.append(f"{url} | Skipped: noindex directive")
            continue
        if final_url in fetched:
            record["reason"] = "duplicate_redirect_target"
            skipped.append(f"{url} | Skipped: duplicate redirect target")
            continue
        fetched.add(final_url)

        # Extract
        text = extract_text(html)
        if not text:
            record.update(outcome="failed", reason="extraction_failed")
            skipped.append(f"{url} | Failed: no content extracted")
            continue

        # Clean
        text = clean_text(text)
        record["word_count"] = len(text.split())

        # Thin content check
        if is_thin_content(text):
            record["reason"] = "thin_content"
            skipped.append(f"{url} | Skipped: thin content ({len(text.split())} words)")
            logger.info("Skipping URL (thin content): %s", url)
            continue

        # Truncate
        text = truncate_text(text)

        # Chunk
        chunks = chunk_text(text, url)
        all_chunks.extend(chunks)
        record.update(outcome="analyzed", reason="")

    df = pd.DataFrame(all_chunks, columns=["url", "chunk_id", "chunk_text"])
    df.attrs["crawl_records"] = records
    logger.info("Ingested %d chunks from %d URLs (%d skipped)", len(df), len(urls) - len(skipped), len(skipped))
    return df, skipped


def ingest_urls(urls: list[str]) -> tuple[pd.DataFrame, list[str]]:
    """Extract eligible HTML pages and attach per-request crawl evidence."""
    with create_session() as session:
        return _ingest_urls(urls, session)
