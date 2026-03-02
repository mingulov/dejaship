from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dejaship.db import get_session
from dejaship.models import AgentIntent, IntentStatus
from dejaship.schemas import StatsResponse

router = APIRouter()


@router.get("/stats", response_model=StatsResponse)
async def stats(session: AsyncSession = Depends(get_session)):
    """Public statistics: total claims and counts by status."""
    query = select(AgentIntent.status, func.count().label("cnt")).group_by(AgentIntent.status)
    result = await session.execute(query)
    counts = {row.status: row.cnt for row in result}
    return StatsResponse(
        total_claims=sum(counts.values()),
        active=counts.get(IntentStatus.IN_PROGRESS, 0),
        shipped=counts.get(IntentStatus.SHIPPED, 0),
        abandoned=counts.get(IntentStatus.ABANDONED, 0),
    )
