from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from dejaship.db import get_session
from dejaship.schemas import UpdateInput, UpdateResponse
from dejaship.services import update_claim

router = APIRouter()


@router.post("/update", response_model=UpdateResponse)
async def update(input: UpdateInput, session: AsyncSession = Depends(get_session)):
    try:
        return await update_claim(input, session)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
