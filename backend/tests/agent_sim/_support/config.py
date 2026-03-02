from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from tests.agent_sim._support.catalog import get_agent_sim_paths

from tests.agent_sim._support.types import AgentSimLLMSettings


class _AgentSimEnvSettings(BaseSettings):
    provider: str | None = Field(default=None, alias="DEJASHIP_AGENT_SIM_LLM_PROVIDER")
    base_url: str | None = Field(default=None, alias="DEJASHIP_AGENT_SIM_LLM_BASE_URL")
    api_key: str | None = Field(default=None, alias="DEJASHIP_AGENT_SIM_LLM_API_KEY")
    default_model: str | None = Field(default=None, alias="DEJASHIP_AGENT_SIM_DEFAULT_MODEL")
    model_set: str = Field(default="smoke", alias="DEJASHIP_AGENT_SIM_MODEL_SET")

    model_config = SettingsConfigDict(
        env_file=get_agent_sim_paths().repo_root / ".env",
        extra="ignore",
    )


def load_agent_sim_llm_settings() -> AgentSimLLMSettings:
    return AgentSimLLMSettings.model_validate(_AgentSimEnvSettings().model_dump())
