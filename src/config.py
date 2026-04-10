"""Configuration and constants for the Topical Authority Mapper."""

import os

# Paths
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

# Pages to skip entirely (by URL pattern)
SKIP_URL_PATTERNS = [
    "/privacy-policy", "/privacy/", "/terms-of-service", "/terms-and-conditions",
    "/cookie-policy", "/legal-notice", "/legal-disclaimer", "/disclaimer",
    "/sitemap.xml", "/robots.txt", "/wp-admin", "/wp-login",
    "/cart", "/checkout", "/my-account", "/login", "/register",
]

# Navigation/boilerplate phrases to filter from extracted text
BOILERPLATE_PHRASES = [
    "all rights reserved", "cookie policy", "privacy policy",
    "terms of service", "terms and conditions", "skip to content",
    "subscribe to our newsletter", "follow us on", "back to top",
    "copyright ©", "powered by",
]
