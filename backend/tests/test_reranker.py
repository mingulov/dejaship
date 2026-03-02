"""Unit tests for ColBERT MaxSim reranker (no model loading required)."""
from unittest.mock import MagicMock, patch

import numpy as np

from dejaship.reranker import maxsim_score, rerank


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


class FakeCandidate:
    def __init__(self, text: str, name: str):
        self.text = text
        self.name = name


def _make_mock_reranker(query_embs: np.ndarray, doc_embs_map: dict[str, np.ndarray]):
    """Return a mock LateInteractionTextEmbedding for unit testing rerank()."""
    mock = MagicMock()
    mock.query_embed.return_value = iter([query_embs])

    # passage_embed receives a list of texts, returns iterator of arrays
    def passage_embed_fn(texts):
        return iter([doc_embs_map[text] for text in texts])

    mock.passage_embed.side_effect = passage_embed_fn
    return mock


def test_rerank_filters_by_threshold():
    """Candidates below threshold are excluded."""
    q = np.array([[1.0, 0.0]])  # 1 query token
    doc_high = np.array([[1.0, 0.0]])   # dot = 1.0 (above threshold)
    doc_low  = np.array([[0.0, 1.0]])   # dot = 0.0 (below threshold)

    candidates = [
        FakeCandidate("high", "high"),
        FakeCandidate("low", "low"),
    ]
    mock_model = _make_mock_reranker(q, {"high": doc_high, "low": doc_low})

    with patch("dejaship.reranker.get_reranker", return_value=mock_model):
        result = rerank(
            "query",
            candidates,
            threshold=0.5,
            text_fn=lambda c: c.text,
        )

    assert len(result) == 1
    assert result[0].name == "high"


def test_rerank_sorts_by_score_descending():
    """Results are ordered by score, highest first."""
    q = np.array([[1.0, 0.0]])
    doc_a = np.array([[0.9, 0.1]])  # score ~0.9
    doc_b = np.array([[0.6, 0.4]])  # score ~0.6
    doc_c = np.array([[0.8, 0.2]])  # score ~0.8

    candidates = [
        FakeCandidate("a", "a"),
        FakeCandidate("b", "b"),
        FakeCandidate("c", "c"),
    ]
    mock_model = _make_mock_reranker(q, {"a": doc_a, "b": doc_b, "c": doc_c})

    with patch("dejaship.reranker.get_reranker", return_value=mock_model):
        result = rerank(
            "query",
            candidates,
            threshold=0.0,
            text_fn=lambda c: c.text,
        )

    assert [r.name for r in result] == ["a", "c", "b"]


def test_rerank_empty_candidates_returns_empty():
    """Empty candidate list returns empty result."""
    mock_model = MagicMock()
    mock_model.query_embed.return_value = iter([np.array([[1.0, 0.0]])])
    mock_model.passage_embed.return_value = iter([])

    with patch("dejaship.reranker.get_reranker", return_value=mock_model):
        result = rerank("query", [], threshold=0.5, text_fn=lambda c: c.text)

    assert result == []


def test_rerank_all_below_threshold_returns_empty():
    """If all candidates score below threshold, returns empty list."""
    q = np.array([[1.0, 0.0]])
    doc = np.array([[0.0, 1.0]])  # dot = 0.0

    candidates = [FakeCandidate("doc", "doc")]
    mock_model = _make_mock_reranker(q, {"doc": doc})

    with patch("dejaship.reranker.get_reranker", return_value=mock_model):
        result = rerank("query", candidates, threshold=0.5, text_fn=lambda c: c.text)

    assert result == []
