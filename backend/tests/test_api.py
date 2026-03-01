import pytest


SAMPLE_KEYWORDS_SEO = ["seo", "plumber", "local-business", "marketing", "website"]
SAMPLE_KEYWORDS_KNITTING = ["knitting", "inventory", "shop-management", "yarn", "crafts"]


@pytest.mark.asyncio
async def test_check_empty_db(client):
    """Returns zero density on fresh database."""
    resp = await client.post("/v1/check", json={
        "core_mechanic": "seo tool for plumbers",
        "keywords": SAMPLE_KEYWORDS_SEO,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["neighborhood_density"]["in_progress"] == 0
    assert data["neighborhood_density"]["shipped"] == 0
    assert data["neighborhood_density"]["abandoned"] == 0
    assert data["closest_active_claims"] == []


@pytest.mark.asyncio
async def test_claim_returns_token(client):
    """Creates record and returns claim_id + edit_token."""
    resp = await client.post("/v1/claim", json={
        "core_mechanic": "seo tool for plumbers",
        "keywords": SAMPLE_KEYWORDS_SEO,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "claim_id" in data
    assert "edit_token" in data
    assert data["status"] == "in_progress"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_check_finds_similar(client):
    """Claim one idea, check a similar idea - density > 0."""
    await client.post("/v1/claim", json={
        "core_mechanic": "seo tool for plumbers",
        "keywords": SAMPLE_KEYWORDS_SEO,
    })
    resp = await client.post("/v1/check", json={
        "core_mechanic": "seo for local plumbing businesses",
        "keywords": ["seo", "plumbing", "local-business", "website", "marketing"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["neighborhood_density"]["in_progress"] >= 1


@pytest.mark.asyncio
async def test_check_ignores_dissimilar(client):
    """Claim one idea, check a totally different idea - density = 0."""
    await client.post("/v1/claim", json={
        "core_mechanic": "seo tool for plumbers",
        "keywords": SAMPLE_KEYWORDS_SEO,
    })
    resp = await client.post("/v1/check", json={
        "core_mechanic": "knitting inventory predictor",
        "keywords": SAMPLE_KEYWORDS_KNITTING,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["neighborhood_density"]["in_progress"] == 0


@pytest.mark.asyncio
async def test_update_shipped(client):
    """Update claim to shipped with URL."""
    claim_resp = await client.post("/v1/claim", json={
        "core_mechanic": "seo tool for plumbers",
        "keywords": SAMPLE_KEYWORDS_SEO,
    })
    claim = claim_resp.json()
    resp = await client.post("/v1/update", json={
        "claim_id": claim["claim_id"],
        "edit_token": claim["edit_token"],
        "status": "shipped",
        "resolution_url": "https://example.com",
    })
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_update_abandoned(client):
    """Update claim to abandoned."""
    claim_resp = await client.post("/v1/claim", json={
        "core_mechanic": "seo tool for plumbers",
        "keywords": SAMPLE_KEYWORDS_SEO,
    })
    claim = claim_resp.json()
    resp = await client.post("/v1/update", json={
        "claim_id": claim["claim_id"],
        "edit_token": claim["edit_token"],
        "status": "abandoned",
    })
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_update_wrong_token(client):
    """Reject update with wrong edit_token - 403."""
    claim_resp = await client.post("/v1/claim", json={
        "core_mechanic": "seo tool for plumbers",
        "keywords": SAMPLE_KEYWORDS_SEO,
    })
    claim = claim_resp.json()
    resp = await client.post("/v1/update", json={
        "claim_id": claim["claim_id"],
        "edit_token": "wrong-token",
        "status": "shipped",
    })
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_invalid_transition(client):
    """Cannot transition from abandoned back to shipped."""
    claim_resp = await client.post("/v1/claim", json={
        "core_mechanic": "seo tool for plumbers",
        "keywords": SAMPLE_KEYWORDS_SEO,
    })
    claim = claim_resp.json()
    await client.post("/v1/update", json={
        "claim_id": claim["claim_id"],
        "edit_token": claim["edit_token"],
        "status": "abandoned",
    })
    resp = await client.post("/v1/update", json={
        "claim_id": claim["claim_id"],
        "edit_token": claim["edit_token"],
        "status": "shipped",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_keyword_validation_too_few(client):
    """Reject fewer than 5 keywords."""
    resp = await client.post("/v1/check", json={
        "core_mechanic": "seo tool",
        "keywords": ["seo", "plumber"],
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_keyword_validation_bad_format(client):
    """Reject keywords with invalid characters."""
    resp = await client.post("/v1/check", json={
        "core_mechanic": "seo tool",
        "keywords": ["SEO", "Plumber", "local business", "MARKETING", "website"],
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_health(client):
    """Health endpoint returns ok."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
