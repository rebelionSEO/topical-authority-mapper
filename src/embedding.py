"""Embedding generation and FAISS indexing."""

import logging
import os
import pickle

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from src.config import CACHE_DIR, EMBEDDING_MODEL

logger = logging.getLogger(__name__)


def get_model() -> SentenceTransformer:
    """Load the sentence-transformer model."""
    logger.info("Loading embedding model: %s", EMBEDDING_MODEL)
    return SentenceTransformer(EMBEDDING_MODEL)


def compute_embeddings(
    texts: list[str],
    model: SentenceTransformer | None = None,
    cache_path: str | None = None,
    batch_size: int = 64,
) -> np.ndarray:
    """
    Compute normalized embeddings for a list of texts.

    Uses cached embeddings if available and cache_path is provided.
    """
    # Check cache
    if cache_path and os.path.exists(cache_path):
        logger.info("Loading cached embeddings from %s", cache_path)
        with open(cache_path, "rb") as f:
            return pickle.load(f)

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
    if cache_path:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "wb") as f:
            pickle.dump(embeddings, f)
        logger.info("Cached embeddings to %s", cache_path)

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
