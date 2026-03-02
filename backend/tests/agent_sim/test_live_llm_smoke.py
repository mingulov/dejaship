import pytest

from tests.agent_sim._support.catalog import load_prompt_text, resolve_model_set
from tests.agent_sim._support.config import load_agent_sim_llm_settings
from tests.agent_sim._support.llm_provider import LLMProviderError, OpenAICompatibleProvider
from tests.agent_sim._support.prompting import render_intent_prompt


pytestmark = [pytest.mark.agent_sim, pytest.mark.live_llm]


@pytest.mark.asyncio
async def test_live_provider_generates_typed_draft(agent_sim_catalog, agent_sim_model_matrix):
    settings = load_agent_sim_llm_settings()
    if not settings.is_configured():
        pytest.skip("live LLM settings are not configured")

    try:
        provider = OpenAICompatibleProvider(settings, timeout_s=45.0)
    except LLMProviderError as exc:
        pytest.skip(str(exc))

    model_alias, model_entry = resolve_model_set(agent_sim_model_matrix, settings.model_set)[0]
    brief = agent_sim_catalog.briefs[0]
    prompt = render_intent_prompt(load_prompt_text("intent_from_brief_v1"), brief)
    draft, raw_response, response_text = await provider.generate_intent_draft(
        model_name=model_entry.model,
        prompt_text=prompt,
    )

    assert model_alias
    assert draft.core_mechanic
    assert draft.keywords
    assert raw_response
    assert response_text
