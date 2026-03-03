import pytest

from tests.agent_sim._support import config
from tests.agent_sim._support.catalog import resolve_enabled_model_aliases


pytestmark = pytest.mark.agent_sim


def test_env_loader_prefers_process_environment(monkeypatch):
    monkeypatch.setenv("DEJASHIP_AGENT_SIM_LLM_PROVIDER", "env-provider")
    monkeypatch.setenv("DEJASHIP_AGENT_SIM_MODEL_SET", "nightly")

    settings = config.load_agent_sim_llm_settings()

    assert settings.provider == "env-provider"
    assert settings.model_set == "nightly"


def test_env_loader_returns_unconfigured_state_without_secrets(monkeypatch):
    class FakeEnvSettings:
        def model_dump(self):
            return {
                "provider": None,
                "base_url": None,
                "api_key": None,
                "default_model": None,
                "model_set": "smoke",
            }

    monkeypatch.setattr(config, "_AgentSimEnvSettings", lambda: FakeEnvSettings())

    settings = config.load_agent_sim_llm_settings()

    assert settings.is_configured() is False
    assert settings.model_set == "smoke"


def test_resolve_enabled_model_aliases_allows_direct_enabled_lookup(agent_sim_model_matrix):
    resolved = resolve_enabled_model_aliases(
        agent_sim_model_matrix,
        ["gpt-oss-120b", "step-3-5-flash"],
    )

    assert [alias for alias, _ in resolved] == ["gpt-oss-120b", "step-3-5-flash"]


def test_resolve_enabled_model_aliases_rejects_disabled_models(agent_sim_model_matrix):
    with pytest.raises(ValueError, match="unknown or disabled model aliases"):
        resolve_enabled_model_aliases(
            agent_sim_model_matrix,
            ["not-a-real-model"],
        )
