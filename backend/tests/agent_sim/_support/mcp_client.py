from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any

import httpx
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from dejaship.schemas import CheckResponse, ClaimResponse, IntentInput, UpdateInput
from tests.agent_sim._support.types import MCPUpdateResult


class MCPToolError(RuntimeError):
    pass


def _decode_tool_result(result) -> dict[str, Any]:
    if result.structuredContent is not None:
        if isinstance(result.structuredContent, dict):
            return result.structuredContent
        raise MCPToolError("unexpected structuredContent type from MCP tool")

    for item in result.content:
        text = getattr(item, "text", None)
        if isinstance(text, str):
            try:
                return json.loads(text)
            except json.JSONDecodeError as exc:
                raise MCPToolError("tool returned non-JSON text content") from exc

    raise MCPToolError("tool result did not contain structured JSON content")


class DejaShipMCPClient:
    def __init__(self, session: ClientSession):
        self._session = session

    async def list_tool_names(self) -> list[str]:
        result = await self._session.list_tools()
        return [tool.name for tool in result.tools]

    async def check_airspace(self, intent: IntentInput) -> CheckResponse:
        result = await self._session.call_tool(
            "dejaship_check_airspace",
            {
                "core_mechanic": intent.core_mechanic,
                "keywords": intent.keywords,
            },
        )
        payload = _decode_tool_result(result)
        if "error" in payload:
            raise MCPToolError(payload["error"])
        return CheckResponse.model_validate(payload)

    async def claim_intent(self, intent: IntentInput) -> ClaimResponse:
        result = await self._session.call_tool(
            "dejaship_claim_intent",
            {
                "core_mechanic": intent.core_mechanic,
                "keywords": intent.keywords,
            },
        )
        payload = _decode_tool_result(result)
        if "error" in payload:
            raise MCPToolError(payload["error"])
        return ClaimResponse.model_validate(payload)

    async def update_claim(self, update: UpdateInput) -> MCPUpdateResult:
        result = await self._session.call_tool(
            "dejaship_update_claim",
            {
                "claim_id": str(update.claim_id),
                "edit_token": update.edit_token,
                "status": update.status,
                "resolution_url": update.resolution_url,
            },
        )
        payload = _decode_tool_result(result)
        return MCPUpdateResult.model_validate(payload)


@asynccontextmanager
async def connect_mcp_client(
    *,
    base_url: str,
    http_client: httpx.AsyncClient,
) -> DejaShipMCPClient:
    async with streamable_http_client(
        base_url,
        http_client=http_client,
        terminate_on_close=False,
    ) as streams:
        async with ClientSession(*streams[:2]) as session:
            await session.initialize()
            yield DejaShipMCPClient(session)
