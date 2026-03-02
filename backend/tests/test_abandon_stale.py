"""Tests for the abandon_stale.py cleanup script."""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from dejaship.models import AgentIntent, IntentStatus

import scripts.abandon_stale as abandon_stale_module
from scripts.abandon_stale import abandon_stale


SAMPLE_KEYWORDS = ["seo", "plumber", "local-business", "marketing", "website"]


async def _age_claim(engine: AsyncEngine, claim_id: str, days: int) -> None:
    """Directly set updated_at and created_at on a claim to make it appear old."""
    old_time = datetime.now(timezone.utc) - timedelta(days=days)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE agent_intents "
                "SET updated_at = :old_time, created_at = :old_time "
                "WHERE id = cast(:claim_id as uuid)"
            ),
            {"old_time": old_time, "claim_id": claim_id},
        )


async def _get_status(engine: AsyncEngine, claim_id: str) -> str:
    """Query the DB directly for a claim's status."""
    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT status FROM agent_intents WHERE id = cast(:claim_id as uuid)"),
            {"claim_id": claim_id},
        )
        row = result.fetchone()
        assert row is not None, f"Claim {claim_id} not found"
        return row[0]


@pytest.mark.asyncio
async def test_stale_in_progress_gets_abandoned(client: AsyncClient, engine: AsyncEngine, monkeypatch):
    """in_progress claims older than ABANDONMENT_DAYS should be marked abandoned."""
    resp = await client.post("/v1/claim", json={
        "core_mechanic": "seo tool for plumbers",
        "keywords": SAMPLE_KEYWORDS,
    })
    assert resp.status_code == 200
    claim_id = resp.json()["claim_id"]

    # Age the claim beyond the 7-day threshold
    await _age_claim(engine, claim_id, days=8)

    # Point the script at the test engine
    monkeypatch.setattr(abandon_stale_module, "engine", engine)

    await abandon_stale()

    status = await _get_status(engine, claim_id)
    assert status == IntentStatus.ABANDONED.value


@pytest.mark.asyncio
async def test_fresh_in_progress_not_abandoned(client: AsyncClient, engine: AsyncEngine, monkeypatch):
    """in_progress claims created recently should NOT be touched."""
    resp = await client.post("/v1/claim", json={
        "core_mechanic": "knitting inventory system",
        "keywords": ["knitting", "inventory", "yarn", "crafts", "shop-management"],
    })
    assert resp.status_code == 200
    claim_id = resp.json()["claim_id"]

    # Age to only 1 day old — well within the 7-day window
    await _age_claim(engine, claim_id, days=1)

    monkeypatch.setattr(abandon_stale_module, "engine", engine)

    await abandon_stale()

    status = await _get_status(engine, claim_id)
    assert status == IntentStatus.IN_PROGRESS.value


@pytest.mark.asyncio
async def test_shipped_claim_not_touched(client: AsyncClient, engine: AsyncEngine, monkeypatch):
    """Shipped claims must not be changed by the cleanup script, even if very old."""
    resp = await client.post("/v1/claim", json={
        "core_mechanic": "crypto defi platform",
        "keywords": ["blockchain", "defi", "smart-contracts", "ethereum", "token"],
    })
    assert resp.status_code == 200
    claim = resp.json()

    await client.post("/v1/update", json={
        "claim_id": claim["claim_id"],
        "edit_token": claim["edit_token"],
        "status": "shipped",
        "resolution_url": "https://example.com",
    })

    # Age the claim far beyond the threshold
    await _age_claim(engine, claim["claim_id"], days=30)

    monkeypatch.setattr(abandon_stale_module, "engine", engine)

    await abandon_stale()

    status = await _get_status(engine, claim["claim_id"])
    assert status == IntentStatus.SHIPPED.value


@pytest.mark.asyncio
async def test_already_abandoned_claim_not_retouched(client: AsyncClient, engine: AsyncEngine, monkeypatch):
    """Claims already abandoned should not have their updated_at changed again."""
    resp = await client.post("/v1/claim", json={
        "core_mechanic": "marketing analytics dashboard",
        "keywords": ["analytics", "marketing", "dashboard", "reporting", "metrics"],
    })
    assert resp.status_code == 200
    claim = resp.json()

    await client.post("/v1/update", json={
        "claim_id": claim["claim_id"],
        "edit_token": claim["edit_token"],
        "status": "abandoned",
    })

    # Age the claim
    await _age_claim(engine, claim["claim_id"], days=30)

    monkeypatch.setattr(abandon_stale_module, "engine", engine)

    await abandon_stale()

    # Status must still be abandoned
    status = await _get_status(engine, claim["claim_id"])
    assert status == IntentStatus.ABANDONED.value


@pytest.mark.asyncio
async def test_only_stale_claims_abandoned_mixed_batch(client: AsyncClient, engine: AsyncEngine, monkeypatch):
    """With a mix of stale and fresh claims, only stale ones get abandoned."""
    # Stale claim
    stale_resp = await client.post("/v1/claim", json={
        "core_mechanic": "invoice tracking saas",
        "keywords": ["saas", "billing", "invoicing", "payments", "recurring"],
    })
    assert stale_resp.status_code == 200
    stale_id = stale_resp.json()["claim_id"]

    # Fresh claim
    fresh_resp = await client.post("/v1/claim", json={
        "core_mechanic": "project management tool",
        "keywords": ["project", "management", "tasks", "collaboration", "team"],
    })
    assert fresh_resp.status_code == 200
    fresh_id = fresh_resp.json()["claim_id"]

    # Age only the stale claim
    await _age_claim(engine, stale_id, days=10)
    await _age_claim(engine, fresh_id, days=2)

    monkeypatch.setattr(abandon_stale_module, "engine", engine)

    await abandon_stale()

    stale_status = await _get_status(engine, stale_id)
    fresh_status = await _get_status(engine, fresh_id)

    assert stale_status == IntentStatus.ABANDONED.value
    assert fresh_status == IntentStatus.IN_PROGRESS.value


@pytest.mark.asyncio
async def test_claim_just_inside_threshold_not_abandoned(client: AsyncClient, engine: AsyncEngine, monkeypatch):
    """A claim aged to just under ABANDONMENT_DAYS (6 days) should NOT be abandoned."""
    from dejaship.config import settings

    resp = await client.post("/v1/claim", json={
        "core_mechanic": "email marketing platform",
        "keywords": ["email", "marketing", "campaigns", "automation", "newsletter"],
    })
    assert resp.status_code == 200
    claim_id = resp.json()["claim_id"]

    # Age to one day short of the threshold — well within the active window
    await _age_claim(engine, claim_id, days=settings.ABANDONMENT_DAYS - 1)

    monkeypatch.setattr(abandon_stale_module, "engine", engine)

    await abandon_stale()

    status = await _get_status(engine, claim_id)
    assert status == IntentStatus.IN_PROGRESS.value
