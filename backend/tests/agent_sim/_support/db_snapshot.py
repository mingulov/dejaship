from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from dejaship.models import AgentIntent
from tests.agent_sim._support.types import PersistedIntentRow, SimulationDatabaseSnapshot


async def fetch_simulation_db_snapshot(engine: AsyncEngine) -> SimulationDatabaseSnapshot:
    async with engine.connect() as conn:
        result = await conn.execute(
            select(
                AgentIntent.core_mechanic,
                AgentIntent.status,
                AgentIntent.resolution_url,
                AgentIntent.keywords,
            )
        )
        persisted_rows = [
            PersistedIntentRow(
                core_mechanic=row.core_mechanic,
                status=row.status.value if hasattr(row.status, "value") else str(row.status),
                resolution_url=row.resolution_url,
                keywords=row.keywords,
            )
            for row in result
        ]

    status_counts = Counter(row.status for row in persisted_rows)
    return SimulationDatabaseSnapshot(
        total_rows=len(persisted_rows),
        status_counts=dict(status_counts),
        shipped_with_resolution_url=sum(
            1
            for row in persisted_rows
            if row.status == "shipped" and row.resolution_url is not None
        ),
        abandoned_with_resolution_url=sum(
            1
            for row in persisted_rows
            if row.status == "abandoned" and row.resolution_url is not None
        ),
        in_progress_with_resolution_url=sum(
            1
            for row in persisted_rows
            if row.status == "in_progress" and row.resolution_url is not None
        ),
        rows=persisted_rows,
    )
