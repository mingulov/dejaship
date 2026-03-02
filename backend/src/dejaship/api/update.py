from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from dejaship.config import settings
from dejaship.db import get_session
from dejaship.limiter import limiter
from dejaship.schemas import UpdateInput, UpdateResponse
from dejaship.services import update_claim

router = APIRouter()


@router.post("/update", response_model=UpdateResponse)
@limiter.limit(settings.RATE_LIMIT_UPDATE)
async def update(request: Request, input: UpdateInput, session: AsyncSession = Depends(get_session)):
    """Update the status of a previously claimed intent.

    Transition from in_progress to either 'shipped' or 'abandoned'.
    Requires the edit_token from the original claim.
    """
    try:
        return await update_claim(input, session)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
