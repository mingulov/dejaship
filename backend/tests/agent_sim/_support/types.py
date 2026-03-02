from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from dejaship.config import settings
from dejaship.keyword_utils import KEYWORD_PATTERN
from dejaship.schemas import IntentInput


def _validate_keyword(value: str) -> str:
    if len(value) < settings.KEYWORD_MIN_LENGTH or len(value) > settings.KEYWORD_MAX_LENGTH:
        raise ValueError(
            f"keyword '{value}' must be {settings.KEYWORD_MIN_LENGTH}-{settings.KEYWORD_MAX_LENGTH} chars"
        )
    if not KEYWORD_PATTERN.match(value):
        raise ValueError(f"keyword '{value}' must match DejaShip keyword rules")
    return value


class AppBrief(BaseModel):
    id: str = Field(min_length=3, max_length=80)
    title: str = Field(min_length=10, max_length=160)
    category: str = Field(min_length=3, max_length=80)
    target_customer: str = Field(min_length=20, max_length=400)
    problem: str = Field(min_length=30, max_length=600)
    workflow: str = Field(min_length=30, max_length=600)
    recurring_revenue_model: str = Field(min_length=20, max_length=300)
    pricing_shape: str = Field(min_length=10, max_length=200)
    distribution_channel: str = Field(min_length=10, max_length=200)
    constraints: list[str] = Field(min_length=2, max_length=8)
    must_have_features: list[str] = Field(min_length=3, max_length=10)
    seed_keywords: list[str] = Field(min_length=settings.MIN_KEYWORDS, max_length=12)
    expected_overlap_group: str = Field(min_length=3, max_length=80)
    adjacent_overlap_groups: list[str] = Field(default_factory=list, max_length=4)
    anti_goals: list[str] = Field(default_factory=list, max_length=5)
    success_metric: str = Field(min_length=10, max_length=200)
    prompt_rendered_brief: str = Field(min_length=250, max_length=4000)

    @field_validator("id", "category", "expected_overlap_group")
    @classmethod
    def validate_slug_fields(cls, value: str) -> str:
        return _validate_keyword(value)

    @field_validator("seed_keywords")
    @classmethod
    def validate_seed_keywords(cls, values: list[str]) -> list[str]:
        return [_validate_keyword(value) for value in values]

    @field_validator("adjacent_overlap_groups")
    @classmethod
    def validate_adjacent_overlap_groups(cls, values: list[str]) -> list[str]:
        return [_validate_keyword(value) for value in values]

    @model_validator(mode="after")
    def ensure_prompt_mentions_title(self) -> "AppBrief":
        title_words = {word.lower() for word in self.title.split() if len(word) > 4}
        prompt_lower = self.prompt_rendered_brief.lower()
        if title_words and not any(word in prompt_lower for word in title_words):
            raise ValueError("prompt_rendered_brief should reflect the title wording")
        return self


class AppCatalog(BaseModel):
    briefs: list[AppBrief] = Field(min_length=20)

    @model_validator(mode="after")
    def ensure_unique_ids(self) -> "AppCatalog":
        ids = [brief.id for brief in self.briefs]
        if len(ids) != len(set(ids)):
            raise ValueError("app brief ids must be unique")
        return self


class ModelEntry(BaseModel):
    model: str = Field(min_length=3, max_length=200)
    role: str = Field(min_length=3, max_length=40)
    weight: int = Field(ge=1, le=20)
    enabled: bool = True
    generation_mode: Literal["tools", "json_text"] = "tools"
    supports_system_role: bool = True
    notes: str | None = Field(default=None, max_length=300)


class ModelMatrix(BaseModel):
    sets: dict[str, list[str]]
    models: dict[str, ModelEntry]

    @field_validator("sets")
    @classmethod
    def ensure_non_empty_sets(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        if not value:
            raise ValueError("at least one model set is required")
        for set_name, model_ids in value.items():
            _validate_keyword(set_name)
            if not model_ids:
                raise ValueError(f"model set '{set_name}' must contain at least one model")
        return value

    @field_validator("models")
    @classmethod
    def ensure_non_empty_models(cls, value: dict[str, ModelEntry]) -> dict[str, ModelEntry]:
        if not value:
            raise ValueError("at least one model entry is required")
        for model_id in value:
            _validate_keyword(model_id)
        return value

    @model_validator(mode="after")
    def ensure_sets_reference_known_models(self) -> "ModelMatrix":
        known = set(self.models)
        missing = {
            f"{set_name}:{model_id}"
            for set_name, model_ids in self.sets.items()
            for model_id in model_ids
            if model_id not in known
        }
        if missing:
            raise ValueError(f"model sets reference unknown models: {sorted(missing)}")
        return self


class ScenarioDefinition(BaseModel):
    agent_count: int = Field(ge=1, le=100)
    total_calls_target: int = Field(ge=1, le=10000)
    model_set: str = Field(min_length=3, max_length=80)
    persona_mix: dict[str, int] = Field(min_length=1)
    brief_selection_strategy: str = Field(min_length=3, max_length=80)
    requires_live_llm: bool = False
    require_stored_fixtures: bool = False
    run_stale_cleanup: bool = False
    keyword_drop_min: int = Field(ge=0, le=10, default=0)
    keyword_drop_max: int = Field(ge=0, le=10, default=0)
    description: str = Field(min_length=10, max_length=300)

    @field_validator("model_set", "brief_selection_strategy")
    @classmethod
    def validate_slug_fields(cls, value: str) -> str:
        return _validate_keyword(value)

    @field_validator("persona_mix")
    @classmethod
    def validate_persona_mix(cls, value: dict[str, int]) -> dict[str, int]:
        for persona, count in value.items():
            _validate_keyword(persona)
            if count < 1:
                raise ValueError("persona counts must be positive")
        return value


class ScenarioMatrix(BaseModel):
    scenarios: dict[str, ScenarioDefinition]

    @field_validator("scenarios")
    @classmethod
    def ensure_non_empty_scenarios(cls, value: dict[str, ScenarioDefinition]) -> dict[str, ScenarioDefinition]:
        if not value:
            raise ValueError("at least one scenario is required")
        for scenario_name in value:
            _validate_keyword(scenario_name)
        return value


class AgentSimLLMSettings(BaseModel):
    provider: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    default_model: str | None = None
    model_set: str = "smoke"

    def is_configured(self) -> bool:
        return bool(self.provider and self.base_url and self.api_key)


class AgentSimPaths(BaseModel):
    repo_root: Path
    backend_root: Path
    agent_sim_root: Path
    fixtures_root: Path
    prompts_root: Path


class GeneratedIntentDraft(BaseModel):
    core_mechanic: str = Field(min_length=1, max_length=settings.CORE_MECHANIC_MAX_LENGTH)
    keywords: list[str] = Field(min_length=1, max_length=settings.MAX_KEYWORDS)


class KeywordBuildResult(BaseModel):
    llm_keywords: list[str]
    derived_keywords: list[str]
    final_keywords: list[str] = Field(min_length=settings.MIN_KEYWORDS, max_length=settings.MAX_KEYWORDS)
    keyword_provenance: dict[str, list[str]]

    @field_validator("llm_keywords", "derived_keywords", "final_keywords")
    @classmethod
    def validate_keyword_lists(cls, values: list[str]) -> list[str]:
        return [_validate_keyword(value) for value in values]

    @field_validator("keyword_provenance")
    @classmethod
    def validate_keyword_provenance(cls, values: dict[str, list[str]]) -> dict[str, list[str]]:
        for keyword, sources in values.items():
            _validate_keyword(keyword)
            if not sources:
                raise ValueError(f"keyword provenance missing sources for '{keyword}'")
        return values

    @model_validator(mode="after")
    def ensure_final_keywords_have_provenance(self) -> "KeywordBuildResult":
        missing = [keyword for keyword in self.final_keywords if keyword not in self.keyword_provenance]
        if missing:
            raise ValueError(f"final keywords missing provenance: {missing}")
        return self


class StoredFixtureMetadata(BaseModel):
    provider: str = Field(min_length=1, max_length=80)
    model_alias: str = Field(min_length=3, max_length=80)
    model_name: str = Field(min_length=3, max_length=200)
    prompt_name: str = Field(min_length=3, max_length=80)
    prompt_version: str = Field(min_length=1, max_length=40)
    brief_hash: str = Field(min_length=32, max_length=64)
    prompt_hash: str = Field(min_length=32, max_length=64)
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @field_validator("model_alias", "prompt_name")
    @classmethod
    def validate_keyword_style_fields(cls, value: str) -> str:
        return _validate_keyword(value)


class StoredLLMFixture(BaseModel):
    brief_id: str = Field(min_length=3, max_length=80)
    metadata: StoredFixtureMetadata
    raw_prompt: str = Field(min_length=20)
    raw_response: dict[str, Any]
    response_text: str = Field(min_length=2)
    llm_output: GeneratedIntentDraft
    keyword_result: KeywordBuildResult
    final_intent_input: IntentInput
    planned_resolution: str = Field(default="claim", pattern=r"^(claim|revise|skip|ship|abandon)$")

    @field_validator("brief_id")
    @classmethod
    def validate_brief_id(cls, value: str) -> str:
        return _validate_keyword(value)

    @model_validator(mode="after")
    def ensure_final_payload_matches_keywords(self) -> "StoredLLMFixture":
        if self.final_intent_input.keywords != self.keyword_result.final_keywords:
            raise ValueError("final_intent_input keywords must match keyword_result.final_keywords")
        return self


class ResolvedSimulationIntent(BaseModel):
    brief_id: str = Field(min_length=3, max_length=80)
    model_alias: str = Field(min_length=3, max_length=80)
    model_name: str = Field(min_length=3, max_length=200)
    source: Literal["stored", "synthetic"]
    fixture: StoredLLMFixture

    @field_validator("brief_id", "model_alias")
    @classmethod
    def validate_slug_fields(cls, value: str) -> str:
        return _validate_keyword(value)


class MCPUpdateResult(BaseModel):
    success: bool
    error: str | None = None


class SimulationAgentAssignment(BaseModel):
    agent_id: str = Field(min_length=3, max_length=80)
    persona: str = Field(min_length=3, max_length=80)
    model_alias: str = Field(min_length=3, max_length=80)
    model_name: str = Field(min_length=3, max_length=200)
    brief_ids: list[str] = Field(min_length=1)
    seed: int = Field(ge=0)
    keyword_drop_count: int = Field(ge=0, le=10, default=0)

    @field_validator("agent_id", "persona", "model_alias")
    @classmethod
    def validate_slug_like_fields(cls, value: str) -> str:
        return _validate_keyword(value)

    @field_validator("brief_ids")
    @classmethod
    def validate_brief_ids(cls, values: list[str]) -> list[str]:
        return [_validate_keyword(value) for value in values]


class SimulationPlan(BaseModel):
    scenario_name: str = Field(min_length=3, max_length=80)
    agent_count: int = Field(ge=1)
    total_calls_target: int = Field(ge=1)
    model_set: str = Field(min_length=3, max_length=80)
    require_stored_fixtures: bool = False
    run_stale_cleanup: bool = False
    keyword_drop_min: int = Field(ge=0, le=10, default=0)
    keyword_drop_max: int = Field(ge=0, le=10, default=0)
    assignments: list[SimulationAgentAssignment] = Field(min_length=1)

    @field_validator("scenario_name", "model_set")
    @classmethod
    def validate_slug_fields(cls, value: str) -> str:
        return _validate_keyword(value)


class SimulationEvent(BaseModel):
    event_index: int = Field(ge=0)
    event_type: str = Field(min_length=3, max_length=80)
    agent_id: str = Field(min_length=3, max_length=80)
    persona: str = Field(min_length=3, max_length=80)
    model_alias: str = Field(min_length=3, max_length=80)
    brief_id: str | None = Field(default=None, min_length=3, max_length=80)
    core_mechanic: str | None = Field(default=None, min_length=1, max_length=settings.CORE_MECHANIC_MAX_LENGTH)
    claim_id: str | None = Field(default=None, min_length=8, max_length=80)
    status: str | None = Field(default=None, min_length=3, max_length=40)
    crowded: bool | None = None
    density_in_progress: int | None = Field(default=None, ge=0)
    density_shipped: int | None = Field(default=None, ge=0)
    density_abandoned: int | None = Field(default=None, ge=0)
    closest_count: int | None = Field(default=None, ge=0)
    closest_mechanics: list[str] = Field(default_factory=list)
    message: str | None = Field(default=None, max_length=500)

    @field_validator("agent_id", "persona", "model_alias")
    @classmethod
    def validate_agent_fields(cls, value: str) -> str:
        return _validate_keyword(value)

    @field_validator("brief_id")
    @classmethod
    def validate_optional_brief_id(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _validate_keyword(value)


class AgentRunSummary(BaseModel):
    agent_id: str = Field(min_length=3, max_length=80)
    persona: str = Field(min_length=3, max_length=80)
    model_alias: str = Field(min_length=3, max_length=80)
    tool_lists: int = Field(ge=0, default=0)
    checks: int = Field(ge=0, default=0)
    claims: int = Field(ge=0, default=0)
    updates: int = Field(ge=0, default=0)
    stale_cleanup_actions: int = Field(ge=0, default=0)
    skips: int = Field(ge=0, default=0)
    errors: int = Field(ge=0, default=0)
    crowded_checks: int = Field(ge=0, default=0)
    keyword_drop_count: int = Field(ge=0, default=0)
    partial_keyword_requests: int = Field(ge=0, default=0)
    claimed_brief_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    shipped_claim_ids: list[str] = Field(default_factory=list)
    abandoned_claim_ids: list[str] = Field(default_factory=list)
    stale_abandoned_claim_ids: list[str] = Field(default_factory=list)
    unresolved_claim_ids: list[str] = Field(default_factory=list)
    completed_statuses: list[str] = Field(default_factory=list)
    fixture_sources: list[str] = Field(default_factory=list)
    events: list[SimulationEvent] = Field(default_factory=list)

    @field_validator("agent_id", "persona", "model_alias")
    @classmethod
    def validate_agent_id(cls, value: str) -> str:
        return _validate_keyword(value)

    @field_validator(
        "claimed_brief_ids",
        "claim_ids",
        "shipped_claim_ids",
        "abandoned_claim_ids",
        "stale_abandoned_claim_ids",
        "unresolved_claim_ids",
    )
    @classmethod
    def validate_claimed_brief_ids(cls, values: list[str]) -> list[str]:
        return [value if value.startswith("claim-") else _validate_keyword(value) for value in values]


class ModelSimulationSummary(BaseModel):
    model_alias: str = Field(min_length=3, max_length=80)
    total_agents: int = Field(ge=0, default=0)
    checks: int = Field(ge=0, default=0)
    claims: int = Field(ge=0, default=0)
    updates: int = Field(ge=0, default=0)
    shipped: int = Field(ge=0, default=0)
    abandoned: int = Field(ge=0, default=0)
    stale_abandoned: int = Field(ge=0, default=0)
    skips: int = Field(ge=0, default=0)
    errors: int = Field(ge=0, default=0)
    crowded_checks: int = Field(ge=0, default=0)
    partial_keyword_requests: int = Field(ge=0, default=0)
    overlap_evaluable_checks: int = Field(ge=0, default=0)
    overlap_hits: int = Field(ge=0, default=0)
    overlap_precision: float = Field(ge=0.0, default=0.0)
    overlap_recall_proxy: float = Field(ge=0.0, default=0.0)
    unique_claimed_briefs: list[str] = Field(default_factory=list)

    @field_validator("model_alias")
    @classmethod
    def validate_model_alias(cls, value: str) -> str:
        return _validate_keyword(value)

    @field_validator("unique_claimed_briefs")
    @classmethod
    def validate_unique_claimed_briefs_for_model(cls, values: list[str]) -> list[str]:
        return [_validate_keyword(value) for value in values]


class PersonaSimulationSummary(BaseModel):
    persona: str = Field(min_length=3, max_length=80)
    total_agents: int = Field(ge=0, default=0)
    claims: int = Field(ge=0, default=0)
    skips: int = Field(ge=0, default=0)
    partial_keyword_requests: int = Field(ge=0, default=0)
    crowded_decisions: int = Field(ge=0, default=0)
    clear_decisions: int = Field(ge=0, default=0)
    claims_after_clear: int = Field(ge=0, default=0)
    skips_after_crowded: int = Field(ge=0, default=0)
    revision_attempts: int = Field(ge=0, default=0)
    revision_successes: int = Field(ge=0, default=0)

    @field_validator("persona")
    @classmethod
    def validate_persona(cls, value: str) -> str:
        return _validate_keyword(value)


class SimulationMetrics(BaseModel):
    claim_rate: float = Field(ge=0.0)
    ship_rate: float = Field(ge=0.0)
    abandon_rate: float = Field(ge=0.0)
    stale_cleanup_rate: float = Field(ge=0.0)
    crowded_check_rate: float = Field(ge=0.0)
    stored_fixture_ratio: float = Field(ge=0.0)
    duplicate_brief_claim_rate: float = Field(ge=0.0)
    unresolved_claim_rate: float = Field(ge=0.0)
    partial_keyword_request_rate: float = Field(ge=0.0)
    average_density_in_progress: float = Field(ge=0.0)
    average_density_shipped: float = Field(ge=0.0)
    average_density_abandoned: float = Field(ge=0.0)
    overlap_hit_rate: float = Field(ge=0.0)
    overlap_precision: float = Field(ge=0.0)
    overlap_recall_proxy: float = Field(ge=0.0)
    claim_when_clear_rate: float = Field(ge=0.0)
    skip_when_crowded_rate: float = Field(ge=0.0)
    revision_success_rate: float = Field(ge=0.0)
    duplicate_overlap_group_rate: float = Field(ge=0.0)
    quality_flags: list[str] = Field(default_factory=list)


class SimulationReport(BaseModel):
    scenario_name: str = Field(min_length=3, max_length=80)
    total_agents: int = Field(ge=1)
    total_calls: int = Field(ge=0, default=0)
    tool_lists: int = Field(ge=0, default=0)
    checks: int = Field(ge=0, default=0)
    claims: int = Field(ge=0, default=0)
    updates: int = Field(ge=0, default=0)
    stale_cleanup_actions: int = Field(ge=0, default=0)
    errors: int = Field(ge=0, default=0)
    skips: int = Field(ge=0, default=0)
    status_counts: dict[str, int] = Field(default_factory=dict)
    fixture_source_counts: dict[str, int] = Field(default_factory=dict)
    unique_claimed_briefs: list[str] = Field(default_factory=list)
    unresolved_claim_ids: list[str] = Field(default_factory=list)
    event_count: int = Field(ge=0, default=0)
    model_summaries: dict[str, ModelSimulationSummary] = Field(default_factory=dict)
    persona_summaries: dict[str, PersonaSimulationSummary] = Field(default_factory=dict)
    metrics: SimulationMetrics = Field(default_factory=SimulationMetrics)
    agent_summaries: list[AgentRunSummary] = Field(default_factory=list)

    @field_validator("scenario_name")
    @classmethod
    def validate_scenario_name(cls, value: str) -> str:
        return _validate_keyword(value)

    @field_validator("status_counts", "fixture_source_counts")
    @classmethod
    def validate_count_mappings(cls, values: dict[str, int]) -> dict[str, int]:
        for key, count in values.items():
            if count < 0:
                raise ValueError(f"count mapping '{key}' must be non-negative")
        return values

    @field_validator("unique_claimed_briefs")
    @classmethod
    def validate_unique_claimed_briefs(cls, values: list[str]) -> list[str]:
        return [_validate_keyword(value) for value in values]

    @field_validator("unresolved_claim_ids")
    @classmethod
    def validate_unresolved_claim_ids(cls, values: list[str]) -> list[str]:
        return values


class PersistedIntentRow(BaseModel):
    core_mechanic: str = Field(min_length=1, max_length=settings.CORE_MECHANIC_MAX_LENGTH)
    status: str = Field(min_length=3, max_length=40)
    resolution_url: str | None = Field(default=None, max_length=2048)
    keywords: list[str] = Field(default_factory=list)

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, values: list[str]) -> list[str]:
        return [_validate_keyword(value) for value in values]


class SimulationDatabaseSnapshot(BaseModel):
    total_rows: int = Field(ge=0)
    status_counts: dict[str, int] = Field(default_factory=dict)
    shipped_with_resolution_url: int = Field(ge=0, default=0)
    abandoned_with_resolution_url: int = Field(ge=0, default=0)
    in_progress_with_resolution_url: int = Field(ge=0, default=0)
    rows: list[PersistedIntentRow] = Field(default_factory=list)

    @field_validator("status_counts")
    @classmethod
    def validate_status_counts(cls, values: dict[str, int]) -> dict[str, int]:
        for key, count in values.items():
            if count < 0:
                raise ValueError(f"status count '{key}' must be non-negative")
        return values
