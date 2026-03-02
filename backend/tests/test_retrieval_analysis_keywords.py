"""Tests that RetrievalRecord carries keywords and mechanic_vector, and that
compute_cross_model_retrieval_matrix supports a pluggable post_filter callback."""
from tests.agent_sim._support.retrieval_analysis import (
    RetrievalRecord,
    compute_cross_model_retrieval_matrix,
)
from tests.agent_sim._support.types import AppBrief, AppCatalog


def test_retrieval_record_has_keywords_field():
    r = RetrievalRecord(brief_id="b", model_alias="m", vector=[0.1, 0.2])
    assert hasattr(r, "keywords")
    assert r.keywords == []


def test_retrieval_record_has_mechanic_vector_field():
    r = RetrievalRecord(brief_id="b", model_alias="m", vector=[0.1, 0.2])
    assert hasattr(r, "mechanic_vector")
    assert r.mechanic_vector == []


def test_retrieval_record_keywords_stored():
    r = RetrievalRecord(brief_id="b", model_alias="m", vector=[0.5], keywords=["saas", "billing"])
    assert r.keywords == ["saas", "billing"]


def _make_minimal_catalog() -> AppCatalog:
    """Return a minimal catalog using model_construct() to bypass Pydantic validation.

    The two briefs share an overlap group so related_brief_ids() returns non-empty sets.
    """
    brief_a = AppBrief.model_construct(
        id="brief-a",
        expected_overlap_group="billing",
        adjacent_overlap_groups=[],
    )
    brief_b = AppBrief.model_construct(
        id="brief-b",
        expected_overlap_group="billing",
        adjacent_overlap_groups=[],
    )
    return AppCatalog.model_construct(briefs=[brief_a, brief_b])


def test_post_filter_reduces_retrieved():
    """A post_filter that drops everything should produce empty retrieved set → FPR=0."""
    catalog = _make_minimal_catalog()
    vec = [1.0, 0.0]
    records = [
        RetrievalRecord(brief_id="brief-a", model_alias="model-x", vector=vec, keywords=["billing"]),
        RetrievalRecord(brief_id="brief-b", model_alias="model-y", vector=vec, keywords=["other"]),
    ]
    result = compute_cross_model_retrieval_matrix(
        catalog=catalog,
        records=records,
        threshold=0.0,
        top_k=10,
        post_filter=lambda kws, cands: [],
    )
    assert result["summary"]["false_positive_rate"] == 0.0  # type: ignore[index]


def test_post_filter_none_behaves_as_baseline():
    """post_filter=None must reproduce the same results as omitting the argument."""
    catalog = _make_minimal_catalog()
    vec = [1.0, 0.0]
    records = [
        RetrievalRecord(brief_id="brief-a", model_alias="model-x", vector=vec, keywords=["billing"]),
        RetrievalRecord(brief_id="brief-b", model_alias="model-y", vector=vec, keywords=["billing"]),
    ]
    baseline = compute_cross_model_retrieval_matrix(
        catalog=catalog, records=records, threshold=0.0, top_k=10
    )
    with_none = compute_cross_model_retrieval_matrix(
        catalog=catalog, records=records, threshold=0.0, top_k=10, post_filter=None
    )
    assert baseline["summary"] == with_none["summary"]  # type: ignore[index]
