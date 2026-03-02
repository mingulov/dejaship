from __future__ import annotations

import hashlib
import json
from pathlib import Path

from dejaship.schemas import IntentInput
from tests.agent_sim._support.keyword_builder import build_keyword_result
from tests.agent_sim._support.catalog import get_agent_sim_paths, load_prompt_text
from tests.agent_sim._support.prompting import render_intent_prompt
from tests.agent_sim._support.types import (
    AppBrief,
    AppCatalog,
    GeneratedIntentDraft,
    ResolvedSimulationIntent,
    StoredFixtureMetadata,
    StoredLLMFixture,
)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def fixture_output_path(
    model_alias: str,
    brief_id: str,
) -> Path:
    paths = get_agent_sim_paths()
    return paths.fixtures_root / "llm_outputs" / model_alias / f"{brief_id}.json"


def fixture_exists(
    model_alias: str,
    brief_id: str,
) -> bool:
    return fixture_output_path(model_alias, brief_id).exists()


def write_fixture(
    fixture: StoredLLMFixture,
) -> Path:
    path = fixture_output_path(
        fixture.metadata.model_alias,
        fixture.brief_id,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(fixture.model_dump_json(indent=2))
    return path


def read_fixture(path: Path) -> StoredLLMFixture:
    return StoredLLMFixture.model_validate(json.loads(path.read_text()))


def iter_fixture_paths() -> list[Path]:
    root = get_agent_sim_paths().fixtures_root / "llm_outputs"
    if not root.exists():
        return []
    return sorted(root.rglob("*.json"))


def _stable_json_hash(payload: dict) -> str:
    return sha256_text(json.dumps(payload, sort_keys=True))


def hash_app_brief(brief: AppBrief) -> str:
    return _stable_json_hash(brief.model_dump(mode="json"))


def build_prompt_hash(brief: AppBrief, *, prompt_name: str, prompt_version: str) -> tuple[str, str]:
    prompt_template = load_prompt_text(f"{prompt_name}_{prompt_version}")
    rendered_prompt = render_intent_prompt(prompt_template, brief)
    return rendered_prompt, sha256_text(rendered_prompt)


def validate_fixture_against_catalog(
    fixture: StoredLLMFixture,
    *,
    catalog: AppCatalog,
) -> list[str]:
    errors: list[str] = []
    brief_map = {brief.id: brief for brief in catalog.briefs}
    brief = brief_map.get(fixture.brief_id)
    if brief is None:
        return [f"unknown brief id '{fixture.brief_id}'"]

    expected_brief_hash = hash_app_brief(brief)
    if fixture.metadata.brief_hash != expected_brief_hash:
        errors.append(
            f"brief hash mismatch for '{fixture.brief_id}': "
            f"{fixture.metadata.brief_hash} != {expected_brief_hash}"
        )

    prompt_name = fixture.metadata.prompt_name.replace("-", "_")
    try:
        rendered_prompt, expected_prompt_hash = build_prompt_hash(
            brief,
            prompt_name=prompt_name,
            prompt_version=fixture.metadata.prompt_version,
        )
    except FileNotFoundError:
        errors.append(
            f"missing prompt template for '{fixture.metadata.prompt_name}' version '{fixture.metadata.prompt_version}'"
        )
    else:
        if fixture.metadata.prompt_hash != expected_prompt_hash:
            errors.append(
                f"prompt hash mismatch for '{fixture.brief_id}'/{fixture.metadata.model_alias}: "
                f"{fixture.metadata.prompt_hash} != {expected_prompt_hash}"
            )
        if fixture.raw_prompt != rendered_prompt:
            errors.append(
                f"raw prompt drift for '{fixture.brief_id}'/{fixture.metadata.model_alias}'"
            )

    return errors


def build_synthetic_fixture(
    brief: AppBrief,
    *,
    model_alias: str = "catalog-baseline",
    model_name: str = "catalog-baseline",
    prompt_name: str = "synthetic-brief",
    prompt_version: str = "baseline-v1",
) -> StoredLLMFixture:
    llm_output = GeneratedIntentDraft(
        core_mechanic=brief.title,
        keywords=brief.seed_keywords[:],
    )
    keyword_result = build_keyword_result(brief, llm_output.keywords)
    final_intent = IntentInput(
        core_mechanic=llm_output.core_mechanic,
        keywords=keyword_result.final_keywords,
    )
    raw_response = llm_output.model_dump(mode="json")
    return StoredLLMFixture(
        brief_id=brief.id,
        metadata=StoredFixtureMetadata(
            provider="synthetic",
            model_alias=model_alias,
            model_name=model_name,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            brief_hash=_stable_json_hash(brief.model_dump(mode="json")),
            prompt_hash=sha256_text(brief.prompt_rendered_brief),
        ),
        raw_prompt=brief.prompt_rendered_brief,
        raw_response=raw_response,
        response_text=json.dumps(raw_response, sort_keys=True),
        llm_output=llm_output,
        keyword_result=keyword_result,
        final_intent_input=final_intent,
        planned_resolution="claim",
    )


class FixtureIndex:
    def __init__(self, fixtures: list[StoredLLMFixture]):
        self._fixtures = fixtures
        self._by_key = {
            (fixture.brief_id, fixture.metadata.model_alias): fixture
            for fixture in fixtures
        }
        self._by_brief: dict[str, list[StoredLLMFixture]] = {}
        for fixture in fixtures:
            self._by_brief.setdefault(fixture.brief_id, []).append(fixture)

    @property
    def fixtures(self) -> list[StoredLLMFixture]:
        return self._fixtures[:]

    def get(self, *, brief_id: str, model_alias: str | None = None) -> StoredLLMFixture | None:
        if model_alias is not None:
            exact = self._by_key.get((brief_id, model_alias))
            if exact is not None:
                return exact
        brief_fixtures = self._by_brief.get(brief_id, [])
        return brief_fixtures[0] if brief_fixtures else None

    def resolve_or_synthesize(
        self,
        *,
        brief: AppBrief,
        model_alias: str,
        model_name: str,
    ) -> ResolvedSimulationIntent:
        fixture = self.get(brief_id=brief.id, model_alias=model_alias)
        if fixture is not None:
            return ResolvedSimulationIntent(
                brief_id=brief.id,
                model_alias=model_alias,
                model_name=model_name,
                source="stored",
                fixture=fixture,
            )

        synthetic_fixture = build_synthetic_fixture(
            brief,
            model_alias=model_alias,
            model_name=model_name,
        )
        return ResolvedSimulationIntent(
            brief_id=brief.id,
            model_alias=model_alias,
            model_name=model_name,
            source="synthetic",
            fixture=synthetic_fixture,
        )


def load_fixture_index() -> FixtureIndex:
    return FixtureIndex([read_fixture(path) for path in iter_fixture_paths()])
