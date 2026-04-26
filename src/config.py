"""Configuration and constants for the Topical Authority Mapper."""

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Optional
from urllib.parse import urlparse

# Paths (defaults — can be overridden per-run via SiteConfig.output_dir / set_runtime_cache_dir)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
CACHE_DIR = os.path.join(PROJECT_ROOT, "cache")

# Model
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Content extraction
MAX_CHARS_PER_PAGE = 7000
MIN_WORDS_THRESHOLD = 300
CHUNK_SIZE_WORDS = 600  # target ~500-700 words per chunk

# Clustering
UMAP_N_NEIGHBORS = 15
UMAP_N_COMPONENTS = 5
UMAP_MIN_DIST = 0.0
UMAP_METRIC = "cosine"
HDBSCAN_MIN_CLUSTER_SIZE = 3
HDBSCAN_MIN_SAMPLES = 2

# KeyBERT
TOP_N_KEYWORDS = 10

# Cannibalization
CANNIBALIZATION_URL_THRESHOLD = 2

# Debug
DEBUG_MODE = False
DEBUG_URL_LIMIT = 10

# Default skip patterns — applied to every run, can be extended via SiteConfig.skip_patterns
DEFAULT_SKIP_URL_PATTERNS = [
    "/privacy-policy", "/privacy/", "/terms-of-service", "/terms-and-conditions",
    "/cookie-policy", "/legal-notice", "/legal-disclaimer", "/disclaimer",
    "/sitemap.xml", "/robots.txt", "/wp-admin", "/wp-login",
    "/cart", "/checkout", "/my-account", "/login", "/register",
]
# Backwards-compat alias
SKIP_URL_PATTERNS = DEFAULT_SKIP_URL_PATTERNS

# Navigation/boilerplate phrases to filter from extracted text
BOILERPLATE_PHRASES = [
    "all rights reserved", "cookie policy", "privacy policy",
    "terms of service", "terms and conditions", "skip to content",
    "subscribe to our newsletter", "follow us on", "back to top",
    "copyright ©", "powered by",
]


# ---------------------------------------------------------------------------
# Per-run site configuration
# ---------------------------------------------------------------------------

SITE_CONFIG_FILENAME = "site_config.json"


@dataclass
class SiteConfig:
    """Configuration for the site being analyzed.

    name             — Human-readable label used in titles/footers (e.g. "Acme Inc").
    domain           — Bare hostname, no protocol, no trailing slash (e.g. "acme.com").
    sitemaps         — Sitemap URLs used by freshness scoring.
    competitors      — Display names of competitor sites for which gap CSVs exist.
    output_dir       — Where to write CSVs / dashboard / PDF (None = default OUTPUT_DIR).
    industry         — Optional vertical hint (e.g. "b2b-saas", "ecommerce", "agency").
    skip_patterns    — Extra URL substrings to skip during ingestion (merged with defaults).
    listing_patterns — Extra regex patterns marking URLs as intentionally thin (hubs, archives).
    """

    name: str
    domain: str
    sitemaps: list = field(default_factory=list)
    competitors: list = field(default_factory=list)
    output_dir: Optional[str] = None
    industry: Optional[str] = None
    skip_patterns: list = field(default_factory=list)
    listing_patterns: list = field(default_factory=list)

    @property
    def url_prefixes(self) -> list:
        """Possible URL prefixes for the site (with/without www, http/https)."""
        host = self.domain
        bare = host[4:] if host.startswith("www.") else host
        return [
            f"https://{host}/",
            f"http://{host}/",
            f"https://www.{bare}/",
            f"http://www.{bare}/",
            f"https://{bare}/",
            f"http://{bare}/",
        ]

    def strip_url(self, url: str) -> str:
        """Convert a full URL into a relative slug starting with '/'."""
        if not url:
            return url
        for prefix in self.url_prefixes:
            if url.startswith(prefix):
                return "/" + url[len(prefix):]
        return url

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SiteConfig":
        return cls(
            name=data["name"],
            domain=data["domain"],
            sitemaps=data.get("sitemaps", []),
            competitors=data.get("competitors", []),
            output_dir=data.get("output_dir"),
            industry=data.get("industry"),
            skip_patterns=data.get("skip_patterns", []),
            listing_patterns=data.get("listing_patterns", []),
        )


def domain_from_url(url: str) -> str:
    """Extract the bare hostname from a URL."""
    parsed = urlparse(url)
    return parsed.netloc or url


# ---------------------------------------------------------------------------
# Runtime path resolution — modules call these instead of using OUTPUT_DIR/CACHE_DIR directly
# ---------------------------------------------------------------------------

_RUNTIME_CACHE_DIR: Optional[str] = None


def set_runtime_cache_dir(path: Optional[str]) -> None:
    """Override the cache directory for the current process. Call from main.py before any I/O."""
    global _RUNTIME_CACHE_DIR
    _RUNTIME_CACHE_DIR = os.path.abspath(path) if path else None


def cache_dir() -> str:
    """Resolve the active cache directory."""
    return _RUNTIME_CACHE_DIR or CACHE_DIR


def output_dir() -> str:
    """Resolve the active output directory: SiteConfig.output_dir if set, else default OUTPUT_DIR."""
    site = load_site_config()
    if site and site.output_dir:
        return site.output_dir
    return OUTPUT_DIR


def save_site_config(config: SiteConfig, cache_dir_path: Optional[str] = None) -> str:
    """Persist the site config to cache so other modules can pick it up."""
    target = cache_dir_path or cache_dir()
    os.makedirs(target, exist_ok=True)
    path = os.path.join(target, SITE_CONFIG_FILENAME)
    with open(path, "w") as f:
        json.dump(config.to_dict(), f, indent=2)
    return path


def load_site_config(cache_dir_path: Optional[str] = None) -> Optional[SiteConfig]:
    """Load the cached site config, or None if it doesn't exist."""
    path = os.path.join(cache_dir_path or cache_dir(), SITE_CONFIG_FILENAME)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return SiteConfig.from_dict(json.load(f))


def require_site_config(cache_dir_path: Optional[str] = None) -> SiteConfig:
    """Load the site config or raise if missing."""
    config = load_site_config(cache_dir_path)
    if config is None:
        raise RuntimeError(
            f"Site config not found. Run the main pipeline first "
            "(python -m src.main --sitemap <url> --site-name <name>) or create the file manually."
        )
    return config


def resolved_skip_patterns() -> list:
    """Default skip patterns plus any added via SiteConfig.skip_patterns."""
    site = load_site_config()
    extras = list(site.skip_patterns) if site else []
    return list(DEFAULT_SKIP_URL_PATTERNS) + extras


def extra_listing_patterns() -> list:
    """Custom listing patterns from SiteConfig (regex strings)."""
    site = load_site_config()
    return list(site.listing_patterns) if site else []
