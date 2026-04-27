"""Re-scrape Acme URLs for per-page actual publish/modified dates.

The sitemap reports a single near-uniform lastmod for every URL (CMS deploy date,
not page date), so freshness comes back as "100% fresh" — useless. This script
forces the HTML-scrape path used as fallback in score_content_freshness, so each
URL gets its own actual datePublished / dateModified from meta tags or JSON-LD.

Reads URLs from output/url_mapping.csv. Writes output/content_freshness.csv.
"""
from __future__ import annotations

import csv
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from src.enhancements import _extract_dates_from_html, _freshness_label  # noqa: E402


def main() -> None:
    url_mapping = ROOT / "output" / "url_mapping.csv"
    if not url_mapping.exists():
        sys.exit(f"missing {url_mapping}")

    with url_mapping.open() as f:
        urls = [r["url"] for r in csv.DictReader(f) if r.get("url")]

    logging.info("Scraping HTML for %d URLs (this takes a few minutes)...", len(urls))
    url_dates = _extract_dates_from_html(urls)

    today = datetime.now()
    rows = []
    for url, date_str in url_dates.items():
        try:
            lastmod = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue
        age_days = (today - lastmod).days
        rows.append({
            "url": url,
            "lastmod": date_str,
            "age_days": age_days,
            "freshness": _freshness_label(age_days),
        })

    rows.sort(key=lambda r: r["age_days"], reverse=True)

    out = ROOT / "output" / "content_freshness.csv"
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["url", "lastmod", "age_days", "freshness"])
        w.writeheader()
        w.writerows(rows)

    from collections import Counter
    buckets = Counter(r["freshness"] for r in rows)
    logging.info("Wrote %d rows to %s", len(rows), out)
    logging.info("Bucket distribution: %s", dict(buckets))


if __name__ == "__main__":
    main()
