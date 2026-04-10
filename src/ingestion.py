"""Content extraction and chunking from URLs."""

import logging
import re
import xml.etree.ElementTree as ET
from typing import Optional

import pandas as pd
import requests
import trafilatura

from src.config import (
    BOILERPLATE_PHRASES,
    CHUNK_SIZE_WORDS,
    MAX_CHARS_PER_PAGE,
    MIN_WORDS_THRESHOLD,
    SKIP_URL_PATTERNS,
)

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def parse_sitemap(sitemap_url: str) -> list[str]:
    """
    Parse a sitemap XML and return all URLs.

    Handles both sitemap index files (pointing to child sitemaps)
    and regular sitemaps with <url> entries.
    """
    urls = []
    logger.info("Fetching sitemap: %s", sitemap_url)

    try:
        resp = requests.get(sitemap_url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error("Failed to fetch sitemap %s: %s", sitemap_url, e)
        return urls

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        logger.error("Failed to parse sitemap XML: %s", e)
        return urls

    # Strip namespace for easier parsing
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    # Check if this is a sitemap index (contains <sitemap> entries)
    sitemap_entries = root.findall(f"{ns}sitemap")
    if sitemap_entries:
        logger.info("Sitemap index detected with %d child sitemaps", len(sitemap_entries))
        for entry in sitemap_entries:
            loc = entry.find(f"{ns}loc")
            if loc is not None and loc.text:
                child_urls = parse_sitemap(loc.text.strip())
                urls.extend(child_urls)
        return urls

    # Regular sitemap with <url> entries
    url_entries = root.findall(f"{ns}url")
    for entry in url_entries:
        loc = entry.find(f"{ns}loc")
        if loc is not None and loc.text:
            urls.append(loc.text.strip())

    logger.info("Parsed %d URLs from sitemap", len(urls))
    return urls


def should_skip_url(url: str) -> bool:
    """Check if URL matches patterns that should be skipped."""
    url_lower = url.lower()
    return any(pattern in url_lower for pattern in SKIP_URL_PATTERNS)


def fetch_page(url: str, timeout: int = 15) -> Optional[str]:
    """Fetch raw HTML from a URL."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
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


def ingest_urls(urls: list[str]) -> tuple[pd.DataFrame, list[str]]:
    """
    Main ingestion pipeline.

    Returns:
        - DataFrame with columns: url, chunk_id, chunk_text
        - List of skipped/failed URLs with reasons
    """
    all_chunks = []
    skipped = []

    for url in urls:
        url = url.strip()
        if not url:
            continue

        # Check skip patterns
        if should_skip_url(url):
            skipped.append(f"{url} | Skipped: matches skip pattern (legal/nav page)")
            logger.info("Skipping URL (pattern match): %s", url)
            continue

        # Fetch
        html = fetch_page(url)
        if not html:
            skipped.append(f"{url} | Failed: could not fetch page")
            continue

        # Extract
        text = extract_text(html)
        if not text:
            skipped.append(f"{url} | Failed: no content extracted")
            continue

        # Clean
        text = clean_text(text)

        # Thin content check
        if is_thin_content(text):
            skipped.append(f"{url} | Skipped: thin content ({len(text.split())} words)")
            logger.info("Skipping URL (thin content): %s", url)
            continue

        # Truncate
        text = truncate_text(text)

        # Chunk
        chunks = chunk_text(text, url)
        all_chunks.extend(chunks)

    df = pd.DataFrame(all_chunks, columns=["url", "chunk_id", "chunk_text"])
    logger.info("Ingested %d chunks from %d URLs (%d skipped)", len(df), len(urls) - len(skipped), len(skipped))
    return df, skipped
