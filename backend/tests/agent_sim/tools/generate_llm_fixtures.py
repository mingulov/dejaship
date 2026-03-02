from __future__ import annotations

import argparse
import asyncio

from dejaship.schemas import IntentInput
from tests.agent_sim._support.catalog import (
    load_app_catalog,
    load_model_matrix,
    load_prompt_text,
    resolve_model_set,
)
from tests.agent_sim._support.config import load_agent_sim_llm_settings
from tests.agent_sim._support.fixture_store import (
    build_prompt_hash,
    hash_app_brief,
    write_fixture,
)
from tests.agent_sim._support.keyword_builder import build_keyword_result
from tests.agent_sim._support.llm_provider import OpenAICompatibleProvider
from tests.agent_sim._support.prompting import render_intent_prompt
from tests.agent_sim._support.types import StoredFixtureMetadata, StoredLLMFixture


PROMPT_NAME = "intent-from-brief"
PROMPT_FILE_STEM = "intent_from_brief"
PROMPT_VERSION = "v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate stored LLM fixtures for agent simulation.")
    parser.add_argument("--brief-id", action="append", dest="brief_ids", help="Only generate for specific brief ids.")
    parser.add_argument("--model-alias", action="append", dest="model_aliases", help="Only generate for specific model aliases.")
    parser.add_argument("--model-set", help="Override the default model set.")
    parser.add_argument("--limit", type=int, default=None, help="Stop after N generated fixtures.")
    parser.add_argument("--dry-run", action="store_true", help="Generate and validate in memory without writing files.")
    parser.add_argument("--output-version", default="v1", help="Fixture output version directory.")
    return parser.parse_args()
def select_briefs(catalog, brief_ids: list[str] | None):
    if not brief_ids:
        return catalog.briefs
    wanted = set(brief_ids)
    selected = [brief for brief in catalog.briefs if brief.id in wanted]
    missing = sorted(wanted - {brief.id for brief in selected})
    if missing:
        raise ValueError(f"unknown brief ids: {missing}")
    return selected


def select_models(model_matrix, model_set: str, model_aliases: list[str] | None):
    models = resolve_model_set(model_matrix, model_set)
    if not model_aliases:
        return models
    wanted = set(model_aliases)
    selected = [(alias, model) for alias, model in models if alias in wanted]
    missing = sorted(wanted - {alias for alias, _ in selected})
    if missing:
        raise ValueError(f"unknown or disabled model aliases in selected set: {missing}")
    return selected


async def main() -> None:
    args = parse_args()
    settings = load_agent_sim_llm_settings()
    if not settings.is_configured():
        raise RuntimeError("agent simulation live LLM settings are not configured")

    catalog = load_app_catalog()
    model_matrix = load_model_matrix()
    prompt_template = load_prompt_text(f"{PROMPT_FILE_STEM}_{PROMPT_VERSION}")

    selected_briefs = select_briefs(catalog, args.brief_ids)
    selected_models = select_models(
        model_matrix,
        args.model_set or settings.model_set,
        args.model_aliases,
    )

    provider = OpenAICompatibleProvider(settings)
    generated_count = 0

    for model_alias, model_entry in selected_models:
        for brief in selected_briefs:
            raw_prompt = render_intent_prompt(prompt_template, brief)
            llm_output, raw_response, response_text = await provider.generate_intent_draft(
                model_name=model_entry.model,
                prompt_text=raw_prompt,
            )
            keyword_result = build_keyword_result(brief, llm_output.keywords)
            final_intent = IntentInput(
                core_mechanic=llm_output.core_mechanic,
                keywords=keyword_result.final_keywords,
            )
            fixture = StoredLLMFixture(
                brief_id=brief.id,
                metadata=StoredFixtureMetadata(
                    provider=settings.provider,
                    model_alias=model_alias,
                    model_name=model_entry.model,
                    prompt_name=PROMPT_NAME,
                    prompt_version=PROMPT_VERSION,
                    brief_hash=hash_app_brief(brief),
                    prompt_hash=build_prompt_hash(
                        brief,
                        prompt_name=PROMPT_FILE_STEM,
                        prompt_version=PROMPT_VERSION,
                    )[1],
                ),
                raw_prompt=raw_prompt,
                raw_response=raw_response,
                response_text=response_text,
                llm_output=llm_output,
                keyword_result=keyword_result,
                final_intent_input=final_intent,
            )
            if args.dry_run:
                print(
                    f"[dry-run] {model_alias} {brief.id} -> "
                    f"{fixture.final_intent_input.core_mechanic} | {fixture.final_intent_input.keywords}"
                )
            else:
                path = write_fixture(fixture, version=args.output_version)
                print(f"wrote {path}")

            generated_count += 1
            if args.limit is not None and generated_count >= args.limit:
                print(f"stopped after {generated_count} fixture(s)")
                return

    print(f"generated {generated_count} fixture(s)")


if __name__ == "__main__":
    asyncio.run(main())
