"""Unit tests for the Jaccard and mechanic rerank post-filters used in feature ablation."""
from tests.agent_sim._support.retrieval_analysis import RetrievalRecord
from tests.agent_sim.tools.evaluate_feature_ablation import _jaccard_filter, _mechanic_rerank_filter


def _rec(kws: list[str], mech_vec: list[float] | None = None) -> tuple[RetrievalRecord, float]:
    return RetrievalRecord(
        brief_id="x", model_alias="m", vector=[], keywords=kws,
        mechanic_vector=mech_vec or [],
    ), 0.9


def _query(kws: list[str], mech_vec: list[float] | None = None) -> RetrievalRecord:
    return RetrievalRecord(
        brief_id="q", model_alias="m", vector=[], keywords=kws,
        mechanic_vector=mech_vec or [],
    )


def test_jaccard_filter_passes_exact_overlap():
    f = _jaccard_filter(threshold=0.1, min_keywords=2)
    q = _query(["saas", "billing", "subscription"])
    candidates = [_rec(["saas", "billing"])]
    result = f(q, candidates)
    assert len(result) == 1  # 2 shared / 3 union ≈ 0.67 > 0.10


def test_jaccard_filter_drops_disjoint():
    f = _jaccard_filter(threshold=0.1, min_keywords=2)
    q = _query(["saas", "billing"])
    candidates = [_rec(["healthcare", "imaging"])]
    result = f(q, candidates)
    assert len(result) == 0  # 0 shared → Jaccard = 0


def test_jaccard_filter_skips_when_few_query_keywords():
    f = _jaccard_filter(threshold=0.5, min_keywords=3)
    q = _query(["saas"])  # only 1, below min_keywords=3
    candidates = [_rec(["healthcare", "imaging"])]
    result = f(q, candidates)
    assert len(result) == 1  # filter skipped, all pass


def test_jaccard_filter_passes_empty_candidate_keywords():
    f = _jaccard_filter(threshold=0.5, min_keywords=2)
    q = _query(["saas", "billing"])
    candidates = [_rec([])]  # no keywords on candidate
    result = f(q, candidates)
    assert len(result) == 1  # no keywords → pass through


def test_jaccard_filter_case_insensitive():
    f = _jaccard_filter(threshold=0.3, min_keywords=2)
    q = _query(["SaaS", "Billing"])
    candidates = [_rec(["saas", "billing"])]  # lowercase
    result = f(q, candidates)
    assert len(result) == 1  # 2/2 union = 1.0 > 0.3


def test_jaccard_filter_exact_threshold_passes():
    # query={"a","b","c"}, doc={"a"} → intersection=1, union=3, Jaccard=0.333
    f = _jaccard_filter(threshold=0.333, min_keywords=2)
    result = f(_query(["a", "b", "c"]), [_rec(["a"])])
    assert len(result) == 1


def test_jaccard_filter_below_threshold_drops():
    # query={"a","b","c","d"}, doc={"a"} → 1/4=0.25 < 0.30
    f = _jaccard_filter(threshold=0.30, min_keywords=2)
    result = f(_query(["a", "b", "c", "d"]), [_rec(["a"])])
    assert len(result) == 0


def test_mechanic_rerank_passes_similar():
    f = _mechanic_rerank_filter(threshold=0.5)
    q = _query([], mech_vec=[1.0, 0.0])
    candidates = [_rec([], mech_vec=[0.9, 0.1])]  # high cosine sim
    result = f(q, candidates)
    assert len(result) == 1


def test_mechanic_rerank_drops_dissimilar():
    f = _mechanic_rerank_filter(threshold=0.9)
    q = _query([], mech_vec=[1.0, 0.0])
    candidates = [_rec([], mech_vec=[0.0, 1.0])]  # orthogonal → sim=0
    result = f(q, candidates)
    assert len(result) == 0


def test_mechanic_rerank_passes_empty_mechanic_vector():
    f = _mechanic_rerank_filter(threshold=0.5)
    q = _query([], mech_vec=[1.0, 0.0])
    candidates = [_rec([], mech_vec=[])]  # no mechanic vector → pass through
    result = f(q, candidates)
    assert len(result) == 1
