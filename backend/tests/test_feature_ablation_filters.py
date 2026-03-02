"""Unit tests for the Jaccard post-filter used in feature ablation."""
from tests.agent_sim._support.retrieval_analysis import RetrievalRecord
from tests.agent_sim.tools.evaluate_feature_ablation import _jaccard_filter


def _rec(kws: list[str]) -> tuple[RetrievalRecord, float]:
    return RetrievalRecord(brief_id="x", model_alias="m", vector=[], keywords=kws), 0.9


def test_jaccard_filter_passes_exact_overlap():
    f = _jaccard_filter(threshold=0.1, min_keywords=2)
    query_kws = ["saas", "billing", "subscription"]
    candidates = [_rec(["saas", "billing"])]
    result = f(query_kws, candidates)
    assert len(result) == 1  # 2 shared / 3 union ≈ 0.67 > 0.10


def test_jaccard_filter_drops_disjoint():
    f = _jaccard_filter(threshold=0.1, min_keywords=2)
    query_kws = ["saas", "billing"]
    candidates = [_rec(["healthcare", "imaging"])]
    result = f(query_kws, candidates)
    assert len(result) == 0  # 0 shared → Jaccard = 0


def test_jaccard_filter_skips_when_few_query_keywords():
    f = _jaccard_filter(threshold=0.5, min_keywords=3)
    query_kws = ["saas"]  # only 1, below min_keywords=3
    candidates = [_rec(["healthcare", "imaging"])]
    result = f(query_kws, candidates)
    assert len(result) == 1  # filter skipped, all pass


def test_jaccard_filter_passes_empty_candidate_keywords():
    f = _jaccard_filter(threshold=0.5, min_keywords=2)
    query_kws = ["saas", "billing"]
    candidates = [_rec([])]  # no keywords on candidate
    result = f(query_kws, candidates)
    assert len(result) == 1  # no keywords → pass through


def test_jaccard_filter_case_insensitive():
    f = _jaccard_filter(threshold=0.3, min_keywords=2)
    query_kws = ["SaaS", "Billing"]
    candidates = [_rec(["saas", "billing"])]  # lowercase
    result = f(query_kws, candidates)
    assert len(result) == 1  # 2/2 union = 1.0 > 0.3


def test_jaccard_filter_exact_threshold_passes():
    # query={"a","b","c"}, doc={"a"} → intersection=1, union=3, Jaccard=0.333
    f = _jaccard_filter(threshold=0.333, min_keywords=2)
    result = f(["a", "b", "c"], [_rec(["a"])])
    assert len(result) == 1


def test_jaccard_filter_below_threshold_drops():
    # query={"a","b","c","d"}, doc={"a"} → 1/4=0.25 < 0.30
    f = _jaccard_filter(threshold=0.30, min_keywords=2)
    result = f(["a", "b", "c", "d"], [_rec(["a"])])
    assert len(result) == 0
