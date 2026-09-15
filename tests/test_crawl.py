import gzip
from unittest.mock import Mock

import pandas as pd
import pytest
import requests

from src import crawl, ingestion, enhancements
from src.config import SiteConfig, save_site_config, set_runtime_cache_dir


def response(url, content, status=200, content_type="text/html", headers=None):
    value = requests.Response()
    value.status_code = status
    value.url = url
    value._content = content.encode() if isinstance(content, str) else content
    value.encoding = "utf-8"
    value.headers = {"Content-Type": content_type, **(headers or {})}
    return value


def test_url_normalization_preserves_meaningful_variants():
    assert crawl.normalize_url("HTTPS://Example.com:443/a?x=2#section") == "https://example.com/a?x=2"
    assert crawl.normalize_url("https://example.com/a/") != crawl.normalize_url("https://example.com/a")
    assert not crawl.normalize_url("file:///etc/hosts")
    assert not crawl.normalize_url("https://user:pass@example.com")
    assert not crawl.normalize_url("https://example.com:bad")


def test_sitemap_cycles_gzip_dates_duplicates_and_partial_failure(monkeypatch):
    base = "https://example.com/"
    docs = {
        base + "index.xml": '<sitemapindex><sitemap><loc>index.xml</loc></sitemap><sitemap><loc>child.xml.gz</loc></sitemap><sitemap><loc>bad.xml</loc></sitemap></sitemapindex>',
        base + "child.xml.gz": gzip.compress(b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://EXAMPLE.com/page#part</loc><lastmod>2025-01-02</lastmod></url><url><loc>https://example.com/page</loc></url></urlset>'),
        base + "bad.xml": "<broken>",
    }
    requested = []
    def get(session, url, **kwargs):
        requested.append(url)
        return response(url, docs[url])
    monkeypatch.setattr(crawl, "fetch", get)
    result = crawl.read_sitemaps([base + "index.xml"], session=Mock())
    assert result.pages == {base + "page": "2025-01-02"}
    assert len(requested) == 3
    assert len(result.issues) == 1
    assert result.issues[0]["url"].endswith("bad.xml")
    bounded = crawl.read_sitemaps([base + "index.xml"], session=Mock(), max_sitemaps=1)
    assert bounded.visited == 1 and bounded.issues[0]["error"] == "discovery_limit"


def test_crawl_records_noindex_redirects_duplicates_canonical_and_failures(monkeypatch):
    base = "https://example.com"
    text = "<p>" + "Useful original technical content for readers. " * 80 + "</p>"
    def get(session, url, **kwargs):
        if url.endswith("robots.txt"):
            return response(url, "User-agent: *\nDisallow: /private")
        if url.endswith("/error"):
            failed = response(url, "", status=503)
            failed.raise_for_status()
        final = base + "/a" if url.endswith("/redirect") else url
        meta = '<meta name="robots" content="noindex">' if url.endswith("/hidden") else ""
        canonical = '<link rel="canonical" href="/preferred">' if url.endswith("/canonical") else ""
        return response(final, f"<html><head><title>Sample page</title>{meta}{canonical}</head><body><h1>Topic</h1>{text}</body></html>")
    monkeypatch.setattr(ingestion, "fetch", get)
    monkeypatch.setattr(ingestion, "resolved_skip_patterns", lambda: [])
    chunks, skipped = ingestion.ingest_urls([base + path for path in ["/a", "/a#part", "/redirect", "/hidden", "/private", "/canonical", "/error"]])
    records = chunks.attrs["crawl_records"]
    assert chunks.url.nunique() == 2
    assert len(records) == 7 and len(skipped) == 5
    assert records[1]["reason"] == "duplicate_url"
    assert records[2]["reason"] == "duplicate_redirect_target"
    assert records[3]["indexability"] == "noindex"
    assert records[4]["reason"] == "robots_disallowed_or_unavailable"
    assert records[5]["canonical"] == base + "/preferred"
    assert records[5]["title"] == "Sample page"
    assert records[6]["status_code"] == 503


def test_freshness_uses_recursive_dates_and_marks_unknown(monkeypatch, tmp_path):
    set_runtime_cache_dir(str(tmp_path / "cache"))
    save_site_config(SiteConfig("Test", "example.com", output_dir=str(tmp_path)))
    monkeypatch.setattr(crawl, "read_sitemaps", lambda _: crawl.SitemapResult(pages={
        "https://example.com/a": "2025-01-01", "https://example.com/b": "invalid", "https://example.com/c": "2999-01-01"}))
    requested = []
    def fallback(urls):
        requested.extend(urls)
        return {"https://example.com/b": "2025-02-01"}
    monkeypatch.setattr(enhancements, "_extract_dates_from_html", fallback)
    try:
        df = enhancements.score_content_freshness(["https://example.com/index.xml"], ["https://example.com/a", "https://example.com/b", "https://example.com/c"])
        rows = df.set_index("url")
        assert rows.loc["https://example.com/a", "date_source"] == "sitemap"
        assert rows.loc["https://example.com/b", "date_source"] == "html"
        assert rows.loc["https://example.com/c", "freshness"] == "Unknown"
        assert "https://example.com/a" not in requested
    finally:
        set_runtime_cache_dir(None)


def test_retry_policy_and_response_size_limit():
    with crawl.create_session() as session:
        policy = session.get_adapter("https://example.com").max_retries
        assert policy.is_retry("GET", 503)
        assert policy.total == 2
    large = Mock()
    large.iter_content.return_value = [b"x" * (crawl.MAX_BYTES + 1)]
    manager = Mock()
    manager.__enter__ = Mock(return_value=large)
    manager.__exit__ = Mock(return_value=False)
    session = Mock()
    session.get.return_value = manager
    with pytest.raises(ValueError, match="exceeds"):
        crawl.fetch(session, "https://example.com/large")
