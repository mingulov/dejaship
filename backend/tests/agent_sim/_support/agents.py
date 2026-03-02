from __future__ import annotations

from dataclasses import dataclass

from dejaship.schemas import CheckResponse, IntentInput, UpdateInput
from tests.agent_sim._support.mcp_client import DejaShipMCPClient
from tests.agent_sim._support.types import AgentRunSummary, ResolvedSimulationIntent, SimulationAgentAssignment


OVERLAP_AVERSE_PERSONAS = {"cautious", "overlap-averse", "reviser"}
EXTRA_MONITORING_PERSONAS = {"cautious", "monitor-first", "overlap-tolerant", "duplicate-prone"}
ABANDONING_PERSONAS = {"abandoner"}


@dataclass(slots=True)
class AgentExecutionState:
    summary: AgentRunSummary
    calls_used: int = 0


def _crowding_score(check: CheckResponse) -> tuple[int, int, int]:
    density = check.neighborhood_density
    return (density.in_progress, density.shipped, density.abandoned)


def _is_crowded(check: CheckResponse) -> bool:
    density = check.neighborhood_density
    return density.in_progress > 0 or density.shipped > 0


def _resolution_status(persona: str, preferred: str) -> str | None:
    if persona in ABANDONING_PERSONAS:
        return "abandoned"
    if preferred in {"ship", "shipped"}:
        return "shipped"
    if preferred == "abandon":
        return "abandoned"
    return "shipped"


async def _list_tools(
    client: DejaShipMCPClient,
    state: AgentExecutionState,
    budget: int,
) -> None:
    if state.calls_used >= budget:
        return
    await client.list_tool_names()
    state.summary.tool_lists += 1
    state.calls_used += 1


async def _check_intent(
    client: DejaShipMCPClient,
    state: AgentExecutionState,
    budget: int,
    intent: IntentInput,
) -> CheckResponse | None:
    if state.calls_used >= budget:
        return None
    result = await client.check_airspace(intent)
    state.summary.checks += 1
    state.calls_used += 1
    return result


async def _claim_intent(
    client: DejaShipMCPClient,
    state: AgentExecutionState,
    budget: int,
    resolved: ResolvedSimulationIntent,
) -> object | None:
    if state.calls_used >= budget:
        return None
    result = await client.claim_intent(resolved.fixture.final_intent_input)
    state.summary.claims += 1
    state.summary.claimed_brief_ids.append(resolved.brief_id)
    if resolved.source not in state.summary.fixture_sources:
        state.summary.fixture_sources.append(resolved.source)
    state.calls_used += 1
    return result


async def _update_claim(
    client: DejaShipMCPClient,
    state: AgentExecutionState,
    budget: int,
    *,
    claim_id,
    edit_token: str,
    brief_id: str,
    status: str,
    agent_id: str,
) -> None:
    if state.calls_used >= budget:
        return
    result = await client.update_claim(
        UpdateInput(
            claim_id=claim_id,
            edit_token=edit_token,
            status=status,
            resolution_url=f"https://agent-sim.local/{brief_id}/{agent_id}" if status == "shipped" else None,
        )
    )
    state.summary.updates += 1
    state.calls_used += 1
    if result.success:
        state.summary.completed_statuses.append(status)
        return
    state.summary.errors += 1


def _select_primary_intent(
    assignment: SimulationAgentAssignment,
    checks_by_brief: dict[str, CheckResponse],
    intents: list[ResolvedSimulationIntent],
) -> ResolvedSimulationIntent:
    if len(intents) == 1:
        return intents[0]

    primary = intents[0]
    secondary = intents[1]

    if assignment.persona == "overlap-averse":
        return min(intents[:2], key=lambda intent: _crowding_score(checks_by_brief[intent.brief_id]))

    if assignment.persona == "reviser" and _is_crowded(checks_by_brief[primary.brief_id]):
        return secondary

    if assignment.persona == "cautious" and _is_crowded(checks_by_brief[primary.brief_id]):
        return secondary

    return primary


async def execute_agent_run(
    *,
    client: DejaShipMCPClient,
    assignment: SimulationAgentAssignment,
    intents: list[ResolvedSimulationIntent],
    call_budget: int,
) -> AgentRunSummary:
    state = AgentExecutionState(summary=AgentRunSummary(agent_id=assignment.agent_id))
    await _list_tools(client, state, call_budget)

    checks_by_brief: dict[str, CheckResponse] = {}
    for resolved in intents:
        check = await _check_intent(client, state, call_budget, resolved.fixture.final_intent_input)
        if check is not None:
            checks_by_brief[resolved.brief_id] = check

    if not checks_by_brief:
        state.summary.errors += 1
        return state.summary

    primary = _select_primary_intent(assignment, checks_by_brief, intents)
    primary_intent = primary.fixture.final_intent_input

    if assignment.persona in EXTRA_MONITORING_PERSONAS:
        await _check_intent(client, state, call_budget, primary_intent)

    if assignment.persona in OVERLAP_AVERSE_PERSONAS and _is_crowded(checks_by_brief[primary.brief_id]) and len(intents) == 1:
        state.summary.skips += 1
    else:
        claim = await _claim_intent(client, state, call_budget, primary)
        if claim is not None:
            if assignment.persona in EXTRA_MONITORING_PERSONAS:
                await _check_intent(client, state, call_budget, primary_intent)
            resolution_status = _resolution_status(assignment.persona, primary.fixture.planned_resolution)
            if resolution_status is not None:
                await _update_claim(
                    client,
                    state,
                    call_budget,
                    claim_id=claim.claim_id,
                    edit_token=claim.edit_token,
                    brief_id=primary.brief_id,
                    status=resolution_status,
                    agent_id=assignment.agent_id,
                )

    while state.calls_used < call_budget:
        await _check_intent(client, state, call_budget, primary_intent)

    return state.summary
