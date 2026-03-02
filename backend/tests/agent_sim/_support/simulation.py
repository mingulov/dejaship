from __future__ import annotations

import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from math import floor

import anyio
import httpx
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine

from dejaship.config import settings
from dejaship.models import AgentIntent, IntentStatus
from tests.agent_sim._support.catalog import resolve_model_set
from tests.agent_sim._support.agents import execute_agent_run
from tests.agent_sim._support.fixture_store import FixtureIndex
from tests.agent_sim._support.mcp_client import connect_mcp_client
from tests.agent_sim._support.reporting import build_simulation_report
from tests.agent_sim._support.types import (
    AppCatalog,
    AgentRunSummary,
    ModelMatrix,
    SimulationEvent,
    ScenarioDefinition,
    SimulationAgentAssignment,
    SimulationPlan,
    SimulationReport,
)


OVERLAP_FOCUSED_STRATEGIES = {"overlap-focused", "overlap-heavy", "mixed-with-overlap", "weighted-mixed"}


def _group_briefs_by_overlap(catalog: AppCatalog) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for brief in catalog.briefs:
        groups[brief.expected_overlap_group].append(brief.id)
    return groups


def _select_brief_pool(catalog: AppCatalog, strategy: str) -> list[str]:
    overlap_groups = _group_briefs_by_overlap(catalog)
    multi_brief_groups = [brief_ids for brief_ids in overlap_groups.values() if len(brief_ids) >= 2]

    if strategy == "balanced":
        return [brief.id for brief in catalog.briefs]

    if strategy in OVERLAP_FOCUSED_STRATEGIES:
        overlap_pool = [brief_id for group in multi_brief_groups for brief_id in group]
        if strategy == "overlap-focused":
            return overlap_pool
        ambiguous_pool = [brief.id for brief in catalog.briefs if brief.adjacent_overlap_groups]
        remaining_pool = [brief.id for brief in catalog.briefs if brief.id not in overlap_pool and brief.id not in ambiguous_pool]
        return overlap_pool + ambiguous_pool + remaining_pool

    return [brief.id for brief in catalog.briefs]


def build_simulation_plan(
    *,
    scenario_name: str,
    scenario: ScenarioDefinition,
    model_matrix: ModelMatrix,
    catalog: AppCatalog,
    seed: int = 1,
) -> SimulationPlan:
    rng = random.Random(seed)
    if scenario.keyword_drop_max < scenario.keyword_drop_min:
        raise ValueError("keyword_drop_max must be >= keyword_drop_min")
    models = resolve_model_set(model_matrix, scenario.model_set)
    model_aliases = [alias for alias, _ in models]
    model_weights = [entry.weight for _, entry in models]
    brief_pool = _select_brief_pool(catalog, scenario.brief_selection_strategy)
    persona_sequence = [
        persona
        for persona, count in scenario.persona_mix.items()
        for _ in range(count)
    ]

    assignments: list[SimulationAgentAssignment] = []
    for agent_index in range(scenario.agent_count):
        persona = persona_sequence[agent_index % len(persona_sequence)]
        model_alias = rng.choices(model_aliases, weights=model_weights, k=1)[0]
        model_name = model_matrix.models[model_alias].model
        primary_brief = brief_pool[agent_index % len(brief_pool)]
        secondary_brief = brief_pool[(agent_index + rng.randint(1, len(brief_pool) - 1)) % len(brief_pool)]
        brief_ids = [primary_brief] if primary_brief == secondary_brief else [primary_brief, secondary_brief]

        assignments.append(
            SimulationAgentAssignment(
                agent_id=f"agent-{agent_index + 1:02d}",
                persona=persona,
                model_alias=model_alias,
                model_name=model_name,
                brief_ids=brief_ids,
                seed=seed * 1000 + agent_index,
                keyword_drop_count=(
                    rng.randint(scenario.keyword_drop_min, scenario.keyword_drop_max)
                    if scenario.keyword_drop_max > 0
                    else 0
                ),
            )
        )

    return SimulationPlan(
        scenario_name=scenario_name,
        agent_count=scenario.agent_count,
        total_calls_target=scenario.total_calls_target,
        model_set=scenario.model_set,
        require_stored_fixtures=scenario.require_stored_fixtures,
        run_stale_cleanup=scenario.run_stale_cleanup,
        keyword_drop_min=scenario.keyword_drop_min,
        keyword_drop_max=scenario.keyword_drop_max,
        assignments=assignments,
    )


def calculate_call_budgets(plan: SimulationPlan) -> dict[str, int]:
    base_budget = max(4, floor(plan.total_calls_target / plan.agent_count))
    remainder = max(0, plan.total_calls_target - (base_budget * plan.agent_count))
    budgets: dict[str, int] = {}
    for index, assignment in enumerate(plan.assignments):
        budgets[assignment.agent_id] = base_budget + (1 if index < remainder else 0)
    return budgets


async def run_simulation(
    *,
    plan: SimulationPlan,
    catalog: AppCatalog,
    fixture_index: FixtureIndex,
    http_client: httpx.AsyncClient,
    base_url: str = "http://localhost/mcp/",
    engine: AsyncEngine | None = None,
) -> SimulationReport:
    brief_map = {brief.id: brief for brief in catalog.briefs}
    budgets = calculate_call_budgets(plan)
    summaries: list[AgentRunSummary] = []
    summary_lock = anyio.Lock()

    async def run_assignment(assignment: SimulationAgentAssignment) -> None:
        intents = [
            fixture_index.resolve_or_synthesize(
                brief=brief_map[brief_id],
                model_alias=assignment.model_alias,
                model_name=assignment.model_name,
            )
            for brief_id in assignment.brief_ids
        ]
        if plan.require_stored_fixtures:
            synthetic_briefs = [intent.brief_id for intent in intents if intent.source != "stored"]
            if synthetic_briefs:
                raise ValueError(
                    f"scenario '{plan.scenario_name}' requires stored fixtures, missing: {synthetic_briefs}"
                )
        async with connect_mcp_client(base_url=base_url, http_client=http_client) as client:
            summary = await execute_agent_run(
                client=client,
                assignment=assignment,
                intents=intents,
                call_budget=budgets[assignment.agent_id],
            )
        async with summary_lock:
            summaries.append(summary)

    async with anyio.create_task_group() as tg:
        for assignment in plan.assignments:
            tg.start_soon(run_assignment, assignment)

    if plan.run_stale_cleanup:
        if engine is None:
            raise ValueError("engine is required when run_stale_cleanup is enabled")

        unresolved = {
            claim_id: summary
            for summary in summaries
            for claim_id in summary.unresolved_claim_ids
        }
        if unresolved:
            stale_cutoff = datetime.now(timezone.utc) - timedelta(days=settings.ABANDONMENT_DAYS + 1)
            async with engine.begin() as conn:
                await conn.execute(
                    update(AgentIntent)
                    .where(AgentIntent.id.in_(list(unresolved)))
                    .values(updated_at=stale_cutoff)
                )
                result = await conn.execute(
                    update(AgentIntent)
                    .where(AgentIntent.status == IntentStatus.IN_PROGRESS)
                    .where(AgentIntent.updated_at < datetime.now(timezone.utc) - timedelta(days=settings.ABANDONMENT_DAYS))
                    .values(
                        status=IntentStatus.ABANDONED,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
            if result.rowcount:
                for claim_id, summary in unresolved.items():
                    summary.stale_cleanup_actions += 1
                    summary.stale_abandoned_claim_ids.append(claim_id)
                    if claim_id in summary.unresolved_claim_ids:
                        summary.unresolved_claim_ids.remove(claim_id)
                    summary.completed_statuses.append("abandoned")
                    summary.events.append(
                        SimulationEvent(
                            event_index=len(summary.events),
                            event_type="cleanup",
                            agent_id=summary.agent_id,
                            persona=summary.persona,
                            model_alias=summary.model_alias,
                            claim_id=claim_id,
                            status="abandoned",
                            message="stale cleanup marked unresolved claim as abandoned",
                        )
                    )

    return build_simulation_report(
        scenario_name=plan.scenario_name,
        summaries=sorted(summaries, key=lambda summary: summary.agent_id),
        catalog=catalog,
    )
