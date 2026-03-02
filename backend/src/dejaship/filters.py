"""Post-retrieval filters for improving search precision."""

from __future__ import annotations

import functools
from typing import Protocol, TypeVar


class HasKeywords(Protocol):
    """Structural type: any object with a .keywords list attribute."""
    keywords: list[str]


_T = TypeVar("_T", bound=HasKeywords)


def jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Compute Jaccard similarity between two keyword sets."""
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


@functools.lru_cache(maxsize=1)
def _get_nlp():
    """Load spaCy en_core_web_sm model (cached singleton).

    Requires: uv sync --extra nlp && python -m spacy download en_core_web_sm
    Only loaded when ENABLE_SPACY_LEMMATIZATION=True.
    """
    import spacy
    return spacy.load("en_core_web_sm", disable=["parser", "ner"])


def _normalize_keyword(kw: str, *, lemmatize: bool) -> str:
    """Lowercase and optionally lemmatize a keyword."""
    if not lemmatize:
        return kw.lower()
    nlp = _get_nlp()
    doc = nlp(kw.lower())
    return " ".join(token.lemma_ for token in doc)


def apply_jaccard_filter(
    query_keywords: list[str],
    candidates: list[_T],
    threshold: float,
    min_keywords: int,
    lemmatize: bool = False,
) -> list[_T]:
    """Filter candidates by keyword Jaccard similarity.

    If query has fewer than min_keywords, skip filtering (not enough signal).
    When lemmatize=True, normalizes keywords to their root form before comparison
    (e.g., "renewals" and "renewal" are treated as identical).
    """
    if len(query_keywords) < min_keywords:
        return candidates
    query_set = {_normalize_keyword(kw, lemmatize=lemmatize) for kw in query_keywords}
    return [
        c for c in candidates
        if jaccard_similarity(
            query_set,
            {_normalize_keyword(kw, lemmatize=lemmatize) for kw in c.keywords},
        ) >= threshold
    ]
