"""Post-retrieval filters for improving search precision."""

from __future__ import annotations

from dejaship.config import settings


def jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Compute Jaccard similarity between two keyword sets."""
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def apply_jaccard_filter(
    query_keywords: list[str],
    candidates: list,
    threshold: float,
    min_keywords: int,
) -> list:
    """Filter candidates by keyword Jaccard similarity.

    Skips filtering if query has fewer than min_keywords (not enough signal).
    Each candidate must have a .keywords attribute (list[str]).
    """
    if len(query_keywords) < min_keywords:
        return candidates
    query_set = {kw.lower() for kw in query_keywords}
    return [
        c for c in candidates
        if jaccard_similarity(query_set, {kw.lower() for kw in c.keywords}) >= threshold
    ]
