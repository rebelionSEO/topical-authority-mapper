"""UMAP dimensionality reduction, HDBSCAN clustering, and keyword extraction."""

import logging
from collections import Counter

import hdbscan
import numpy as np
import pandas as pd
import umap
from sklearn.feature_extraction.text import TfidfVectorizer

from src.config import (
    HDBSCAN_MIN_CLUSTER_SIZE,
    HDBSCAN_MIN_SAMPLES,
    TOP_N_KEYWORDS,
    UMAP_METRIC,
    UMAP_MIN_DIST,
    UMAP_N_COMPONENTS,
    UMAP_N_NEIGHBORS,
)

logger = logging.getLogger(__name__)


def reduce_dimensions(embeddings: np.ndarray) -> np.ndarray:
    """Reduce embedding dimensions with UMAP."""
    logger.info("Reducing dimensions with UMAP (%d -> %d)", embeddings.shape[1], UMAP_N_COMPONENTS)
    reducer = umap.UMAP(
        n_neighbors=UMAP_N_NEIGHBORS,
        n_components=UMAP_N_COMPONENTS,
        min_dist=UMAP_MIN_DIST,
        metric=UMAP_METRIC,
        random_state=42,
    )
    reduced = reducer.fit_transform(embeddings)
    return reduced


def cluster_embeddings(reduced: np.ndarray) -> np.ndarray:
    """Cluster reduced embeddings with HDBSCAN. Returns cluster labels (-1 = noise)."""
    logger.info("Clustering with HDBSCAN (min_cluster_size=%d)", HDBSCAN_MIN_CLUSTER_SIZE)
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=HDBSCAN_MIN_CLUSTER_SIZE,
        min_samples=HDBSCAN_MIN_SAMPLES,
        metric="euclidean",
    )
    labels = clusterer.fit_predict(reduced)

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = (labels == -1).sum()
    logger.info("Found %d clusters, %d noise points", n_clusters, n_noise)
    return labels


def extract_cluster_keywords(
    df: pd.DataFrame,
    label_col: str = "cluster_id",
    text_col: str = "chunk_text",
) -> pd.DataFrame:
    """Extract top keywords per cluster using TF-IDF."""
    cluster_ids = sorted(df[label_col].unique())
    valid_clusters = [c for c in cluster_ids if c != -1]

    if not valid_clusters:
        return pd.DataFrame(columns=["cluster_id", "cluster_name", "keywords"])

    # Build one TF-IDF matrix across all clusters for better term weighting
    cluster_texts = {}
    for cid in valid_clusters:
        texts = df[df[label_col] == cid][text_col].tolist()
        cluster_texts[cid] = " ".join(texts)

    # Generic single words to filter out of final keyword lists
    GENERIC_SINGLES = {
        "marketing", "content", "seo", "ads", "ai", "digital", "data", "strategy",
        "guide", "tips", "tools", "best", "online", "business", "growth", "brand",
        "page", "search", "social", "media", "web", "agency", "services", "campaign",
        "advertising", "management", "platform", "software", "email", "video",
        "google", "facebook", "free", "new", "top", "make", "way", "use", "using",
        "like", "need", "help", "time", "key", "also", "one", "can", "get", "just",
        "right", "work", "create", "good", "high", "learn", "customers", "customer",
        "companies", "company", "team", "results", "important", "people", "world",
        "success", "experience", "process", "based", "including", "approach",
        "industry", "market", "service", "marketing", "research", "target",
        "audience", "brands", "channels", "cost", "rate", "lead", "leads",
        "build", "offer", "product", "products", "solutions", "home", "site",
        "traffic", "users", "user", "website", "year", "example", "different",
        "provide", "specific", "type", "types", "tool", "options", "set", "way",
        "ensures", "review", "real", "value", "making", "potential", "drive",
        "effective", "ensure", "makes", "plan", "start", "level", "run", "turn",
        "connectors", "answer", "form", "builders", "copy", "ctr", "cpm",
    }

    corpus = [cluster_texts[cid] for cid in valid_clusters]
    # Two-pass: extract 2-3 word phrases for keywords, but also 1-grams for cluster naming fallback
    tfidf_phrases = TfidfVectorizer(
        ngram_range=(2, 3),
        stop_words="english",
        max_features=5000,
        min_df=1,
    )
    tfidf_singles = TfidfVectorizer(
        ngram_range=(1, 1),
        stop_words="english",
        max_features=3000,
        min_df=1,
    )
    phrase_matrix = tfidf_phrases.fit_transform(corpus)
    single_matrix = tfidf_singles.fit_transform(corpus)
    phrase_names = tfidf_phrases.get_feature_names_out()
    single_names = tfidf_singles.get_feature_names_out()

    results = []
    for i, cid in enumerate(valid_clusters):
        # Get top multi-word phrases (the good stuff)
        p_scores = phrase_matrix[i].toarray().flatten()
        p_top = p_scores.argsort()[-TOP_N_KEYWORDS * 2:][::-1]
        phrases = [phrase_names[idx] for idx in p_top if p_scores[idx] > 0]

        # Get top single words (for cluster naming only, filtered)
        s_scores = single_matrix[i].toarray().flatten()
        s_top = s_scores.argsort()[-20:][::-1]
        singles = [single_names[idx] for idx in s_top
                   if s_scores[idx] > 0 and single_names[idx] not in GENERIC_SINGLES]

        # Final keyword list: prefer phrases, pad with non-generic singles if needed
        kw_list = phrases[:TOP_N_KEYWORDS]
        if len(kw_list) < TOP_N_KEYWORDS:
            for s in singles:
                if s not in " ".join(kw_list) and len(kw_list) < TOP_N_KEYWORDS:
                    kw_list.append(s)

        # Generate cluster name from the most specific phrase
        cluster_name = _generate_cluster_name(kw_list)

        results.append({
            "cluster_id": cid,
            "cluster_name": cluster_name,
            "keywords": ", ".join(kw_list),
        })

    return pd.DataFrame(results)


def _generate_cluster_name(keywords: list[str]) -> str:
    """Generate a descriptive cluster name from top keywords."""
    if not keywords:
        return "Uncategorized"

    # Use top 2-3 keywords, capitalize
    name_parts = keywords[:3]
    # Find the most descriptive (longest) keyword as primary
    primary = max(name_parts, key=len)
    return primary.title()


def assign_url_clusters(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate chunk-level clusters to URL level.

    Returns DataFrame with: url, main_cluster, secondary_clusters
    """
    url_clusters = []

    for url, group in df.groupby("url"):
        cluster_counts = Counter(group["cluster_id"])
        # Remove noise from consideration for main cluster
        if -1 in cluster_counts and len(cluster_counts) > 1:
            del cluster_counts[-1]

        if not cluster_counts:
            main_cluster = -1
            secondary = []
        else:
            main_cluster = cluster_counts.most_common(1)[0][0]
            secondary = [c for c, _ in cluster_counts.most_common() if c != main_cluster and c != -1]

        url_clusters.append({
            "url": url,
            "main_cluster": main_cluster,
            "secondary_clusters": "; ".join(str(c) for c in secondary) if secondary else "",
        })

    return pd.DataFrame(url_clusters)
