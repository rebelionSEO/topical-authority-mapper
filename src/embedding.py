"""Embedding generation and FAISS indexing."""

import logging
import os
import hashlib
import json
import tempfile
from typing import TYPE_CHECKING

import faiss
import numpy as np
if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

from src.config import EMBEDDING_MODEL

logger = logging.getLogger(__name__)


def get_model() -> "SentenceTransformer":
    """Load the sentence-transformer model."""
    logger.info("Loading embedding model: %s", EMBEDDING_MODEL)
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMBEDDING_MODEL)


def compute_embeddings(
    texts: list[str],
    model: "SentenceTransformer | None" = None,
    cache_path: str | None = None,
    batch_size: int = 64,
    model_id: str | None = None,
) -> np.ndarray:
    """
    Compute normalized embeddings for a list of texts.

    Uses cached embeddings if available and cache_path is provided.
    """
    # Check cache
    # Custom encoders must declare a stable identity to reuse persistent results.
    identity = model_id or (EMBEDDING_MODEL if model is None else None)
    fingerprint = hashlib.sha256(json.dumps(
        {"version": 1, "model": identity, "texts": texts},
        ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    safe_path = cache_path + ".npz" if cache_path and identity else None
    if safe_path and os.path.exists(safe_path):
        try:
            with np.load(safe_path, allow_pickle=False) as cached:
                values = cached["embeddings"]
                if (str(cached["fingerprint"]) == fingerprint and values.ndim == 2
                        and len(values) == len(texts) and np.isfinite(values).all()):
                    return values
        except (ValueError, OSError, KeyError):
            logger.warning("Invalid embedding cache; recomputing %s", safe_path)

    if model is None:
        model = get_model()

    logger.info("Computing embeddings for %d texts (batch_size=%d)", len(texts), batch_size)
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,
    )
    embeddings = np.array(embeddings, dtype=np.float32)

    # Cache
    if embeddings.ndim != 2 or len(embeddings) != len(texts) or not np.isfinite(embeddings).all():
        raise ValueError("Encoder returned invalid embeddings")
    if safe_path:
        directory = os.path.dirname(os.path.abspath(safe_path))
        os.makedirs(directory, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=directory, suffix=".npz", delete=False) as f:
            tmp_path = f.name
        try:
            np.savez(tmp_path, embeddings=embeddings, fingerprint=fingerprint)
            os.replace(tmp_path, safe_path)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    return embeddings


def build_faiss_index(embeddings: np.ndarray, save_path: str | None = None) -> faiss.IndexFlatIP:
    """Build a FAISS index for similarity search (inner product on normalized vectors = cosine)."""
    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)
    logger.info("Built FAISS index with %d vectors (dim=%d)", index.ntotal, dim)

    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        faiss.write_index(index, save_path)
        logger.info("Saved FAISS index to %s", save_path)

    return index


def search_similar(index: faiss.IndexFlatIP, query_embedding: np.ndarray, top_k: int = 5) -> tuple:
    """Search for most similar vectors. Returns (distances, indices)."""
    distances, indices = index.search(query_embedding.reshape(1, -1), top_k)
    return distances[0], indices[0]
