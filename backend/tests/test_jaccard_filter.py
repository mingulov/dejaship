"""Unit tests for keyword Jaccard post-filter."""
from dejaship.filters import apply_jaccard_filter, jaccard_similarity


def test_jaccard_similarity_identical():
    assert jaccard_similarity({"a", "b", "c"}, {"a", "b", "c"}) == 1.0


def test_jaccard_similarity_disjoint():
    assert jaccard_similarity({"a", "b"}, {"c", "d"}) == 0.0


def test_jaccard_similarity_partial():
    result = jaccard_similarity({"a", "b", "c"}, {"b", "c", "d"})
    assert abs(result - 0.5) < 0.001


def test_jaccard_similarity_empty_a():
    assert jaccard_similarity(set(), {"a"}) == 0.0


def test_jaccard_similarity_empty_b():
    assert jaccard_similarity({"a"}, set()) == 0.0


class FakeRecord:
    def __init__(self, keywords):
        self.keywords = keywords


def test_apply_jaccard_filter_skips_when_few_query_keywords():
    """Filter is skipped when query has fewer than min_keywords — all candidates returned."""
    candidates = [FakeRecord(["x", "y", "z"]), FakeRecord(["a", "b", "c"])]
    result = apply_jaccard_filter(["only-one"], candidates, threshold=0.15, min_keywords=3)
    assert result == candidates  # unchanged


def test_apply_jaccard_filter_removes_disjoint():
    """Candidates with zero keyword overlap are filtered out."""
    candidates = [
        FakeRecord(["hvac", "technician", "dispatch"]),  # no overlap with query
        FakeRecord(["subscription", "recurring", "billing"]),  # some overlap
    ]
    query = ["subscription", "saas", "billing", "recurring"]
    result = apply_jaccard_filter(query, candidates, threshold=0.15, min_keywords=3)
    assert len(result) == 1
    assert result[0].keywords == ["subscription", "recurring", "billing"]


def test_apply_jaccard_filter_keeps_overlapping():
    """Candidates above threshold are kept."""
    candidates = [FakeRecord(["a", "b", "c", "d"])]
    query = ["a", "b", "c", "e"]  # 3/5 union, Jaccard=0.6
    result = apply_jaccard_filter(query, candidates, threshold=0.5, min_keywords=2)
    assert result == candidates


def test_apply_jaccard_filter_case_insensitive():
    """Keyword matching is case-insensitive."""
    candidates = [FakeRecord(["HVAC", "Subscription"])]
    query = ["hvac", "subscription", "billing"]
    result = apply_jaccard_filter(query, candidates, threshold=0.3, min_keywords=2)
    assert len(result) == 1


def test_apply_jaccard_filter_exact_threshold():
    """Candidates at exactly the threshold are kept."""
    # set_a = {a, b}, set_b = {b, c} → intersection={b}, union={a,b,c} → J=1/3 ≈ 0.333
    candidates = [FakeRecord(["b", "c"])]
    result = apply_jaccard_filter(["a", "b"], candidates, threshold=1/3, min_keywords=1)
    assert len(result) == 1


def test_apply_jaccard_filter_empty_candidates():
    result = apply_jaccard_filter(["a", "b", "c"], [], threshold=0.15, min_keywords=3)
    assert result == []


def test_apply_jaccard_filter_skips_at_min_keywords_minus_one():
    """Query of exactly min_keywords - 1 skips the filter (boundary: < not <=)."""
    candidates = [FakeRecord(["x", "y", "z"])]
    result = apply_jaccard_filter(["a", "b"], candidates, threshold=0.9, min_keywords=3)
    assert result == candidates  # 2 < 3, filter skipped


def test_apply_jaccard_filter_applies_at_min_keywords():
    """Query of exactly min_keywords does apply the filter."""
    candidates = [FakeRecord(["x", "y", "z"])]
    result = apply_jaccard_filter(["a", "b", "c"], candidates, threshold=0.9, min_keywords=3)
    assert result == []  # 3 >= 3, filter active; no overlap → empty


def test_apply_jaccard_filter_lemmatizes_when_enabled():
    """With lemmatize=True, 'renewals' and 'renewal' match as the same root."""
    class Claim:
        def __init__(self, keywords):
            self.keywords = keywords

    # Query uses "renewal" (singular), claim uses "renewals" (plural)
    query_keywords = ["crm", "renewal", "billing"]
    candidates = [
        Claim(["crm", "renewals", "billing"]),  # plural — should match with lemmatization
        Claim(["analytics", "dashboard"]),         # no overlap — should not match
    ]

    result = apply_jaccard_filter(
        query_keywords=query_keywords,
        candidates=candidates,
        threshold=0.3,
        min_keywords=2,
        lemmatize=True,
    )
    assert len(result) == 1
    assert result[0].keywords == ["crm", "renewals", "billing"]


def test_apply_jaccard_filter_no_lemmatize_by_default():
    """Without lemmatize=True, 'renewals' and 'renewal' do NOT match."""
    class Claim:
        def __init__(self, keywords):
            self.keywords = keywords

    query_keywords = ["crm", "renewal", "billing"]
    candidates = [
        Claim(["crm", "renewals", "billing"]),
    ]

    # At threshold=0.5: query_set={"crm","renewal","billing"}, claim_set={"crm","renewals","billing"}
    # intersection={"crm","billing"} (2), union={"crm","renewal","renewals","billing"} (4) → J=0.5
    result = apply_jaccard_filter(
        query_keywords=query_keywords,
        candidates=candidates,
        threshold=0.6,  # higher threshold that would not pass without lemmatization
        min_keywords=2,
        lemmatize=False,
    )
    assert len(result) == 0  # doesn't match without lemmatization at threshold=0.6
