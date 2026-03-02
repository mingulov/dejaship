from collections import Counter

import pytest

from dejaship.config import settings
from dejaship.schemas import IntentInput
from tests.agent_sim._support.catalog import get_agent_sim_paths


pytestmark = pytest.mark.agent_sim


def test_fixture_directories_exist():
    paths = get_agent_sim_paths()
    assert paths.fixtures_root.exists()
    assert paths.prompts_root.exists()


def test_app_catalog_has_expected_brief_count(agent_sim_catalog):
    assert len(agent_sim_catalog.briefs) == 20


def test_app_briefs_provide_valid_seed_payloads(agent_sim_catalog):
    for brief in agent_sim_catalog.briefs:
        payload = IntentInput(
            core_mechanic=brief.title[: settings.CORE_MECHANIC_MAX_LENGTH],
            keywords=brief.seed_keywords,
        )
        assert payload.keywords == brief.seed_keywords


def test_prompt_briefs_are_substantive(agent_sim_catalog):
    for brief in agent_sim_catalog.briefs:
        sentence_count = brief.prompt_rendered_brief.count(".")
        assert sentence_count >= 4, f"{brief.id} should have a multi-sentence rendered brief"


def test_catalog_has_deliberate_overlap_groups(agent_sim_catalog):
    counts = Counter(brief.expected_overlap_group for brief in agent_sim_catalog.briefs)
    shared_groups = {group: count for group, count in counts.items() if count >= 2}
    ambiguous_briefs = [brief for brief in agent_sim_catalog.briefs if brief.adjacent_overlap_groups]

    assert len(shared_groups) >= 4
    assert len(ambiguous_briefs) >= 4


def test_model_matrix_has_expected_sets(agent_sim_model_matrix):
    assert {"smoke", "default", "search-probe", "coverage-max", "nightly"} <= set(
        agent_sim_model_matrix.sets
    )
    assert len(agent_sim_model_matrix.sets["smoke"]) >= 2
    assert len(agent_sim_model_matrix.sets["default"]) >= 2
    assert len(agent_sim_model_matrix.sets["search-probe"]) > len(
        agent_sim_model_matrix.sets["default"]
    )
    assert len(agent_sim_model_matrix.sets["coverage-max"]) >= len(
        agent_sim_model_matrix.sets["search-probe"]
    )
    assert len(agent_sim_model_matrix.sets["nightly"]) >= len(
        agent_sim_model_matrix.sets["coverage-max"]
    )


def test_scenario_matrix_matches_expected_scale(agent_sim_scenario_matrix):
    scenarios = agent_sim_scenario_matrix.scenarios

    assert scenarios["smoke"].agent_count == 4
    assert scenarios["local"].agent_count == 10
    assert scenarios["stress"].agent_count == 20
    assert scenarios["hundred-agent"].agent_count == 100
    assert scenarios["stress"].total_calls_target == 3000
    assert scenarios["hundred-agent"].total_calls_target == 10000
    assert scenarios["live-smoke"].requires_live_llm is True
    assert scenarios["smoke"].model_set == "smoke"
    assert scenarios["local"].model_set == "smoke"
    assert scenarios["extended"].model_set == "smoke"
    assert scenarios["stress"].model_set == "smoke"
    assert scenarios["stale-cleanup"].run_stale_cleanup is True
    assert scenarios["smoke"].require_stored_fixtures is True
    assert scenarios["local"].total_calls_target < scenarios["stress"].total_calls_target
