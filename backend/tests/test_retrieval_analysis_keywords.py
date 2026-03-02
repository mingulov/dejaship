"""Tests that RetrievalRecord carries keywords and mechanic_vector."""
from tests.agent_sim._support.retrieval_analysis import RetrievalRecord


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
