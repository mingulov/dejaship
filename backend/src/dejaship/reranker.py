"""ColBERT (late-interaction) reranker module."""
from __future__ import annotations

import numpy as np
from fastembed import LateInteractionTextEmbedding

from dejaship.config import settings

_reranker: LateInteractionTextEmbedding | None = None


def load_reranker() -> LateInteractionTextEmbedding:
    global _reranker
    _reranker = LateInteractionTextEmbedding(model_name=settings.RERANKER_MODEL)
    return _reranker


def get_reranker() -> LateInteractionTextEmbedding:
    if _reranker is None:
        raise RuntimeError("Reranker not loaded. Call load_reranker() first.")
    return _reranker


def maxsim_score(query_embeddings: np.ndarray, doc_embeddings: np.ndarray) -> float:
    """Compute ColBERT MaxSim score between query and document token embeddings.

    For each query token, find maximum cosine similarity with any doc token,
    then sum across all query tokens.

    Args:
        query_embeddings: shape (Q, D) - query token embeddings
        doc_embeddings: shape (T, D) - document token embeddings

    Returns:
        MaxSim score (higher = more relevant)
    """
    # dot product matrix: Q x T
    scores = query_embeddings @ doc_embeddings.T
    # MaxSim: for each query token, max sim over doc tokens; sum over query tokens
    return float(scores.max(axis=1).sum())


def rerank(
    query_text: str,
    candidates: list,
    *,
    threshold: float,
    text_fn: callable,
) -> list:
    """Rerank candidates using ColBERT MaxSim scoring.

    Args:
        query_text: The query string
        candidates: List of objects with a text representation
        threshold: Minimum MaxSim score to include in results
        text_fn: Callable(candidate) -> str to extract text for scoring

    Returns:
        Candidates passing threshold, sorted by score descending.
    """
    model = get_reranker()

    # Encode query
    query_embs = list(model.query_embed([query_text]))[0]  # (Q, D) ndarray

    scored = []
    for candidate in candidates:
        doc_text = text_fn(candidate)
        doc_embs = list(model.passage_embed([doc_text]))[0]  # (T, D) ndarray
        score = maxsim_score(query_embs, doc_embs)
        if score >= threshold:
            scored.append((score, candidate))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored]
