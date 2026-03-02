import pytest

from tests.agent_sim._support.retrieval_analysis import (
    RetrievalRecord,
    compute_cross_model_retrieval_matrix,
    cosine_similarity,
    evaluate_thresholds,
)


pytestmark = pytest.mark.agent_sim


def test_cosine_similarity_scores_identical_vectors():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


def test_cross_model_retrieval_matrix_scores_exact_and_related_hits(agent_sim_catalog):
    records = [
        RetrievalRecord(brief_id="hvac-service-plan-ops", model_alias="model-a", vector=[1.0, 0.0]),
        RetrievalRecord(brief_id="pest-control-renewal-engine", model_alias="model-a", vector=[0.96, 0.04]),
        RetrievalRecord(brief_id="hvac-service-plan-ops", model_alias="model-b", vector=[0.99, 0.01]),
        RetrievalRecord(brief_id="pest-control-renewal-engine", model_alias="model-b", vector=[0.95, 0.05]),
    ]

    result = compute_cross_model_retrieval_matrix(
        catalog=agent_sim_catalog,
        records=records,
        threshold=0.9,
        top_k=2,
    )

    pair = result["matrix"]["model-a"]["model-b"]
    assert pair["exact_top1_rate"] == 1.0
    assert pair["exact_threshold_rate"] == 1.0
    assert pair["false_positive_rate"] >= 0.0
    assert pair["recall_at_k"] >= 0.0
    assert "average_first_relevant_rank" in pair
    assert "asymmetry" in result


def test_evaluate_thresholds_returns_recommendation(agent_sim_catalog):
    records = [
        RetrievalRecord(brief_id="hvac-service-plan-ops", model_alias="model-a", vector=[1.0, 0.0]),
        RetrievalRecord(brief_id="pest-control-renewal-engine", model_alias="model-a", vector=[0.95, 0.05]),
        RetrievalRecord(brief_id="hvac-service-plan-ops", model_alias="model-b", vector=[1.0, 0.0]),
        RetrievalRecord(brief_id="pest-control-renewal-engine", model_alias="model-b", vector=[0.95, 0.05]),
    ]

    result = evaluate_thresholds(
        catalog=agent_sim_catalog,
        records=records,
        thresholds=[0.5, 0.9],
        top_k=2,
    )

    assert result["recommended_threshold"] in {0.5, 0.9}
    assert len(result["evaluations"]) == 2
