"""2D projection of the chunk embeddings for the dashboard's Vector Map tab.

Aggregates chunks → one point per URL (mean of chunk embeddings), then projects
to 2D via UMAP. Each point gets metadata for tooltip + click handling: URL,
cluster_id, cluster_name, page_type, intent.

Output: output/vector_map.json with the shape:
  {
    "points": [
      {"x": 1.23, "y": -0.45, "url": "...", "cluster_id": 3,
       "cluster_name": "Funnel Analysis", "page_type": "blog", "intent": "informational"},
      ...
    ],
    "cluster_legend": {3: "Funnel Analysis", ...}
  }

Read by dashboard.py + rendered as a Plotly scatter in dashboard_html.py.
"""

import json
import logging
import os
import pickle
from typing import Optional

import numpy as np
import pandas as pd

from src.config import cache_dir, output_dir

logger = logging.getLogger(__name__)


def build_vector_map(
    chunks_df: Optional[pd.DataFrame] = None,
    embeddings: Optional[np.ndarray] = None,
    cluster_info: Optional[pd.DataFrame] = None,
) -> dict:
    """Compute the 2D vector map. If args are None, loads from cache + output dir."""

    cdir = cache_dir()
    out = output_dir()

    if chunks_df is None:
        path = os.path.join(cdir, "chunks_df.pkl")
        if not os.path.exists(path):
            logger.warning("vector_map: chunks_df.pkl missing")
            return {"points": [], "cluster_legend": {}}
        chunks_df = pd.read_pickle(path)

    if embeddings is None:
        path = os.path.join(cdir, "embeddings.pkl")
        if not os.path.exists(path):
            logger.warning("vector_map: embeddings.pkl missing")
            return {"points": [], "cluster_legend": {}}
        with open(path, "rb") as f:
            embeddings = pickle.load(f)

    if cluster_info is None:
        path = os.path.join(out, "clusters.csv")
        if os.path.exists(path):
            cluster_info = pd.read_csv(path)
        else:
            cluster_info = pd.DataFrame(columns=["cluster_id", "cluster_name"])

    cluster_name_by_id = dict(zip(cluster_info["cluster_id"], cluster_info["cluster_name"]))

    # Aggregate chunks → one mean vector per URL
    chunks_df = chunks_df.reset_index(drop=True)
    embeddings = np.asarray(embeddings, dtype=np.float32)

    url_to_indices: dict = {}
    for i, row in chunks_df.iterrows():
        url_to_indices.setdefault(row["url"], []).append(i)

    urls = []
    url_vecs = []
    url_clusters = []
    for url, idxs in url_to_indices.items():
        urls.append(url)
        url_vecs.append(embeddings[idxs].mean(axis=0))
        # Pick the most-common cluster id assigned to this URL's chunks (mode)
        cids = [int(chunks_df.iloc[i].get("cluster_id", -1)) if "cluster_id" in chunks_df.columns else -1 for i in idxs]
        url_clusters.append(max(set(cids), key=cids.count))

    if not url_vecs:
        return {"points": [], "cluster_legend": {}}

    matrix = np.vstack(url_vecs)

    # 2D project — UMAP if enough points, else PCA fallback
    coords = _project_2d(matrix)

    # Per-URL metadata enrichment (intent, page type)
    intent_by_url: dict = {}
    intent_path = os.path.join(out, "search_intent.csv")
    if os.path.exists(intent_path):
        try:
            idf = pd.read_csv(intent_path)
            intent_by_url = dict(zip(idf["url"], idf["primary_intent"]))
        except Exception:
            pass

    from src.enhancements import classify_page_type

    points = []
    for i, url in enumerate(urls):
        cid = url_clusters[i]
        points.append({
            "x": float(coords[i, 0]),
            "y": float(coords[i, 1]),
            "url": url,
            "cluster_id": cid,
            "cluster_name": cluster_name_by_id.get(cid, "Unclustered" if cid == -1 else f"Cluster {cid}"),
            "page_type": classify_page_type(url),
            "intent": intent_by_url.get(url, ""),
        })

    legend = {int(cid): cluster_name_by_id.get(int(cid), f"Cluster {cid}") for cid in cluster_info["cluster_id"]}

    result = {"points": points, "cluster_legend": legend}

    out_path = os.path.join(out, "vector_map.json")
    try:
        with open(out_path, "w") as f:
            json.dump(result, f)
        logger.info("vector_map written: %d points → %s", len(points), out_path)
    except OSError as e:
        logger.warning("Could not write vector_map.json: %s", e)

    return result


def _project_2d(matrix: np.ndarray) -> np.ndarray:
    """Project N×D vectors to N×2. Tries UMAP, falls back to PCA."""
    n, d = matrix.shape
    if n < 4:
        # Too few points for meaningful projection — just zero-pad
        result = np.zeros((n, 2))
        for i in range(n):
            result[i] = [float(i), 0.0]
        return result
    try:
        import umap
        reducer = umap.UMAP(
            n_components=2,
            n_neighbors=min(15, n - 1),
            min_dist=0.1,
            metric="cosine",
            random_state=42,
        )
        return reducer.fit_transform(matrix)
    except Exception as e:
        logger.warning("UMAP failed (%s); falling back to PCA", e)
        try:
            from sklearn.decomposition import PCA
            return PCA(n_components=2).fit_transform(matrix)
        except Exception as e2:
            logger.error("PCA also failed (%s); returning zero coords", e2)
            return np.zeros((n, 2))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = build_vector_map()
    print(f"Vector map: {len(result['points'])} points across {len(result['cluster_legend'])} clusters")
