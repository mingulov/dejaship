from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict

from openai import APIConnectionError, APITimeoutError, RateLimitError

from dejaship.schemas import IntentInput
from tests.agent_sim._support.catalog import (
    load_app_catalog,
    load_model_matrix,
    load_prompt_text,
    resolve_enabled_model_aliases,
    resolve_model_set,
)
from tests.agent_sim._support.config import load_agent_sim_llm_settings
from tests.agent_sim._support.fixture_store import (
    build_prompt_hash,
    fixture_exists,
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
DEFAULT_MAX_ATTEMPTS = 2
DEFAULT_MODEL_FAILURE_THRESHOLD = 3
RETRYABLE_EXCEPTIONS = (RateLimitError, APITimeoutError, APIConnectionError)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate stored LLM fixtures for agent simulation.")
    parser.add_argument("--brief-id", action="append", dest="brief_ids", help="Only generate for specific brief ids.")
    parser.add_argument("--model-alias", action="append", dest="model_aliases", help="Only generate for specific model aliases.")
    parser.add_argument("--model-set", help="Override the default model set.")
    parser.add_argument("--limit", type=int, default=None, help="Stop after N generated fixtures.")
    parser.add_argument("--dry-run", action="store_true", help="Generate and validate in memory without writing files.")
    parser.add_argument(
        "--timeout-s",
        type=float,
        default=30.0,
        help="Per-request provider timeout in seconds.",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=DEFAULT_MAX_ATTEMPTS,
        help="Maximum attempts per fixture for retryable provider errors.",
    )
    parser.add_argument(
        "--skip-existing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip fixtures that already exist on disk.",
    )
    parser.add_argument(
        "--model-failure-threshold",
        type=int,
        default=DEFAULT_MODEL_FAILURE_THRESHOLD,
        help="Mark a model retry-later after this many failed briefs in the current run.",
    )
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
    if not model_aliases:
        return resolve_model_set(model_matrix, model_set)
    return resolve_enabled_model_aliases(model_matrix, model_aliases)


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

    provider = OpenAICompatibleProvider(settings, timeout_s=args.timeout_s)
    generated_count = 0
    skipped_count = 0
    failure_counts: dict[str, int] = defaultdict(int)
    retry_later_models: dict[str, str] = {}
    failures: list[str] = []

    for model_alias, model_entry in selected_models:
        if model_alias in retry_later_models:
            continue

        for brief in selected_briefs:
            if model_alias in retry_later_models:
                break

            if args.skip_existing and not args.dry_run and fixture_exists(model_alias, brief.id):
                skipped_count += 1
                continue

            raw_prompt = render_intent_prompt(prompt_template, brief)
            llm_output = raw_response = response_text = None
            print(f"generating {model_alias} {brief.id}")
            for attempt in range(1, args.max_attempts + 1):
                try:
                    llm_output, raw_response, response_text = await provider.generate_intent_draft(
                        model_name=model_entry.model,
                        prompt_text=raw_prompt,
                    )
                    break
                except RETRYABLE_EXCEPTIONS as exc:
                    if attempt == args.max_attempts:
                        message = f"failed {model_alias} {brief.id}: {type(exc).__name__}: {exc}"
                        print(message)
                        failures.append(message)
                        failure_counts[model_alias] += 1
                    else:
                        delay_s = min(2**attempt, 20)
                        print(
                            f"retrying {model_alias} {brief.id} after {type(exc).__name__} "
                            f"(attempt {attempt}/{args.max_attempts}, sleep {delay_s}s)"
                        )
                        await asyncio.sleep(delay_s)
                except Exception as exc:
                    message = f"failed {model_alias} {brief.id}: {type(exc).__name__}: {exc}"
                    print(message)
                    failures.append(message)
                    failure_counts[model_alias] += 1
                    break

            if llm_output is None or raw_response is None or response_text is None:
                if (
                    args.model_failure_threshold > 0
                    and failure_counts[model_alias] >= args.model_failure_threshold
                ):
                    reason = (
                        f"marked retry-later after {failure_counts[model_alias]} failed briefs "
                        f"(threshold {args.model_failure_threshold})"
                    )
                    retry_later_models[model_alias] = reason
                    print(f"skipping remaining briefs for {model_alias}: {reason}")
                continue
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
                path = write_fixture(fixture)
                print(f"wrote {path}")

            generated_count += 1
            if args.limit is not None and generated_count >= args.limit:
                print(f"stopped after {generated_count} fixture(s)")
                return

    print(f"generated {generated_count} fixture(s)")
    if skipped_count:
        print(f"skipped existing fixtures: {skipped_count}")
    if failures:
        print(f"failed fixtures: {len(failures)}")
        for model_alias in sorted(failure_counts):
            print(f"  {model_alias}: {failure_counts[model_alias]} failure(s)")
    if retry_later_models:
        print(f"retry-later models: {len(retry_later_models)}")
        for model_alias, reason in sorted(retry_later_models.items()):
            print(f"  {model_alias}: {reason}")


if __name__ == "__main__":
    asyncio.run(main())
