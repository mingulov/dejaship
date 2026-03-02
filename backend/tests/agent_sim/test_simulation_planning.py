from collections import Counter

import pytest

from tests.agent_sim._support.simulation import build_simulation_plan, calculate_call_budgets


pytestmark = pytest.mark.agent_sim


def test_build_simulation_plan_matches_scenario(agent_sim_catalog, agent_sim_model_matrix, agent_sim_scenario_matrix):
    scenario = agent_sim_scenario_matrix.scenarios["local"]

    plan = build_simulation_plan(
        scenario_name="local",
        scenario=scenario,
        model_matrix=agent_sim_model_matrix,
        catalog=agent_sim_catalog,
        seed=7,
    )

    assert plan.agent_count == scenario.agent_count
    assert plan.total_calls_target == scenario.total_calls_target
    assert len(plan.assignments) == scenario.agent_count
    assert all(assignment.model_alias in agent_sim_model_matrix.sets["default"] for assignment in plan.assignments)


def test_build_simulation_plan_respects_persona_mix(agent_sim_catalog, agent_sim_model_matrix, agent_sim_scenario_matrix):
    scenario = agent_sim_scenario_matrix.scenarios["smoke"]

    plan = build_simulation_plan(
        scenario_name="smoke",
        scenario=scenario,
        model_matrix=agent_sim_model_matrix,
        catalog=agent_sim_catalog,
        seed=3,
    )

    persona_counts = Counter(assignment.persona for assignment in plan.assignments)
    assert persona_counts == Counter(scenario.persona_mix)


def test_overlap_heavy_scenario_assigns_multiple_briefs(agent_sim_catalog, agent_sim_model_matrix, agent_sim_scenario_matrix):
    scenario = agent_sim_scenario_matrix.scenarios["stress"]

    plan = build_simulation_plan(
        scenario_name="stress",
        scenario=scenario,
        model_matrix=agent_sim_model_matrix,
        catalog=agent_sim_catalog,
        seed=11,
    )

    assert any(len(assignment.brief_ids) > 1 for assignment in plan.assignments)
    overlap_counts = Counter(brief_id for assignment in plan.assignments for brief_id in assignment.brief_ids)
    assert any(count >= 2 for count in overlap_counts.values())


def test_calculate_call_budgets_matches_total(agent_sim_catalog, agent_sim_model_matrix, agent_sim_scenario_matrix):
    scenario = agent_sim_scenario_matrix.scenarios["smoke"]
    plan = build_simulation_plan(
        scenario_name="smoke",
        scenario=scenario,
        model_matrix=agent_sim_model_matrix,
        catalog=agent_sim_catalog,
        seed=5,
    )

    budgets = calculate_call_budgets(plan)

    assert sum(budgets.values()) == scenario.total_calls_target
    assert all(budget >= 4 for budget in budgets.values())
