"""ColBERT (late-interaction) reranker module."""
from __future__ import annotations

from typing import Any, Callable

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

    For each query token, find the maximum dot product with any doc token,
    then sum across all query tokens. fastembed's LateInteractionTextEmbedding
    returns L2-normalised token embeddings, so dot product equals cosine similarity.

    Args:
        query_embeddings: shape (Q, D) — query token embeddings (L2-normalised)
        doc_embeddings: shape (T, D) — document token embeddings (L2-normalised)

    Returns:
        MaxSim score (higher = more relevant)
    """
    # dot product matrix: Q x T
    scores = query_embeddings @ doc_embeddings.T
    # MaxSim: for each query token, max sim over doc tokens; sum over query tokens
    return float(scores.max(axis=1).sum())


def rerank(
    query_text: str,
    candidates: list[Any],
    *,
    threshold: float,
    text_fn: Callable[[Any], str],
) -> list[Any]:
    """Rerank candidates using ColBERT MaxSim scoring.

    This function is synchronous (CPU-bound ONNX inference) and must be
    called via run_in_threadpool in async contexts.

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

    # Batch-encode all documents (single ONNX forward pass per model batch)
    doc_texts = [text_fn(c) for c in candidates]
    doc_embs_list = list(model.passage_embed(doc_texts))

    scored = []
    for candidate, doc_embs in zip(candidates, doc_embs_list):
        score = maxsim_score(query_embs, doc_embs)
        if score >= threshold:
            scored.append((score, candidate))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored]
