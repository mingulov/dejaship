import pytest

from tests.agent_sim._support.assertions import (
    assert_db_snapshot_matches_report,
    assert_report_has_overlap_pressure,
    assert_report_uses_only_stored_fixtures,
    assert_simulation_report,
    assert_swarm_outcomes_have_terminal_states,
)
from tests.agent_sim._support.db_snapshot import fetch_simulation_db_snapshot
from tests.agent_sim._support.simulation import build_simulation_plan, run_simulation


pytestmark = pytest.mark.agent_sim


async def _run_and_assert_scenario(
    *,
    scenario_name: str,
    seed: int,
    agent_sim_catalog,
    agent_sim_fixture_index,
    agent_sim_model_matrix,
    agent_sim_scenario_matrix,
    engine,
    mcp_base_url,
    mcp_http_client_factory,
):
    scenario = agent_sim_scenario_matrix.scenarios[scenario_name]
    plan = build_simulation_plan(
        scenario_name=scenario_name,
        scenario=scenario,
        model_matrix=agent_sim_model_matrix,
        catalog=agent_sim_catalog,
        seed=seed,
    )

    async with mcp_http_client_factory() as mcp_http_client:
        report = await run_simulation(
            plan=plan,
            catalog=agent_sim_catalog,
            fixture_index=agent_sim_fixture_index,
            http_client=mcp_http_client,
            base_url=mcp_base_url,
        )

    snapshot = await fetch_simulation_db_snapshot(engine)

    assert_simulation_report(report, scenario_name=scenario_name, scenario=scenario)
    assert_swarm_outcomes_have_terminal_states(report)
    assert_db_snapshot_matches_report(snapshot, report)
    assert_report_has_overlap_pressure(report, agent_sim_catalog)
    assert_report_uses_only_stored_fixtures(report)

    return report


@pytest.mark.asyncio
async def test_agent_swarm_smoke_scenario(
    agent_sim_catalog,
    agent_sim_fixture_index,
    agent_sim_model_matrix,
    agent_sim_scenario_matrix,
    engine,
    mcp_base_url,
    mcp_http_client_factory,
):
    report = await _run_and_assert_scenario(
        scenario_name="smoke",
        seed=13,
        agent_sim_catalog=agent_sim_catalog,
        agent_sim_fixture_index=agent_sim_fixture_index,
        agent_sim_model_matrix=agent_sim_model_matrix,
        agent_sim_scenario_matrix=agent_sim_scenario_matrix,
        engine=engine,
        mcp_base_url=mcp_base_url,
        mcp_http_client_factory=mcp_http_client_factory,
    )

    assert report.total_agents == 4
    assert report.status_counts.get("shipped", 0) >= 1


@pytest.mark.asyncio
@pytest.mark.slow
async def test_agent_swarm_local_scenario(
    agent_sim_catalog,
    agent_sim_fixture_index,
    agent_sim_model_matrix,
    agent_sim_scenario_matrix,
    engine,
    mcp_base_url,
    mcp_http_client_factory,
):
    report = await _run_and_assert_scenario(
        scenario_name="local",
        seed=17,
        agent_sim_catalog=agent_sim_catalog,
        agent_sim_fixture_index=agent_sim_fixture_index,
        agent_sim_model_matrix=agent_sim_model_matrix,
        agent_sim_scenario_matrix=agent_sim_scenario_matrix,
        engine=engine,
        mcp_base_url=mcp_base_url,
        mcp_http_client_factory=mcp_http_client_factory,
    )

    assert report.total_agents == 10
    assert len(report.unique_claimed_briefs) >= 6


@pytest.mark.asyncio
@pytest.mark.slow
async def test_agent_swarm_extended_scenario(
    agent_sim_catalog,
    agent_sim_fixture_index,
    agent_sim_model_matrix,
    agent_sim_scenario_matrix,
    engine,
    mcp_base_url,
    mcp_http_client_factory,
):
    report = await _run_and_assert_scenario(
        scenario_name="extended",
        seed=23,
        agent_sim_catalog=agent_sim_catalog,
        agent_sim_fixture_index=agent_sim_fixture_index,
        agent_sim_model_matrix=agent_sim_model_matrix,
        agent_sim_scenario_matrix=agent_sim_scenario_matrix,
        engine=engine,
        mcp_base_url=mcp_base_url,
        mcp_http_client_factory=mcp_http_client_factory,
    )

    assert report.total_agents == 12
    assert report.total_calls == 500
    assert len(report.unique_claimed_briefs) >= 7
