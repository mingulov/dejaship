import pytest

from dejaship.schemas import IntentInput
from tests.agent_sim._support.keyword_builder import build_keyword_result, normalize_keyword_candidate


pytestmark = pytest.mark.agent_sim


def test_normalize_keyword_candidate_handles_spaces_and_case():
    assert normalize_keyword_candidate(" Local Business ") == "local-business"
    assert normalize_keyword_candidate("SEO") == "seo"
    assert normalize_keyword_candidate("!!") is None


def test_keyword_builder_creates_valid_final_keywords(agent_sim_catalog):
    brief = next(brief for brief in agent_sim_catalog.briefs if brief.id == "hvac-service-plan-ops")
    result = build_keyword_result(
        brief,
        ["HVAC", "local business", "renewals", "dispatch", "homeowner"],
    )

    payload = IntentInput(core_mechanic=brief.title, keywords=result.final_keywords)

    assert payload.keywords == result.final_keywords
    assert "hvac" in result.final_keywords
    assert "renewals" in result.final_keywords
    assert "llm" in result.keyword_provenance["hvac"]
    assert "seed_keywords" in result.keyword_provenance["hvac"]


def test_keyword_builder_derives_keywords_without_llm_signal(agent_sim_catalog):
    brief = next(brief for brief in agent_sim_catalog.briefs if brief.id == "therapy-prior-auth-tracker")
    result = build_keyword_result(brief, [])

    assert len(result.final_keywords) >= 5
    assert "therapy" in result.final_keywords
    assert "prior-auth" in result.final_keywords or "insurance" in result.final_keywords
