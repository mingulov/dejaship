import uuid

import pytest
from httpx import AsyncClient
from starlette.requests import Request

from dejaship.config import settings
from dejaship.limiter import get_client_ip


SAMPLE_KEYWORDS_SEO = ["seo", "plumber", "local-business", "marketing", "website"]
SAMPLE_KEYWORDS_KNITTING = ["knitting", "inventory", "shop-management", "yarn", "crafts"]
SAMPLE_KEYWORDS_CRYPTO = ["blockchain", "defi", "smart-contracts", "ethereum", "token"]


# --- Check Endpoint ---


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
async def test_check_density_by_status(client):
    """Density counts are correct per status."""
    # Create 2 in_progress + 1 shipped + 1 abandoned
    claim1 = (await client.post("/v1/claim", json={
        "core_mechanic": "seo tool for plumbers",
        "keywords": SAMPLE_KEYWORDS_SEO,
    })).json()
    claim2 = (await client.post("/v1/claim", json={
        "core_mechanic": "seo helper for plumbing",
        "keywords": ["seo", "plumber", "local-seo", "marketing", "website"],
    })).json()
    await client.post("/v1/claim", json={
        "core_mechanic": "seo platform for local plumbers",
        "keywords": ["seo", "plumber", "local-business", "online", "digital"],
    })

    # Ship one
    await client.post("/v1/update", json={
        "claim_id": claim1["claim_id"],
        "edit_token": claim1["edit_token"],
        "status": "shipped",
        "resolution_url": "https://example.com",
    })
    # Abandon one
    await client.post("/v1/update", json={
        "claim_id": claim2["claim_id"],
        "edit_token": claim2["edit_token"],
        "status": "abandoned",
    })

    # Check - claim3 still in_progress, claim1 shipped, claim2 abandoned
    resp = await client.post("/v1/check", json={
        "core_mechanic": "seo for plumbing services",
        "keywords": ["seo", "plumber", "local-business", "marketing", "web"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["neighborhood_density"]["in_progress"] >= 1
    assert data["neighborhood_density"]["shipped"] >= 1
    assert data["neighborhood_density"]["abandoned"] >= 1


@pytest.mark.asyncio
async def test_check_excludes_abandoned_from_closest(client):
    """Abandoned claims are not included in closest_active_claims."""
    claim = (await client.post("/v1/claim", json={
        "core_mechanic": "seo tool for plumbers",
        "keywords": SAMPLE_KEYWORDS_SEO,
    })).json()
    await client.post("/v1/update", json={
        "claim_id": claim["claim_id"],
        "edit_token": claim["edit_token"],
        "status": "abandoned",
    })

    resp = await client.post("/v1/check", json={
        "core_mechanic": "seo for local plumbing businesses",
        "keywords": ["seo", "plumbing", "local-business", "website", "marketing"],
    })
    data = resp.json()
    # Abandoned should show in density but NOT in closest_active_claims
    assert data["neighborhood_density"]["abandoned"] >= 1
    for claim_item in data["closest_active_claims"]:
        assert claim_item["status"] != "abandoned"


@pytest.mark.asyncio
async def test_check_closest_includes_shipped(client):
    """Shipped claims are included in closest_active_claims."""
    claim = (await client.post("/v1/claim", json={
        "core_mechanic": "seo tool for plumbers",
        "keywords": SAMPLE_KEYWORDS_SEO,
    })).json()
    await client.post("/v1/update", json={
        "claim_id": claim["claim_id"],
        "edit_token": claim["edit_token"],
        "status": "shipped",
        "resolution_url": "https://example.com",
    })

    resp = await client.post("/v1/check", json={
        "core_mechanic": "seo for local plumbing businesses",
        "keywords": ["seo", "plumbing", "local-business", "website", "marketing"],
    })
    data = resp.json()
    statuses = [c["status"] for c in data["closest_active_claims"]]
    assert "shipped" in statuses


@pytest.mark.asyncio
async def test_check_closest_has_age_hours(client):
    """closest_active_claims entries have age_hours field."""
    await client.post("/v1/claim", json={
        "core_mechanic": "seo tool for plumbers",
        "keywords": SAMPLE_KEYWORDS_SEO,
    })
    resp = await client.post("/v1/check", json={
        "core_mechanic": "seo for local plumbing businesses",
        "keywords": ["seo", "plumbing", "local-business", "website", "marketing"],
    })
    data = resp.json()
    assert len(data["closest_active_claims"]) >= 1
    for claim_item in data["closest_active_claims"]:
        assert "age_hours" in claim_item
        assert isinstance(claim_item["age_hours"], (int, float))
        assert claim_item["age_hours"] >= 0


# --- Claim Endpoint ---


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
async def test_claim_creates_separate_records(client):
    """Same input twice creates 2 different records with different IDs."""
    payload = {
        "core_mechanic": "seo tool for plumbers",
        "keywords": SAMPLE_KEYWORDS_SEO,
    }
    resp1 = await client.post("/v1/claim", json=payload)
    resp2 = await client.post("/v1/claim", json=payload)
    assert resp1.json()["claim_id"] != resp2.json()["claim_id"]


@pytest.mark.asyncio
async def test_claim_tokens_differ(client):
    """Each claim gets a unique edit_token."""
    payload = {
        "core_mechanic": "seo tool for plumbers",
        "keywords": SAMPLE_KEYWORDS_SEO,
    }
    resp1 = await client.post("/v1/claim", json=payload)
    resp2 = await client.post("/v1/claim", json=payload)
    assert resp1.json()["edit_token"] != resp2.json()["edit_token"]


# --- Update Endpoint ---


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
async def test_update_nonexistent_claim(client):
    """Update a claim that doesn't exist returns 400."""
    resp = await client.post("/v1/update", json={
        "claim_id": str(uuid.uuid4()),
        "edit_token": "some-token",
        "status": "shipped",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_update_shipped_to_shipped(client):
    """Cannot transition from shipped to shipped again."""
    claim = (await client.post("/v1/claim", json={
        "core_mechanic": "seo tool for plumbers",
        "keywords": SAMPLE_KEYWORDS_SEO,
    })).json()
    await client.post("/v1/update", json={
        "claim_id": claim["claim_id"],
        "edit_token": claim["edit_token"],
        "status": "shipped",
        "resolution_url": "https://example.com",
    })
    resp = await client.post("/v1/update", json={
        "claim_id": claim["claim_id"],
        "edit_token": claim["edit_token"],
        "status": "shipped",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_update_shipped_to_abandoned(client):
    """Cannot transition from shipped to abandoned."""
    claim = (await client.post("/v1/claim", json={
        "core_mechanic": "seo tool for plumbers",
        "keywords": SAMPLE_KEYWORDS_SEO,
    })).json()
    await client.post("/v1/update", json={
        "claim_id": claim["claim_id"],
        "edit_token": claim["edit_token"],
        "status": "shipped",
        "resolution_url": "https://example.com",
    })
    resp = await client.post("/v1/update", json={
        "claim_id": claim["claim_id"],
        "edit_token": claim["edit_token"],
        "status": "abandoned",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_update_invalid_status_value(client):
    """Status must be shipped or abandoned, not arbitrary string."""
    claim = (await client.post("/v1/claim", json={
        "core_mechanic": "seo tool for plumbers",
        "keywords": SAMPLE_KEYWORDS_SEO,
    })).json()
    resp = await client.post("/v1/update", json={
        "claim_id": claim["claim_id"],
        "edit_token": claim["edit_token"],
        "status": "in_progress",
    })
    assert resp.status_code == 422


# --- Validation ---


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
async def test_keyword_validation_too_short(client):
    """Reject keywords shorter than 3 characters."""
    resp = await client.post("/v1/check", json={
        "core_mechanic": "seo tool",
        "keywords": ["ab", "plumber", "local-business", "marketing", "website"],
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_keyword_validation_too_long(client):
    """Reject keywords longer than 40 characters."""
    long_keyword = "a" * 41
    resp = await client.post("/v1/check", json={
        "core_mechanic": "seo tool",
        "keywords": [long_keyword, "plumber", "local-business", "marketing", "website"],
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_core_mechanic_too_long(client):
    """Reject core_mechanic longer than 250 characters."""
    resp = await client.post("/v1/check", json={
        "core_mechanic": "x" * 251,
        "keywords": SAMPLE_KEYWORDS_SEO,
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_core_mechanic_empty(client):
    """Reject empty core_mechanic."""
    resp = await client.post("/v1/check", json={
        "core_mechanic": "",
        "keywords": SAMPLE_KEYWORDS_SEO,
    })
    assert resp.status_code == 422


# --- MCP Endpoint ---


@pytest.mark.asyncio
async def test_mcp_endpoint_mounted(client):
    """MCP streamable HTTP endpoint at /mcp responds (not 404)."""
    # Send a JSON-RPC request to initialize
    resp = await client.post("/mcp", json={
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0.1.0"},
        },
    })
    # Should not be 404 - the route is mounted
    assert resp.status_code != 404


@pytest.mark.asyncio
async def test_mcp_endpoint_rate_limited(client, monkeypatch):
    """MCP endpoint uses the dedicated rate limit."""
    monkeypatch.setattr(settings, "RATE_LIMIT_MCP", "1/minute")

    first = await client.post("/mcp", json={
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0.1.0"},
        },
    })
    second = await client.post("/mcp", json={
        "jsonrpc": "2.0",
        "id": 2,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0.1.0"},
        },
    })

    assert first.status_code != 429
    assert second.status_code == 429


# --- Boundary Value Tests ---


@pytest.mark.asyncio
async def test_keyword_exactly_5_accepted(client):
    """Exactly 5 keywords (minimum) should succeed."""
    resp = await client.post("/v1/check", json={
        "core_mechanic": "seo tool",
        "keywords": ["seo", "plumber", "local-business", "marketing", "website"],
    })
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_keyword_exactly_min_length_accepted(client):
    """Keyword of exactly 3 characters should be valid."""
    resp = await client.post("/v1/check", json={
        "core_mechanic": "seo tool",
        "keywords": ["seo", "plumber", "local-business", "marketing", "web"],
    })
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_keyword_exactly_max_length_accepted(client):
    """Keyword of exactly 40 characters should be valid."""
    kw40 = "a" * 40
    resp = await client.post("/v1/check", json={
        "core_mechanic": "seo tool",
        "keywords": [kw40, "plumber", "local-business", "marketing", "website"],
    })
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_keyword_with_hyphens_accepted(client):
    """Keywords containing hyphens like 'local-business' are valid."""
    resp = await client.post("/v1/check", json={
        "core_mechanic": "tool for local businesses",
        "keywords": ["local-business", "small-business", "b2c", "marketplace", "commerce"],
    })
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_claim_more_than_10_keywords_accepted(client):
    """More than 10 keywords should be accepted (11+ are included once, not repeated)."""
    keywords = [f"kw{i}" for i in range(15)]
    resp = await client.post("/v1/claim", json={
        "core_mechanic": "tool with many keywords",
        "keywords": keywords,
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"


@pytest.mark.asyncio
async def test_check_closest_ordered_by_similarity(client):
    """closest_active_claims are ordered closest first (most similar)."""
    # Claim a very similar and a less similar project
    await client.post("/v1/claim", json={
        "core_mechanic": "seo tool for plumbers",
        "keywords": SAMPLE_KEYWORDS_SEO,
    })
    await client.post("/v1/claim", json={
        "core_mechanic": "blockchain defi platform",
        "keywords": SAMPLE_KEYWORDS_CRYPTO,
    })

    resp = await client.post("/v1/check", json={
        "core_mechanic": "seo for local plumbing businesses",
        "keywords": ["seo", "plumbing", "local-business", "website", "marketing"],
    })
    data = resp.json()
    claims = data["closest_active_claims"]
    # If more than one result, the most relevant (SEO) should appear first
    if len(claims) >= 2:
        assert "plumb" in claims[0]["mechanic"].lower() or "seo" in claims[0]["mechanic"].lower()


# --- Health Endpoint ---


@pytest.mark.asyncio
async def test_health(client):
    """Health endpoint returns ok."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_ready(client):
    """Readiness endpoint checks DB and embedding model."""
    resp = await client.get("/ready")
    assert resp.status_code == 200
    assert resp.json() == {
        "status": "ok",
        "checks": {"database": "ok", "embeddings": "ok"},
    }


@pytest.mark.asyncio
async def test_ready_reports_failures(client, monkeypatch):
    """Readiness endpoint returns 503 when a dependency is unavailable."""

    class BrokenConnect:
        async def __aenter__(self):
            raise RuntimeError("db down")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class BrokenEngine:
        def connect(self):
            return BrokenConnect()

    monkeypatch.setattr("dejaship.main.engine", BrokenEngine())
    monkeypatch.setattr("dejaship.main.get_model", lambda: (_ for _ in ()).throw(RuntimeError("missing")))

    resp = await client.get("/ready")
    assert resp.status_code == 503
    assert resp.json() == {
        "status": "error",
        "checks": {"database": "error", "embeddings": "error"},
    }


def test_get_client_ip_ignores_untrusted_proxy_headers(monkeypatch):
    """Proxy headers are ignored unless the peer is trusted."""
    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", False)

    request = Request({
        "type": "http",
        "headers": [
            (b"cf-connecting-ip", b"203.0.113.10"),
            (b"x-forwarded-for", b"198.51.100.1"),
        ],
        "client": ("127.0.0.1", 12345),
        "method": "GET",
        "path": "/v1/check",
    })

    assert get_client_ip(request) == "127.0.0.1"


def test_get_client_ip_uses_trusted_proxy_headers(monkeypatch):
    """Trusted proxies can supply the real client IP."""
    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(settings, "TRUSTED_PROXY_CIDRS", "127.0.0.0/8")

    request = Request({
        "type": "http",
        "headers": [(b"x-forwarded-for", b"198.51.100.1, 127.0.0.1")],
        "client": ("127.0.0.1", 12345),
        "method": "GET",
        "path": "/v1/check",
    })

    assert get_client_ip(request) == "198.51.100.1"


# --- Stats Endpoint ---


@pytest.mark.anyio
async def test_stats_empty_db(client: AsyncClient):
    resp = await client.get("/v1/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_claims"] == 0
    assert data["active"] == 0
    assert data["shipped"] == 0
    assert data["abandoned"] == 0


@pytest.mark.anyio
async def test_stats_counts_claims(client: AsyncClient):
    keywords = ["saas", "billing", "invoicing", "payments", "recurring"]
    r1 = await client.post("/v1/claim", json={"core_mechanic": "Invoice tracking", "keywords": keywords})
    r2 = await client.post("/v1/claim", json={"core_mechanic": "Payment processing", "keywords": keywords})
    assert r1.status_code == 200
    assert r2.status_code == 200

    claim = r1.json()
    await client.post("/v1/update", json={
        "claim_id": claim["claim_id"],
        "edit_token": claim["edit_token"],
        "status": "shipped",
    })

    resp = await client.get("/v1/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_claims"] == 2
    assert data["active"] == 1
    assert data["shipped"] == 1
    assert data["abandoned"] == 0
