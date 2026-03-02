import pytest

from dejaship.schemas import IntentInput, UpdateInput
from tests.agent_sim._support.mcp_client import connect_mcp_client


pytestmark = pytest.mark.agent_sim


@pytest.mark.asyncio
async def test_mcp_client_lists_tools(mcp_base_url, mcp_http_client_factory):
    async with mcp_http_client_factory() as mcp_http_client:
        async with connect_mcp_client(base_url=mcp_base_url, http_client=mcp_http_client) as mcp_session:
            tool_names = await mcp_session.list_tool_names()

    assert set(tool_names) == {
        "dejaship_check_airspace",
        "dejaship_claim_intent",
        "dejaship_update_claim",
    }


@pytest.mark.asyncio
async def test_mcp_client_round_trip_claim_and_update(mcp_base_url, mcp_http_client_factory):
    intent = IntentInput(
        core_mechanic="seo tool for plumbers",
        keywords=["seo", "plumber", "local-business", "marketing", "website"],
    )

    async with mcp_http_client_factory() as mcp_http_client:
        async with connect_mcp_client(base_url=mcp_base_url, http_client=mcp_http_client) as mcp_session:
            check = await mcp_session.check_airspace(intent)
            claim = await mcp_session.claim_intent(intent)
            update = await mcp_session.update_claim(
                UpdateInput(
                    claim_id=claim.claim_id,
                    edit_token=claim.edit_token,
                    status="shipped",
                    resolution_url="https://example.com",
                )
            )

    assert check.neighborhood_density.in_progress == 0
    assert claim.status == "in_progress"
    assert update.success is True


@pytest.mark.asyncio
async def test_mcp_client_reports_update_failures(mcp_base_url, mcp_http_client_factory):
    intent = IntentInput(
        core_mechanic="seo tool for plumbers",
        keywords=["seo", "plumber", "local-business", "marketing", "website"],
    )

    async with mcp_http_client_factory() as mcp_http_client:
        async with connect_mcp_client(base_url=mcp_base_url, http_client=mcp_http_client) as mcp_session:
            claim = await mcp_session.claim_intent(intent)
            result = await mcp_session.update_claim(
                UpdateInput(
                    claim_id=claim.claim_id,
                    edit_token="wrong-token",
                    status="shipped",
                )
            )

    assert result.success is False
    assert result.error is not None
