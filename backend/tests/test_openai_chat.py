# =============================================================================
# File: test_openai_chat.py
# Module/Service: Chat Service — OpenAI adapter
# Layer: Adapter
# Purpose: Unit tests for OpenAI structured chat + provider resolution.
# Responsibilities:
#   - max_completion_tokens for gpt-5; Chat Completions JSON parse
#   - resolve_chat_llm provider selection
#   - reasoning_effort wiring + EmptyCompletionError classification (P0 fix:
#     gpt-5 reasoning tokens exhausting the completion budget → empty answer)
# Dependencies:
#   - pytest, httpx mock via respx or monkeypatch
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: openai_chat, chat_llm
# Important Notes: Does not hit live OpenAI.
# =============================================================================

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.adapters.chat_llm import extract_structured_json_async, resolve_chat_llm
from app.adapters.llm_result import EmptyCompletionError
from app.adapters.openai_chat import _build_body, _result_from_response, extract_structured_json
from app.core.config import Settings


def test_build_body_gpt5_uses_max_completion_tokens() -> None:
    body = _build_body(
        system="sys",
        user="user",
        model="gpt-5",
        max_tokens=256,
        temperature=0.0,
        top_p=1.0,
    )
    assert body["max_completion_tokens"] == 256
    assert "max_tokens" not in body
    assert body["response_format"] == {"type": "json_object"}


def test_build_body_gpt4o_uses_max_tokens() -> None:
    body = _build_body(
        system="sys",
        user="user",
        model="gpt-4o-mini",
        max_tokens=128,
        temperature=0.2,
        top_p=0.9,
    )
    assert body["max_tokens"] == 128
    assert body["temperature"] == 0.2
    assert "max_completion_tokens" not in body


def test_resolve_chat_llm_openai() -> None:
    settings = Settings(
        chat_llm_provider="openai",
        openai_api_key="sk-test",
        openai_api_base="https://api.openai.com/v1",
    )
    cfg = resolve_chat_llm(settings)
    assert cfg is not None
    assert cfg.provider == "openai"
    assert cfg.api_key == "sk-test"


def test_resolve_chat_llm_openai_missing_key() -> None:
    settings = Settings(chat_llm_provider="openai", openai_api_key=None)
    assert resolve_chat_llm(settings) is None


def test_build_body_gpt5_includes_reasoning_effort_when_given() -> None:
    body = _build_body(
        system="sys",
        user="user",
        model="gpt-5",
        max_tokens=256,
        temperature=0.0,
        top_p=1.0,
        reasoning_effort="minimal",
    )
    assert body["reasoning_effort"] == "minimal"


def test_build_body_gpt5_omits_reasoning_effort_when_not_given() -> None:
    body = _build_body(
        system="sys",
        user="user",
        model="gpt-5",
        max_tokens=256,
        temperature=0.0,
        top_p=1.0,
    )
    assert "reasoning_effort" not in body


def test_build_body_gpt4o_ignores_reasoning_effort() -> None:
    """Non-reasoning models never send reasoning_effort (unsupported param)."""
    body = _build_body(
        system="sys",
        user="user",
        model="gpt-4o-mini",
        max_tokens=128,
        temperature=0.2,
        top_p=0.9,
        reasoning_effort="minimal",
    )
    assert "reasoning_effort" not in body


def test_result_from_response_raises_empty_completion_error_on_blank_content() -> None:
    """Reproduces the P0 bug: HTTP 200 but message.content is empty because
    gpt-5 spent its entire max_completion_tokens budget on hidden reasoning
    tokens (finish_reason=length). Must be classified, never silently parsed
    into an empty/garbage answer."""
    body = {
        "model": "gpt-5",
        "choices": [
            {
                "finish_reason": "length",
                "message": {"content": ""},
            }
        ],
        "usage": {"prompt_tokens": 120, "completion_tokens": 4096},
    }
    with pytest.raises(EmptyCompletionError) as exc_info:
        _result_from_response(body, model="gpt-5", cost_estimator=None)
    assert exc_info.value.finish_reason == "length"
    assert exc_info.value.model == "gpt-5"
    assert exc_info.value.output_tokens == 4096


def test_result_from_response_captures_finish_reason_on_success() -> None:
    body = {
        "model": "gpt-5",
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"content": '{"answer": "hi", "citation_ids": []}'},
            }
        ],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2},
    }
    result = _result_from_response(body, model="gpt-5", cost_estimator=None)
    assert result.finish_reason == "stop"
    assert result.data["answer"] == "hi"


@pytest.mark.asyncio
async def test_extract_structured_json_async_sends_configured_reasoning_effort() -> None:
    """chat_llm.extract_structured_json_async must forward
    Settings.openai_reasoning_effort into the provider request body — this is
    the actual fix wiring (adapter alone is not enough without this thread)."""
    captured_body: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "model": "gpt-5",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": '{"answer": "ok", "citation_ids": []}'},
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *exc: object) -> bool:
            return False

        async def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]) -> FakeResponse:
            captured_body.update(json)
            return FakeResponse()

    settings = Settings(
        chat_llm_provider="openai",
        openai_api_key="sk-test",
        openai_chat_model="gpt-5",
        openai_reasoning_effort="minimal",
    )
    with patch("app.adapters.openai_chat.httpx.AsyncClient", FakeAsyncClient):
        result = await extract_structured_json_async(
            settings=settings,
            system="s",
            user="u",
            model="gpt-5",
            max_tokens=4096,
        )
    assert captured_body["reasoning_effort"] == "minimal"
    assert captured_body["max_completion_tokens"] == 4096
    assert result.data["answer"] == "ok"


def test_extract_structured_json_parses_openai_response() -> None:
    fake_resp = MagicMock()
    fake_resp.raise_for_status = MagicMock()
    fake_resp.json.return_value = {
        "model": "gpt-5",
        "choices": [
            {
                "message": {
                    "content": '{"answer": "hi", "citation_ids": []}',
                }
            }
        ],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2},
    }
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = False
    fake_client.post.return_value = fake_resp

    with patch("app.adapters.openai_chat.httpx.Client", return_value=fake_client):
        result = extract_structured_json(
            system="s",
            user="u",
            model="gpt-5",
            api_key="sk",
        )
    assert result.data["answer"] == "hi"
    assert result.input_tokens == 3
    assert result.output_tokens == 2
    assert result.model == "gpt-5"
