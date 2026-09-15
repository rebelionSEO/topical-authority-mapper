"""Bounded HTTP fetching, conservative URL normalization and sitemap discovery."""

import gzip
import io
import logging
import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)
MAX_BYTES = 10 * 1024 * 1024
USER_AGENT = "TopicalAuthorityMapper/0.2 (+https://github.com/rebelionSEO/topical-authority-mapper)"


def normalize_url(url):
    """Preserve path/query semantics; remove fragments and default ports."""
    try:
        parsed = urlsplit(str(url).strip())
        if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            return ""
        host = parsed.hostname.lower().encode("idna").decode("ascii")
        if ":" in host:
            host = f"[{host}]"
        port = parsed.port
        if port and (parsed.scheme.lower(), port) not in (("http", 80), ("https", 443)):
            host += f":{port}"
        return urlunsplit((parsed.scheme.lower(), host, parsed.path or "/", parsed.query, ""))
    except (ValueError, UnicodeError):
        return ""


def create_session():
    session = requests.Session()
    retry = Retry(total=2, connect=2, read=2, status=2, backoff_factor=0.5,
                  status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"],
                  respect_retry_after_header=True)
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    session.headers.update({"User-Agent": USER_AGENT})
    session.max_redirects = 5
    return session


def fetch(session, url, timeout=20):
    if not normalize_url(url):
        raise ValueError(f"Unsupported URL: {url}")
    with session.get(url, timeout=timeout, stream=True) as response:
        response.raise_for_status()
        parts = []
        size = 0
        for part in response.iter_content(65536):
            size += len(part)
            if size > MAX_BYTES:
                raise ValueError(f"Response exceeds {MAX_BYTES} bytes: {url}")
            parts.append(part)
        # Materialize within the response context, releasing its connection promptly.
        response._content = b"".join(parts)
        response._content_consumed = True
        return response


@dataclass
class SitemapResult:
    pages: dict = field(default_factory=dict)
    issues: list = field(default_factory=list)
    visited: int = 0


def read_sitemaps(urls, *, session=None, max_sitemaps=100, max_depth=8, max_urls=50000):
    result = SitemapResult()
    owned = session is None
    session = session or create_session()
    queue = deque((url, 0) for url in urls)
    seen = set()
    try:
        while queue:
            raw, depth = queue.popleft()
            url = normalize_url(raw)
            if not url:
                result.issues.append({"url": str(raw), "error": "invalid_url"})
                continue
            if url in seen:
                continue
            if len(seen) >= max_sitemaps or len(result.pages) >= max_urls:
                result.issues.append({"url": url, "error": "discovery_limit"})
                break
            if depth > max_depth:
                result.issues.append({"url": url, "error": "depth_limit"})
                continue
            seen.add(url)
            result.visited += 1
            try:
                response = fetch(session, url)
                payload = response.content
                if payload.startswith(b"\x1f\x8b"):
                    with gzip.GzipFile(fileobj=io.BytesIO(payload)) as compressed:
                        payload = compressed.read(MAX_BYTES + 1)
                    if len(payload) > MAX_BYTES:
                        raise ValueError("Decompressed sitemap exceeds size limit")
                root = ET.fromstring(payload)
                kind = root.tag.rsplit("}", 1)[-1]
                if kind not in ("urlset", "sitemapindex"):
                    raise ValueError("Not a sitemap document")
                for entry in root:
                    fields = {child.tag.rsplit("}", 1)[-1]: (child.text or "").strip() for child in entry}
                    loc = normalize_url(urljoin(response.url, fields.get("loc", ""))) if fields.get("loc") else ""
                    if not loc:
                        continue
                    if kind == "sitemapindex":
                        queue.append((loc, depth + 1))
                    elif len(result.pages) < max_urls:
                        if loc not in result.pages or not result.pages[loc]:
                            result.pages[loc] = fields.get("lastmod", "")
                    else:
                        result.issues.append({"url": url, "error": "url_limit"})
                        break
            except (requests.RequestException, ValueError, ET.ParseError, OSError) as exc:
                result.issues.append({"url": url, "error": str(exc)})
    finally:
        if owned:
            session.close()
    return result
