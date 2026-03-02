"""Integration tests for feature-flagged search paths.

These test that the API doesn't crash when feature flags are enabled.
They don't assert quality (that's the ablation framework's job) — just correctness.
"""
import pytest
from httpx import AsyncClient

import dejaship.services as services_module


CLAIM_PAYLOAD = {
    "core_mechanic": "AI-powered HVAC maintenance scheduling with predictive failure detection",
    "keywords": ["hvac", "maintenance", "scheduling", "predictive", "field-service"],
}

CHECK_PAYLOAD = {
    "core_mechanic": "Smart building maintenance automation for commercial properties",
    "keywords": ["hvac", "maintenance", "automation", "building", "commercial"],
}


@pytest.fixture
async def seeded_db(client: AsyncClient):
    """Seed the DB with one claim so searches have something to find."""
    resp = await client.post("/v1/claim", json=CLAIM_PAYLOAD)
    assert resp.status_code == 200
    return resp.json()


@pytest.mark.asyncio
async def test_two_stage_retrieval_path(client: AsyncClient, seeded_db, monkeypatch):
    """ENABLE_TWO_STAGE_RETRIEVAL=True doesn't crash."""
    monkeypatch.setattr(services_module.settings, "ENABLE_TWO_STAGE_RETRIEVAL", True)
    monkeypatch.setattr(services_module.settings, "STAGE1_THRESHOLD", 0.55)
    monkeypatch.setattr(services_module.settings, "STAGE2_THRESHOLD", 0.65)
    monkeypatch.setattr(services_module.settings, "STAGE2_CANDIDATE_MULTIPLIER", 3)

    resp = await client.post("/v1/check", json=CHECK_PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert "neighborhood_density" in data
    assert "closest_active_claims" in data


@pytest.mark.asyncio
async def test_hybrid_search_path(client: AsyncClient, seeded_db, monkeypatch):
    """ENABLE_HYBRID_SEARCH=True doesn't crash."""
    monkeypatch.setattr(services_module.settings, "ENABLE_HYBRID_SEARCH", True)
    monkeypatch.setattr(services_module.settings, "HYBRID_RRF_K", 60)
    monkeypatch.setattr(services_module.settings, "HYBRID_FTS_WEIGHT", 0.3)

    resp = await client.post("/v1/check", json=CHECK_PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert "neighborhood_density" in data
    assert "closest_active_claims" in data


@pytest.mark.asyncio
async def test_jaccard_filter_path(client: AsyncClient, seeded_db, monkeypatch):
    """ENABLE_JACCARD_FILTER=True doesn't crash."""
    monkeypatch.setattr(services_module.settings, "ENABLE_JACCARD_FILTER", True)
    monkeypatch.setattr(services_module.settings, "JACCARD_THRESHOLD", 0.15)
    monkeypatch.setattr(services_module.settings, "JACCARD_MIN_KEYWORDS", 3)

    resp = await client.post("/v1/check", json=CHECK_PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert "neighborhood_density" in data
    assert "closest_active_claims" in data
