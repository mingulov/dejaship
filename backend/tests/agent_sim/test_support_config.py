import pytest

from tests.agent_sim._support import config


pytestmark = pytest.mark.agent_sim


def test_env_loader_prefers_process_environment(monkeypatch):
    monkeypatch.setenv("DEJASHIP_AGENT_SIM_LLM_PROVIDER", "env-provider")
    monkeypatch.setenv("DEJASHIP_AGENT_SIM_MODEL_SET", "nightly")

    settings = config.load_agent_sim_llm_settings()

    assert settings.provider == "env-provider"
    assert settings.model_set == "nightly"
    assert settings.base_url is not None
    assert settings.default_model is not None


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
