"""Full-stack retrieval quality test using real pgvector + testcontainers.

Requires Docker. Run with:
    uv run pytest tests/agent_sim/test_coverage_max_fullstack.py -v -m slow -s

Measures FPR and recall of check_airspace() on the coverage-max corpus,
testing the full stack: pgvector HNSW index, embedding model, and all feature flags.

Strategy:
- For each brief, pick one fixture (first available model) to represent it
- Claim all briefs using those fixtures → inserts real embeddings into pgvector
- Check each brief using its own fixture payload
- Correlate returned mechanics back to brief_ids via a mechanic→brief_id lookup
- Measure recall and FPR using the same related_brief_ids logic as in-memory eval
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.agent_sim._support.catalog import (
    load_app_catalog,
    load_model_matrix,
    resolve_model_set,
)
from tests.agent_sim._support.fixture_store import load_fixture_index
from tests.agent_sim._support.retrieval_analysis import related_brief_ids

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def app_catalog():
    return load_app_catalog()


@pytest.fixture(scope="module")
def coverage_max_representative_fixtures(app_catalog):
    """Return one fixture per brief_id (first model with a stored fixture)."""
    model_matrix = load_model_matrix()
    fixture_index = load_fixture_index()
    selected_models = resolve_model_set(model_matrix, "coverage-max")

    # brief_id → (model_alias, fixture)
    by_brief: dict[str, tuple[str, object]] = {}
    for model_alias, _ in selected_models:
        for brief in app_catalog.briefs:
            if brief.id in by_brief:
                continue
            fx = fixture_index.get(brief_id=brief.id, model_alias=model_alias)
            if fx is not None:
                by_brief[brief.id] = (model_alias, fx)
    return by_brief


@pytest.mark.asyncio
async def test_fullstack_retrieval_quality(
    client: AsyncClient,
    app_catalog,
    coverage_max_representative_fixtures,
):
    """Populate DB with coverage-max claims, measure FPR/recall via check_airspace.

    Uses one representative fixture per brief to get a clean mechanic→brief_id mapping.
    """
    by_brief = coverage_max_representative_fixtures
    # mechanic_text → brief_id, for correlating check responses
    mechanic_to_brief: dict[str, str] = {}

    # Step 1: Claim all representative fixtures
    for brief_id, (model_alias, fx) in by_brief.items():
        payload = {
            "core_mechanic": fx.final_intent_input.core_mechanic,
            "keywords": fx.final_intent_input.keywords,
        }
        resp = await client.post("/v1/claim", json=payload)
        assert resp.status_code == 201, (
            f"claim failed for {brief_id}/{model_alias}: {resp.text}"
        )
        mechanic_to_brief[fx.final_intent_input.core_mechanic] = brief_id

    # Step 2: Check each brief and measure retrieval quality
    retrieved_total = 0
    false_positive_retrieved = 0
    relevant_available = 0
    relevant_retrieved = 0

    for brief_id, (_model_alias, fx) in by_brief.items():
        payload = {
            "core_mechanic": fx.final_intent_input.core_mechanic,
            "keywords": fx.final_intent_input.keywords,
        }
        resp = await client.post("/v1/check", json=payload)
        assert resp.status_code == 200, f"check failed for {brief_id}: {resp.text}"

        closest = resp.json().get("closest_active_claims", [])
        related_ids = related_brief_ids(app_catalog, brief_id)

        # Count how many claimed briefs are related to this query
        relevant_available += len(related_ids & set(by_brief))

        retrieved_total += len(closest)
        for claim in closest:
            mechanic = claim["mechanic"]
            returned_brief_id = mechanic_to_brief.get(mechanic)
            if returned_brief_id is None or returned_brief_id == brief_id:
                # Unknown mechanic or self-retrieval — not counted as relevant or FP
                continue
            if returned_brief_id in related_ids:
                relevant_retrieved += 1
            else:
                false_positive_retrieved += 1

    recall = relevant_retrieved / relevant_available if relevant_available > 0 else 0.0
    fpr = false_positive_retrieved / retrieved_total if retrieved_total > 0 else 0.0

    print(f"\nFull-stack retrieval quality (coverage-max, 1 fixture per brief):")
    print(f"  Briefs tested: {len(by_brief)}")
    print(f"  Retrieved total: {retrieved_total}")
    print(f"  Relevant available: {relevant_available}")
    print(f"  Recall@k: {recall:.4f}")
    print(f"  False positive rate: {fpr:.4f}")

    # Soft assertions: baseline quality floors — not hard SLOs
    assert recall >= 0.20, f"recall {recall:.4f} below minimum threshold of 0.20"
    assert fpr <= 0.95, f"fpr {fpr:.4f} above maximum threshold of 0.95"
