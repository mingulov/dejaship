"""Unit tests for Reciprocal Rank Fusion (no DB required)."""
from dejaship.fts import rrf_score


def test_rrf_score_equal_ranks_balanced():
    """With equal ranks and 50/50 weight, both components contribute equally."""
    score = rrf_score(1, 1, fts_weight=0.5, k=60)
    expected = 0.5 / 61 + 0.5 / 61
    assert abs(score - expected) < 1e-9


def test_rrf_score_vector_only_weight():
    """With fts_weight=0, only vector rank matters."""
    score = rrf_score(1, 100, fts_weight=0.0, k=60)
    expected = 1.0 / 61
    assert abs(score - expected) < 1e-9


def test_rrf_score_fts_only_weight():
    """With fts_weight=1, only FTS rank matters."""
    score = rrf_score(100, 1, fts_weight=1.0, k=60)
    expected = 1.0 / 61
    assert abs(score - expected) < 1e-9


def test_rrf_score_rank1_beats_rank10():
    """Rank 1 scores higher than rank 10 for same weight."""
    score_rank1 = rrf_score(1, 1, fts_weight=0.5, k=60)
    score_rank10 = rrf_score(10, 10, fts_weight=0.5, k=60)
    assert score_rank1 > score_rank10


def test_rrf_score_monotonically_decreasing():
    """Higher rank number -> lower score (worse match)."""
    scores = [rrf_score(i, i, fts_weight=0.3, k=60) for i in range(1, 11)]
    assert all(scores[i] > scores[i + 1] for i in range(len(scores) - 1))


def test_rrf_score_returns_float():
    """rrf_score always returns float."""
    result = rrf_score(1, 1, fts_weight=0.3, k=60)
    assert isinstance(result, float)


def test_rrf_score_fts_weight_affects_contribution():
    """Increasing fts_weight shifts score toward FTS component."""
    # Case: vector rank 1 (perfect), fts rank 10 (bad)
    # Higher fts_weight -> lower overall score
    score_low_fts = rrf_score(1, 10, fts_weight=0.1, k=60)
    score_high_fts = rrf_score(1, 10, fts_weight=0.9, k=60)
    assert score_low_fts > score_high_fts
