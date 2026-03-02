from __future__ import annotations

import random
from collections import defaultdict
from math import floor

import anyio
import httpx

from tests.agent_sim._support.catalog import resolve_model_set
from tests.agent_sim._support.agents import execute_agent_run
from tests.agent_sim._support.fixture_store import FixtureIndex
from tests.agent_sim._support.mcp_client import connect_mcp_client
from tests.agent_sim._support.reporting import build_simulation_report
from tests.agent_sim._support.types import (
    AppCatalog,
    AgentRunSummary,
    ModelMatrix,
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
            )
        )

    return SimulationPlan(
        scenario_name=scenario_name,
        agent_count=scenario.agent_count,
        total_calls_target=scenario.total_calls_target,
        model_set=scenario.model_set,
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

    return build_simulation_report(
        scenario_name=plan.scenario_name,
        summaries=sorted(summaries, key=lambda summary: summary.agent_id),
    )
