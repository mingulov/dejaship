from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from dejaship.config import settings
from dejaship.db import get_session
from dejaship.limiter import limiter
from dejaship.schemas import CheckResponse, IntentInput
from dejaship.services import check_airspace

router = APIRouter()


@router.post("/check", response_model=CheckResponse)
@limiter.limit(settings.RATE_LIMIT_CHECK)
async def check(request: Request, input: IntentInput, session: AsyncSession = Depends(get_session)):
    return await check_airspace(input, session)
