from tests.agent_sim._support.catalog import get_agent_sim_paths
from tests.agent_sim._support.fixture_store import (
    FixtureIndex,
    hash_app_brief,
    build_prompt_hash,
    build_synthetic_fixture,
    fixture_output_path,
    read_fixture,
    validate_fixture_against_catalog,
    write_fixture,
)
from tests.agent_sim._support.keyword_builder import build_keyword_result
from tests.agent_sim._support.types import GeneratedIntentDraft, StoredFixtureMetadata, StoredLLMFixture
from dejaship.schemas import IntentInput


def test_fixture_output_path_uses_versioned_layout():
    path = fixture_output_path("llama-3-1-8b-instruct", "hvac-service-plan-ops")
    assert path == (
        get_agent_sim_paths().fixtures_root
        / "llm_outputs"
        / "llama-3-1-8b-instruct"
        / "hvac-service-plan-ops.json"
    )


def test_fixture_store_round_trip(agent_sim_catalog, tmp_path, monkeypatch):
    brief = agent_sim_catalog.briefs[0]
    keyword_result = build_keyword_result(brief, ["renewals", "dispatch", "hvac"])
    fixture = StoredLLMFixture(
        brief_id=brief.id,
        metadata=StoredFixtureMetadata(
            provider="openai",
            model_alias="llama-3-1-8b-instruct",
            model_name="meta/llama-3.1-8b-instruct",
            prompt_name="intent-from-brief",
            prompt_version="v1",
            brief_hash="a" * 64,
            prompt_hash="b" * 64,
        ),
        raw_prompt="Prompt text with enough content for fixture validation.",
        raw_response={"choices": [{"message": {"content": "{\"core_mechanic\": \"x\", \"keywords\": [\"hvac\"]}"}}]},
        response_text='{"core_mechanic":"x","keywords":["hvac"]}',
        llm_output=GeneratedIntentDraft(core_mechanic="hvac renewals workflow", keywords=["hvac"]),
        keyword_result=keyword_result,
        final_intent_input=IntentInput(
            core_mechanic="hvac renewals workflow",
            keywords=keyword_result.final_keywords,
        ),
    )

    from tests.agent_sim._support import fixture_store

    monkeypatch.setattr(
        fixture_store,
        "get_agent_sim_paths",
        lambda: get_agent_sim_paths().model_copy(update={"fixtures_root": tmp_path}),
    )

    path = write_fixture(fixture)
    loaded = read_fixture(path)

    assert path.exists()
    assert loaded.brief_id == fixture.brief_id
    assert loaded.final_intent_input.keywords == fixture.final_intent_input.keywords


def test_build_synthetic_fixture_uses_catalog_defaults(agent_sim_catalog):
    brief = agent_sim_catalog.briefs[0]

    fixture = build_synthetic_fixture(
        brief,
        model_alias="llama-3-1-8b-instruct",
        model_name="meta/llama-3.1-8b-instruct",
    )

    assert fixture.metadata.provider == "synthetic"
    assert fixture.llm_output.core_mechanic == brief.title
    assert fixture.final_intent_input.keywords == fixture.keyword_result.final_keywords


def test_fixture_index_resolves_synthetic_fallback(agent_sim_catalog):
    brief = agent_sim_catalog.briefs[0]
    fixture_index = FixtureIndex([])

    resolved = fixture_index.resolve_or_synthesize(
        brief=brief,
        model_alias="llama-3-1-8b-instruct",
        model_name="meta/llama-3.1-8b-instruct",
    )

    assert resolved.source == "synthetic"
    assert resolved.fixture.brief_id == brief.id


def test_validate_fixture_against_catalog_accepts_matching_hashes(agent_sim_catalog):
    brief = agent_sim_catalog.briefs[0]
    rendered_prompt, prompt_hash = build_prompt_hash(
        brief,
        prompt_name="intent_from_brief",
        prompt_version="v1",
    )
    keyword_result = build_keyword_result(brief, ["renewals", "dispatch", "hvac"])
    fixture = StoredLLMFixture(
        brief_id=brief.id,
        metadata=StoredFixtureMetadata(
            provider="openai",
            model_alias="llama-3-1-8b-instruct",
            model_name="meta/llama-3.1-8b-instruct",
            prompt_name="intent-from-brief",
            prompt_version="v1",
            brief_hash=hash_app_brief(brief),
            prompt_hash=prompt_hash,
        ),
        raw_prompt=rendered_prompt,
        raw_response={"choices": [{"message": {"content": "{\"core_mechanic\": \"x\", \"keywords\": [\"hvac\"]}"}}]},
        response_text='{"core_mechanic":"x","keywords":["hvac"]}',
        llm_output=GeneratedIntentDraft(core_mechanic="hvac renewals workflow", keywords=["hvac"]),
        keyword_result=keyword_result,
        final_intent_input=IntentInput(
            core_mechanic="hvac renewals workflow",
            keywords=keyword_result.final_keywords,
        ),
    )

    assert validate_fixture_against_catalog(fixture, catalog=agent_sim_catalog) == []


def test_validate_fixture_against_catalog_detects_prompt_drift(agent_sim_catalog):
    brief = agent_sim_catalog.briefs[0]
    fixture = build_synthetic_fixture(
        brief,
        model_alias="llama-3-1-8b-instruct",
        model_name="meta/llama-3.1-8b-instruct",
    )
    fixture.metadata.provider = "openai"
    fixture.metadata.prompt_name = "intent-from-brief"
    fixture.metadata.prompt_version = "v1"
    fixture.metadata.brief_hash = hash_app_brief(brief)
    fixture.metadata.prompt_hash = "0" * 64
    fixture.raw_prompt = "stale prompt"

    errors = validate_fixture_against_catalog(fixture, catalog=agent_sim_catalog)

    assert len(errors) >= 1
