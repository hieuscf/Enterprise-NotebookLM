# =============================================================================
# File: test_openai_chat.py
# Module/Service: Chat Service — OpenAI adapter
# Layer: Adapter
# Purpose: Unit tests for OpenAI structured chat + provider resolution.
# Responsibilities:
#   - max_completion_tokens for gpt-5; Chat Completions JSON parse
#   - resolve_chat_llm provider selection
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

from app.adapters.chat_llm import resolve_chat_llm
from app.adapters.openai_chat import _build_body, extract_structured_json
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
