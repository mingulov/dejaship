"""Unit tests for two-stage retrieval logic (no Docker required)."""
import math

from dejaship.embeddings import cosine_similarity


def test_cosine_similarity_identical():
    """Unit-norm identical vectors → similarity = 1.0."""
    v = [1.0, 0.0, 0.0]
    assert abs(cosine_similarity(v, v) - 1.0) < 1e-9


def test_cosine_similarity_orthogonal():
    """Orthogonal vectors → similarity = 0.0."""
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_similarity_opposite():
    """Anti-parallel vectors → similarity = -1.0."""
    assert abs(cosine_similarity([1.0, 0.0], [-1.0, 0.0]) - (-1.0)) < 1e-9


def test_cosine_similarity_partial():
    """Partial overlap at 45 degrees → similarity ≈ 0.707."""
    v1 = [1.0, 0.0]
    v2 = [math.sqrt(0.5), math.sqrt(0.5)]
    assert abs(cosine_similarity(v1, v2) - math.sqrt(0.5)) < 1e-6


def test_cosine_similarity_longer_vector():
    """Works with 768-dim vectors."""
    dims = 768
    v = [1.0 / dims**0.5] * dims  # unit vector
    assert abs(cosine_similarity(v, v) - 1.0) < 1e-6


def test_cosine_similarity_dimension_mismatch_raises():
    """Mismatched dimensions raise ValueError — no silent truncation."""
    import pytest
    with pytest.raises(ValueError, match="dimension mismatch"):
        cosine_similarity([1.0, 0.0, 0.0], [1.0, 0.0])
