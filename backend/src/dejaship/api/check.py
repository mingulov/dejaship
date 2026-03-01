from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dejaship.db import get_session
from dejaship.schemas import CheckResponse, IntentInput
from dejaship.services import check_airspace

router = APIRouter()


@router.post("/check", response_model=CheckResponse)
async def check(input: IntentInput, session: AsyncSession = Depends(get_session)):
    return await check_airspace(input, session)
