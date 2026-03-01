from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dejaship.db import get_session
from dejaship.schemas import ClaimResponse, IntentInput
from dejaship.services import claim_intent

router = APIRouter()


@router.post("/claim", response_model=ClaimResponse)
async def claim(input: IntentInput, session: AsyncSession = Depends(get_session)):
    return await claim_intent(input, session)
