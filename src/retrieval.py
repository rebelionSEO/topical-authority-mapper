"""Shared RAG retrieval layer.

Reuses the FAISS index + chunks_df that the audit pipeline already builds. Three
retrieval modes:

  - search_by_text(query, k)       — vector search across the whole corpus
  - search_by_url(url, k)          — return chunks belonging to that URL (no search)
  - search_by_cluster(cluster_id, k) — top chunks closest to the cluster centroid
                                       (most "representative" of the cluster)

The pipeline saves three artifacts to the cache dir:
  - cache/embeddings.pkl   (numpy ndarray, normalized)
  - cache/embeddings.faiss (FAISS IndexFlatIP)
  - cache/chunks_df.pkl    (pandas DataFrame: url, chunk_id, chunk_text, cluster_id)

Row order matches between embeddings and chunks_df, so embeddings[i] is the
vector for chunks_df.iloc[i].

Returns a list of `Chunk` records ready to be inlined in an LLM prompt.
"""

import logging
import os
import pickle
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from src.config import EMBEDDING_MODEL, cache_dir

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    url: str
    chunk_id: int
    text: str
    cluster_id: int
    score: float = 0.0  # cosine similarity from the query (0 if not from a search)

    def short(self, max_chars: int = 600) -> str:
        t = (self.text or "").strip()
        return t if len(t) <= max_chars else t[:max_chars] + "…"


class RetrievalIndex:
    """Lazy-loaded RAG index over the audited site's content."""

    def __init__(self, chunks_df: pd.DataFrame, embeddings: np.ndarray, faiss_index):
        self.chunks_df = chunks_df.reset_index(drop=True)
        self.embeddings = embeddings
        self.faiss = faiss_index
        self._model = None  # lazy-loaded sentence-transformer for query encoding

        # url -> [chunk row indices]
        self._url_index: dict = {}
        for i, row in self.chunks_df.iterrows():
            self._url_index.setdefault(row["url"], []).append(i)
        # cluster_id -> [chunk row indices]
        self._cluster_index: dict = {}
        for i, row in self.chunks_df.iterrows():
            cid = int(row.get("cluster_id", -1)) if "cluster_id" in self.chunks_df.columns else -1
            self._cluster_index.setdefault(cid, []).append(i)

    # ---------------------------------------------------------------------
    # Loaders
    # ---------------------------------------------------------------------

    @classmethod
    def from_cache(cls, cache_dir_path: Optional[str] = None) -> Optional["RetrievalIndex"]:
        """Try to load the retrieval index from cache. Returns None if any artifact is missing."""
        cdir = cache_dir_path or cache_dir()
        chunks_path = os.path.join(cdir, "chunks_df.pkl")
        emb_path = os.path.join(cdir, "embeddings.pkl")
        faiss_path = os.path.join(cdir, "embeddings.faiss")
        if not (os.path.exists(chunks_path) and os.path.exists(emb_path)):
            logger.info("RetrievalIndex unavailable: missing chunks_df.pkl or embeddings.pkl")
            return None
        try:
            chunks_df = pd.read_pickle(chunks_path)
            with open(emb_path, "rb") as f:
                embeddings = pickle.load(f)
        except Exception:
            logger.exception("Could not load RAG cache files")
            return None
        # FAISS is optional — we can build it on the fly from embeddings if missing
        faiss_index = None
        try:
            import faiss
            if os.path.exists(faiss_path):
                faiss_index = faiss.read_index(faiss_path)
            else:
                # Inner-product index on normalized vectors == cosine similarity
                arr = np.asarray(embeddings, dtype=np.float32)
                norms = np.linalg.norm(arr, axis=1, keepdims=True)
                norms[norms == 0] = 1
                arr = arr / norms
                faiss_index = faiss.IndexFlatIP(arr.shape[1])
                faiss_index.add(arr)
                embeddings = arr
        except ImportError:
            logger.warning("FAISS not available; falling back to numpy-only search")
        return cls(chunks_df, embeddings, faiss_index)

    # ---------------------------------------------------------------------
    # Encoding
    # ---------------------------------------------------------------------

    def _encode(self, texts: list[str]) -> np.ndarray:
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(EMBEDDING_MODEL)
        return self._model.encode(texts, show_progress_bar=False, normalize_embeddings=True)

    # ---------------------------------------------------------------------
    # Public retrieval API
    # ---------------------------------------------------------------------

    def search_by_text(self, query: str, k: int = 5) -> list[Chunk]:
        """Vector search across the whole corpus. Returns top-k chunks by cosine sim."""
        if not query:
            return []
        qvec = self._encode([query]).astype(np.float32)
        if self.faiss is not None:
            scores, idxs = self.faiss.search(qvec, k)
            scores, idxs = scores[0], idxs[0]
        else:
            # numpy fallback
            sims = self.embeddings @ qvec[0]
            order = np.argsort(-sims)[:k]
            scores = sims[order]
            idxs = order
        return self._materialize(idxs, scores)

    def search_by_url(self, url: str, k: int = 5) -> list[Chunk]:
        """Return up to k chunks from a specific URL (in chunk_id order)."""
        idxs = self._url_index.get(url, [])[:k]
        return self._materialize(idxs, scores=None)

    def search_by_cluster(self, cluster_id: int, k: int = 8) -> list[Chunk]:
        """Return the k chunks closest to the cluster centroid — most representative."""
        idxs_all = self._cluster_index.get(cluster_id, [])
        if not idxs_all:
            return []
        # Compute centroid + cosine sim to each cluster member
        cluster_embs = self.embeddings[idxs_all]
        centroid = cluster_embs.mean(axis=0)
        n = np.linalg.norm(centroid)
        if n > 0:
            centroid = centroid / n
        sims = cluster_embs @ centroid
        order = np.argsort(-sims)[:k]
        chosen_global_idxs = [idxs_all[i] for i in order]
        chosen_scores = sims[order]
        return self._materialize(chosen_global_idxs, chosen_scores)

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------

    def _materialize(self, idxs, scores=None) -> list[Chunk]:
        out = []
        for i, idx in enumerate(idxs):
            if idx < 0 or idx >= len(self.chunks_df):
                continue
            row = self.chunks_df.iloc[int(idx)]
            score = float(scores[i]) if scores is not None else 0.0
            out.append(Chunk(
                url=row.get("url", ""),
                chunk_id=int(row.get("chunk_id", 0)),
                text=str(row.get("chunk_text", "")),
                cluster_id=int(row.get("cluster_id", -1)) if "cluster_id" in self.chunks_df.columns else -1,
                score=score,
            ))
        return out

    @property
    def n_chunks(self) -> int:
        return len(self.chunks_df)

    @property
    def n_urls(self) -> int:
        return len(self._url_index)

    @property
    def n_clusters(self) -> int:
        return len([cid for cid in self._cluster_index if cid != -1])


# Convenience module-level loader (cached per-process)
_INDEX_CACHE: Optional[RetrievalIndex] = None


def get_index() -> Optional[RetrievalIndex]:
    """Get a process-cached retrieval index, or None if cache files are missing."""
    global _INDEX_CACHE
    if _INDEX_CACHE is None:
        _INDEX_CACHE = RetrievalIndex.from_cache()
    return _INDEX_CACHE


def reset_cache():
    """Force the next get_index() call to reload from disk (use after a fresh pipeline run)."""
    global _INDEX_CACHE
    _INDEX_CACHE = None
