from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from dejaship.config import settings
from dejaship.db import get_session
from dejaship.limiter import limiter
from dejaship.schemas import ClaimResponse, IntentInput
from dejaship.services import claim_intent

router = APIRouter()


@router.post("/claim", response_model=ClaimResponse)
@limiter.limit(settings.RATE_LIMIT_CLAIM)
async def claim(request: Request, input: IntentInput, session: AsyncSession = Depends(get_session)):
    """Claim an intent to build a specific project.

    Registers your project in the global ledger. Returns a claim_id and a
    secret edit_token — store the token safely, it cannot be recovered.
    """
    return await claim_intent(input, session)
