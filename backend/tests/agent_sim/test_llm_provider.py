import types
import json

import pytest

from tests.agent_sim._support.llm_provider import (
    LLMProviderError,
    _extract_message_text,
    _load_instructor_dependencies,
    _parse_json_payload,
    OpenAICompatibleProvider,
)
from tests.agent_sim._support.types import AgentSimLLMSettings, GeneratedIntentDraft


pytestmark = pytest.mark.agent_sim


def test_extract_message_text_supports_string_content():
    response = {"choices": [{"message": {"content": "{\"core_mechanic\":\"x\",\"keywords\":[\"a\"]}"}}]}
    assert _extract_message_text(response).startswith("{")


def test_extract_message_text_supports_list_content():
    response = {
        "choices": [
            {
                "message": {
                    "content": [
                        {"type": "text", "text": "{\"core_mechanic\":\"x\",\"keywords\":[\"a\"]}"},
                    ]
                }
            }
        ]
    }
    assert _extract_message_text(response).startswith("{")


def test_parse_json_payload_extracts_embedded_json():
    text = "Here is the result:\n{\"core_mechanic\":\"x\",\"keywords\":[\"a\"]}"
    parsed = _parse_json_payload(text)
    assert parsed["core_mechanic"] == "x"


def test_parse_json_payload_raises_for_missing_json():
    with pytest.raises(LLMProviderError):
        _parse_json_payload("plain text only")


def test_load_instructor_dependencies_raises_when_missing(monkeypatch):
    def fake_import_module(name):
        raise ImportError(name)

    monkeypatch.setattr("tests.agent_sim._support.llm_provider.importlib.import_module", fake_import_module)

    with pytest.raises(LLMProviderError):
        _load_instructor_dependencies()


def test_provider_serialize_completion_uses_model_dump():
    completion = types.SimpleNamespace(model_dump=lambda mode="json": {"id": "abc"})

    serialized = OpenAICompatibleProvider._serialize_completion(completion)

    assert serialized == {"id": "abc"}


def test_provider_init_builds_client_with_instructor(monkeypatch):
    captured = {}

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            captured["openai_kwargs"] = kwargs

    class FakeInstructorModule:
        class Mode:
            TOOLS = "tools"

        class hooks:
            class Hooks:
                def clear(self):
                    return None

                def on(self, *_args, **_kwargs):
                    return None

        @staticmethod
        def patch(client, mode):
            captured["patched_client"] = client
            captured["mode"] = mode
            return "patched"

    def fake_load():
        return FakeInstructorModule, types.SimpleNamespace(AsyncOpenAI=FakeAsyncOpenAI)

    monkeypatch.setattr(
        "tests.agent_sim._support.llm_provider._load_instructor_dependencies",
        fake_load,
    )

    provider = OpenAICompatibleProvider(
        AgentSimLLMSettings(
            provider="openai",
            base_url="https://example.test/v1",
            api_key="secret",
            default_model="test-model",
        )
    )

    assert provider._tool_client == "patched"
    assert provider._raw_client is captured["patched_client"]
    assert captured["mode"] == "tools"
    assert captured["openai_kwargs"]["base_url"] == "https://example.test/v1"
    assert provider._hooks is not None


@pytest.mark.asyncio
async def test_generate_intent_draft_falls_back_to_typed_json_when_raw_text_empty(monkeypatch):
    class FakeHooks:
        def __init__(self):
            self._handler = None

        def clear(self):
            self._handler = None

        def on(self, _event_name, handler):
            self._handler = handler

        def emit(self, payload):
            if self._handler is not None:
                self._handler(payload)

    class FakeCreate:
        def __init__(self, hooks):
            self._hooks = hooks

        async def __call__(self, **_kwargs):
            self._hooks.emit({"choices": [{"message": {"content": ""}}]})
            return GeneratedIntentDraft(core_mechanic="typed mechanic", keywords=["alpha", "bravo"])

    fake_hooks = FakeHooks()
    fake_tool_client = types.SimpleNamespace(
        chat=types.SimpleNamespace(
            completions=types.SimpleNamespace(create=FakeCreate(fake_hooks))
        )
    )

    monkeypatch.setattr(
        OpenAICompatibleProvider,
        "_build_client",
        lambda self: (types.SimpleNamespace(), fake_tool_client, fake_hooks),
    )

    provider = OpenAICompatibleProvider(
        AgentSimLLMSettings(
            provider="openai",
            base_url="https://example.test/v1",
            api_key="secret",
            default_model="test-model",
        )
    )

    draft, raw_response, response_text = await provider.generate_intent_draft(
        model_entry=types.SimpleNamespace(
            model="test-model",
            generation_mode="tools",
            supports_system_role=True,
        ),
        prompt_text="prompt",
    )

    assert draft.core_mechanic == "typed mechanic"
    assert raw_response["choices"][0]["message"]["content"] == ""
    assert json.loads(response_text)["core_mechanic"] == "typed mechanic"


@pytest.mark.asyncio
async def test_generate_intent_draft_json_text_mode_parses_response(monkeypatch):
    class FakeCreate:
        async def __call__(self, **_kwargs):
            return {
                "choices": [
                    {
                        "message": {
                            "content": '```json\n{"core_mechanic":"text mode","keywords":["alpha","bravo"]}\n```'
                        }
                    }
                ]
            }

    fake_raw_client = types.SimpleNamespace(
        chat=types.SimpleNamespace(
            completions=types.SimpleNamespace(create=FakeCreate())
        )
    )

    monkeypatch.setattr(
        OpenAICompatibleProvider,
        "_build_client",
        lambda self: (fake_raw_client, types.SimpleNamespace(), types.SimpleNamespace()),
    )

    provider = OpenAICompatibleProvider(
        AgentSimLLMSettings(
            provider="openai",
            base_url="https://example.test/v1",
            api_key="secret",
            default_model="test-model",
        )
    )

    draft, raw_response, response_text = await provider.generate_intent_draft(
        model_entry=types.SimpleNamespace(
            model="test-model",
            generation_mode="json_text",
            supports_system_role=False,
        ),
        prompt_text="prompt",
    )

    assert draft.core_mechanic == "text mode"
    assert raw_response["choices"][0]["message"]["content"].startswith("```json")
    assert response_text.startswith("```json")
