"""Cron job: mark stale in_progress claims as abandoned.

Usage: uv run python scripts/abandon_stale.py
"""

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import update

from dejaship.config import settings
from dejaship.db import engine
from dejaship.models import AgentIntent, IntentStatus


async def abandon_stale():
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.ABANDONMENT_DAYS)
    async with engine.begin() as conn:
        result = await conn.execute(
            update(AgentIntent)
            .where(AgentIntent.status == IntentStatus.IN_PROGRESS)
            .where(AgentIntent.updated_at < cutoff)
            .values(status=IntentStatus.ABANDONED, updated_at=datetime.now(timezone.utc))
        )
        print(f"Abandoned {result.rowcount} stale claims")


if __name__ == "__main__":
    asyncio.run(abandon_stale())
