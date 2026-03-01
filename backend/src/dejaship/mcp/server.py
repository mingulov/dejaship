from mcp.server.fastmcp import FastMCP
from pydantic import ValidationError

from dejaship.db import async_session
from dejaship.schemas import IntentInput, UpdateInput
from dejaship.services import check_airspace, claim_intent, update_claim

mcp = FastMCP(
    "DejaShip",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
)


@mcp.tool()
async def dejaship_check_airspace(
    core_mechanic: str,
    keywords: list[str],
) -> dict:
    """Check the semantic neighborhood density for a project idea.

    Before building something, check how many other agents are already building
    similar projects. Returns density counts by status and the closest active claims.

    Args:
        core_mechanic: A short description of what you plan to build (max 250 chars).
        keywords: 5-50 lowercase keywords describing the project (each 3-40 chars, alphanumeric + hyphens).
    """
    try:
        input = IntentInput(core_mechanic=core_mechanic, keywords=keywords)
    except ValidationError as e:
        return {"error": str(e)}
    async with async_session() as session:
        result = await check_airspace(input, session)
    return result.model_dump()


@mcp.tool()
async def dejaship_claim_intent(
    core_mechanic: str,
    keywords: list[str],
) -> dict:
    """Claim an intent to build a specific project idea.

    Registers your intent in the global ledger so other agents know this niche
    is being worked on. Returns a claim_id and secret edit_token for future updates.

    Args:
        core_mechanic: A short description of what you plan to build (max 250 chars).
        keywords: 5-50 lowercase keywords describing the project (each 3-40 chars, alphanumeric + hyphens).
    """
    try:
        input = IntentInput(core_mechanic=core_mechanic, keywords=keywords)
    except ValidationError as e:
        return {"error": str(e)}
    async with async_session() as session:
        result = await claim_intent(input, session)
    return result.model_dump(mode="json")


@mcp.tool()
async def dejaship_update_claim(
    claim_id: str,
    edit_token: str,
    status: str,
    resolution_url: str | None = None,
) -> dict:
    """Update the status of a previously claimed intent.

    Call this when you've either shipped the project or decided to abandon it.

    Args:
        claim_id: The UUID returned from dejaship_claim_intent.
        edit_token: The secret token returned from dejaship_claim_intent.
        status: Either "shipped" or "abandoned".
        resolution_url: The live URL if status is "shipped" (optional).
    """
    try:
        input = UpdateInput(
            claim_id=claim_id,
            edit_token=edit_token,
            status=status,
            resolution_url=resolution_url,
        )
    except ValidationError as e:
        return {"error": str(e)}
    async with async_session() as session:
        try:
            result = await update_claim(input, session)
            return result.model_dump()
        except (ValueError, PermissionError) as e:
            return {"success": False, "error": str(e)}
