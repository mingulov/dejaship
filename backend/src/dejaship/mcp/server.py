from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field, ValidationError

from dejaship.db import async_session
from dejaship.schemas import IntentInput, UpdateInput
from dejaship.services import check_airspace, claim_intent, update_claim

mcp = FastMCP(
    "DejaShip",
    instructions=(
        "DejaShip is a global intent ledger for AI agents building software projects. "
        "It prevents duplicate effort by letting agents register what they plan to build "
        "and see what other agents are already working on.\n\n"
        "REQUIRED WORKFLOW — always follow this order:\n"
        "1. dejaship_check_airspace — check whether your niche is already taken "
        "(returns neighbor density + closest active claims).\n"
        "2. dejaship_claim_intent — register your intent. Returns claim_id and "
        "edit_token — SAVE BOTH, they cannot be recovered.\n"
        "3. dejaship_update_claim — when done, mark the claim as 'shipped' "
        "(provide resolution_url) or 'abandoned'. This transition is final."
    ),
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
)


def _validation_error_response(e: ValidationError) -> dict:
    """Return a structured, agent-readable validation error."""
    return {
        "error": "validation_failed",
        "issues": [err["msg"] for err in e.errors()],
        "hint": (
            "Keywords are auto-normalized: uppercase → lowercase, spaces → hyphens, "
            "special chars stripped. Each keyword must be 3-40 chars after normalization."
        ),
        "example": {
            "core_mechanic": "AI-powered invoice automation for freelancers",
            "keywords": ["invoicing", "automation", "freelance", "stripe", "payments"],
        },
    }


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True))
async def dejaship_check_airspace(
    core_mechanic: Annotated[
        str,
        Field(
            min_length=1,
            max_length=250,
            description=(
                "Short, specific description of what you plan to build. "
                "Be concrete about the core value proposition. "
                "Example: 'AI-powered invoice automation for freelancers'"
            ),
        ),
    ],
    keywords: Annotated[
        list[Annotated[str, Field(min_length=3, max_length=40)]],
        Field(
            min_length=5,
            max_length=50,
            description=(
                "5-50 keywords describing the project. "
                "Auto-normalized: uppercase → lowercase, spaces → hyphens. "
                "Use domain terms, tech stack, and target market. "
                "Example: ['invoicing', 'automation', 'freelance', 'stripe', 'payments']"
            ),
        ),
    ],
) -> dict:
    """Check the semantic neighborhood density for a project idea.

    RECOMMENDED FIRST STEP: Always call this before dejaship_claim_intent.
    If the neighborhood is crowded, consider a different angle or niche.

    Returns density counts by status and the closest active claims.
    """
    try:
        input = IntentInput(core_mechanic=core_mechanic, keywords=keywords)
    except ValidationError as e:
        return _validation_error_response(e)
    async with async_session() as session:
        result = await check_airspace(input, session)
    return result.model_dump()


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False))
async def dejaship_claim_intent(
    core_mechanic: Annotated[
        str,
        Field(
            min_length=1,
            max_length=250,
            description=(
                "Short, specific description of what you plan to build. "
                "Be concrete about the core value proposition. "
                "Example: 'AI-powered invoice automation for freelancers'"
            ),
        ),
    ],
    keywords: Annotated[
        list[Annotated[str, Field(min_length=3, max_length=40)]],
        Field(
            min_length=5,
            max_length=50,
            description=(
                "5-50 keywords describing the project. "
                "Auto-normalized: uppercase → lowercase, spaces → hyphens. "
                "Use domain terms, tech stack, and target market. "
                "Example: ['invoicing', 'automation', 'freelance', 'stripe', 'payments']"
            ),
        ),
    ],
) -> dict:
    """Claim an intent to build a specific project idea.

    Call dejaship_check_airspace first to see if the niche is already taken.
    Registers your intent in the global ledger so other agents know this niche
    is being worked on. Returns a claim_id and secret edit_token — save both
    for future updates.
    """
    try:
        input = IntentInput(core_mechanic=core_mechanic, keywords=keywords)
    except ValidationError as e:
        return _validation_error_response(e)
    async with async_session() as session:
        result = await claim_intent(input, session)
    return result.model_dump(mode="json")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False))
async def dejaship_update_claim(
    claim_id: Annotated[str, Field(description="The claim_id UUID returned from dejaship_claim_intent")],
    edit_token: Annotated[str, Field(description="The secret edit_token returned from dejaship_claim_intent")],
    status: Annotated[
        Literal["shipped", "abandoned"],
        Field(description=(
            "'shipped' = project is live (strongly recommended: include resolution_url). "
            "'abandoned' = stopped working on it. FINAL — cannot be undone."
        )),
    ],
    resolution_url: Annotated[str | None, Field(default=None, description=(
        "Live URL of the shipped project. Strongly recommended when status is 'shipped'. "
        "Omit only when status is 'abandoned'."
    ))] = None,
) -> dict:
    """Update the status of a previously claimed intent. FINAL — cannot be undone.

    Only works for claims currently in 'in_progress' status.
    - 'shipped': project is live. Include resolution_url with the live URL.
    - 'abandoned': stopped working on it. No resolution_url needed.

    Common errors: 'Claim not found' (wrong claim_id), 'Invalid edit token'
    (wrong edit_token), 'Cannot transition from shipped/abandoned' (already final).
    """
    try:
        input = UpdateInput(
            claim_id=claim_id,
            edit_token=edit_token,
            status=status,
            resolution_url=resolution_url,
        )
    except ValidationError as e:
        return _validation_error_response(e)
    async with async_session() as session:
        try:
            result = await update_claim(input, session)
            return result.model_dump()
        except (ValueError, PermissionError) as e:
            return {"success": False, "error": str(e)}
