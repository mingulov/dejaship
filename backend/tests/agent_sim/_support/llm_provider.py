from __future__ import annotations

import importlib
import json
from typing import Any

from tests.agent_sim._support.types import AgentSimLLMSettings, GeneratedIntentDraft, ModelEntry


class LLMProviderError(RuntimeError):
    pass


def _load_instructor_dependencies() -> tuple[Any, Any]:
    try:
        instructor = importlib.import_module("instructor")
        openai = importlib.import_module("openai")
    except ImportError as exc:
        raise LLMProviderError(
            "live fixture generation requires 'instructor' and 'openai'. "
            "Install backend dev dependencies before using the live generator."
        ) from exc
    return instructor, openai


def _extract_message_text(response_json: dict[str, Any]) -> str:
    try:
        content = response_json["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMProviderError("provider response missing choices[0].message.content") from exc

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") in {"text", "output_text"}
        ]
        if text_parts:
            return "\n".join(part for part in text_parts if part)

    raise LLMProviderError("unable to extract text content from provider response")


def _parse_json_payload(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise LLMProviderError("provider response did not contain a JSON object")
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMProviderError("provider response contained invalid JSON") from exc


class OpenAICompatibleProvider:
    def __init__(self, settings: AgentSimLLMSettings, *, timeout_s: float = 60.0):
        if not settings.is_configured():
            raise LLMProviderError("live LLM settings are not configured")
        self._settings = settings
        self._timeout_s = timeout_s
        self._raw_client, self._tool_client, self._hooks = self._build_client()

    def _build_client(self) -> tuple[Any, Any, Any]:
        instructor, openai = _load_instructor_dependencies()
        base_client = openai.AsyncOpenAI(
            api_key=self._settings.api_key,
            base_url=self._settings.base_url,
            timeout=self._timeout_s,
        )
        hooks = instructor.hooks.Hooks()
        patched = instructor.patch(base_client, mode=instructor.Mode.TOOLS)
        return base_client, patched, hooks

    @staticmethod
    def _serialize_completion(completion: Any) -> dict[str, Any]:
        if hasattr(completion, "model_dump"):
            return completion.model_dump(mode="json")
        if isinstance(completion, dict):
            return completion
        raise LLMProviderError("unable to serialize raw provider completion")

    @staticmethod
    def _build_messages(*, prompt_text: str, supports_system_role: bool) -> list[dict[str, str]]:
        system_text = "Return strict JSON only. Do not wrap the answer in markdown fences."
        if supports_system_role:
            return [
                {"role": "system", "content": system_text},
                {"role": "user", "content": prompt_text},
            ]
        return [
            {
                "role": "user",
                "content": f"{system_text}\n\n{prompt_text}",
            }
        ]

    async def _generate_with_tools(
        self,
        *,
        model_name: str,
        prompt_text: str,
        supports_system_role: bool,
    ) -> tuple[GeneratedIntentDraft, dict[str, Any], str]:
        raw_completion: Any | None = None

        def capture_completion(response: Any) -> None:
            nonlocal raw_completion
            raw_completion = response

        self._hooks.clear()
        self._hooks.on("completion:response", capture_completion)

        draft = await self._tool_client.chat.completions.create(
            model=model_name,
            temperature=0.2,
            max_retries=2,
            response_model=GeneratedIntentDraft,
            hooks=self._hooks,
            messages=self._build_messages(
                prompt_text=prompt_text,
                supports_system_role=supports_system_role,
            ),
        )
        if raw_completion is None:
            raise LLMProviderError("provider did not emit a raw completion response")
        response_json = self._serialize_completion(raw_completion)
        try:
            response_text = _extract_message_text(response_json)
        except LLMProviderError:
            response_text = draft.model_dump_json()
        if not response_text.strip():
            response_text = draft.model_dump_json()
        return draft, response_json, response_text

    async def _generate_with_json_text(
        self,
        *,
        model_name: str,
        prompt_text: str,
        supports_system_role: bool,
    ) -> tuple[GeneratedIntentDraft, dict[str, Any], str]:
        completion = await self._raw_client.chat.completions.create(
            model=model_name,
            temperature=0.2,
            messages=self._build_messages(
                prompt_text=prompt_text,
                supports_system_role=supports_system_role,
            ),
        )
        response_json = self._serialize_completion(completion)
        response_text = _extract_message_text(response_json)
        parsed = _parse_json_payload(response_text)
        draft = GeneratedIntentDraft.model_validate(parsed)
        return draft, response_json, response_text

    async def generate_intent_draft(
        self,
        *,
        model_entry: ModelEntry,
        prompt_text: str,
    ) -> tuple[GeneratedIntentDraft, dict[str, Any], str]:
        if model_entry.generation_mode == "json_text":
            return await self._generate_with_json_text(
                model_name=model_entry.model,
                prompt_text=prompt_text,
                supports_system_role=model_entry.supports_system_role,
            )
        return await self._generate_with_tools(
            model_name=model_entry.model,
            prompt_text=prompt_text,
            supports_system_role=model_entry.supports_system_role,
        )
