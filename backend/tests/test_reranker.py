"""Unit tests for ColBERT MaxSim reranker (no model loading required)."""
import numpy as np
import pytest

from dejaship.reranker import maxsim_score


def test_maxsim_identical_query_doc():
    """When query = doc, each token matches itself exactly → high score."""
    Q = np.array([[1.0, 0.0], [0.0, 1.0]])  # 2 query tokens, dim=2
    D = np.array([[1.0, 0.0], [0.0, 1.0]])  # 2 doc tokens, dim=2
    score = maxsim_score(Q, D)
    # Each query token gets max sim of 1.0, sum = 2.0
    assert abs(score - 2.0) < 1e-6


def test_maxsim_orthogonal():
    """Orthogonal embeddings → max sim = 0 → score = 0."""
    Q = np.array([[1.0, 0.0]])  # 1 query token
    D = np.array([[0.0, 1.0]])  # 1 doc token
    score = maxsim_score(Q, D)
    assert score == 0.0


def test_maxsim_partial_overlap():
    """Query token finds best match in longer document."""
    Q = np.array([[1.0, 0.0]])  # 1 query token
    D = np.array([[0.5, 0.5], [1.0, 0.0], [0.0, 1.0]])  # 3 doc tokens
    score = maxsim_score(Q, D)
    # Best match for [1.0, 0.0] is [1.0, 0.0] with dot=1.0
    assert abs(score - 1.0) < 1e-6


def test_maxsim_multiple_query_tokens():
    """MaxSim sums over all query tokens."""
    Q = np.array([[1.0, 0.0], [0.0, 1.0]])  # 2 query tokens
    D = np.array([[1.0, 0.0], [0.0, 1.0]])  # exact match
    score = maxsim_score(Q, D)
    assert abs(score - 2.0) < 1e-6


def test_maxsim_each_query_token_finds_best():
    """Each query token independently finds its best doc token."""
    # Query: [[1,0], [0,1]]
    # Doc: [[0.8, 0.2], [0.1, 0.9]]
    Q = np.array([[1.0, 0.0], [0.0, 1.0]])
    D = np.array([[0.8, 0.2], [0.1, 0.9]])
    score = maxsim_score(Q, D)
    # q[0]=[1,0]: max dot with D → max(0.8, 0.1) = 0.8
    # q[1]=[0,1]: max dot with D → max(0.2, 0.9) = 0.9
    # total = 1.7
    assert abs(score - 1.7) < 1e-6


def test_maxsim_returns_float():
    """maxsim_score always returns float."""
    Q = np.array([[1.0, 0.0]])
    D = np.array([[1.0, 0.0]])
    result = maxsim_score(Q, D)
    assert isinstance(result, float)
