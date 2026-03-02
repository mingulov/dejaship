import pytest

from tests.agent_sim._support.fixture_store import (
    iter_fixture_paths,
    read_fixture,
    validate_fixture_against_catalog,
)


pytestmark = pytest.mark.agent_sim


def test_fixture_replay_directory_structure_exists():
    paths = iter_fixture_paths()
    assert paths == [] or all(path.suffix == ".json" for path in paths)


def test_stored_fixtures_validate_when_present():
    fixture_paths = iter_fixture_paths()
    if not fixture_paths:
        pytest.skip("no stored fixtures generated yet")

    for path in fixture_paths:
        fixture = read_fixture(path)
        assert fixture.metadata.prompt_version == "v1"
        assert fixture.final_intent_input.keywords == fixture.keyword_result.final_keywords


def test_stored_fixtures_match_current_catalog_and_prompt(agent_sim_catalog):
    fixture_paths = iter_fixture_paths()
    if not fixture_paths:
        pytest.skip("no stored fixtures generated yet")

    for path in fixture_paths:
        fixture = read_fixture(path)
        assert validate_fixture_against_catalog(fixture, catalog=agent_sim_catalog) == []
