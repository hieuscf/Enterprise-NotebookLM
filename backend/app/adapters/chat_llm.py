# =============================================================================
# File: chat_llm.py
# Module/Service: Chat Service (FR4)
# Layer: Adapter
# Purpose: Resolve chat LLM provider from Settings and dispatch structured calls.
# Responsibilities:
#   - Select anthropic | openai (gemini reserved) via CHAT_LLM_PROVIDER
#   - Expose api_key / api_base / sync+async extract helpers for chat paths
# Dependencies:
#   - Settings, anthropic_client, openai_chat, llm_result
# Public Exports:
#   - ChatLlmConfig, resolve_chat_llm, extract_structured_json,
#     extract_structured_json_async
# Database/Table: N/A
# Related Modules: answer_generator, rewrite_agent, model_tiering
# Important Notes:
#   - Graph extraction stays on Anthropic (GRAPH_LLM_*); this module is chat-only.
#   - Embedding stays on EMBEDDING_PROVIDER (OpenAI embeddings when configured).
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.adapters import anthropic_client, openai_chat
from app.adapters.llm_result import StructuredLlmResult
from app.core.config import Settings

ChatLlmProvider = Literal["anthropic", "openai", "gemini"]


@dataclass(frozen=True, slots=True)
class ChatLlmConfig:
    """Resolved credentials + endpoint for the active chat provider."""

    provider: ChatLlmProvider
    api_key: str
    api_base: str


def resolve_chat_llm(settings: Settings) -> ChatLlmConfig | None:
    """Return provider config when API key is present; else None."""
    provider = _normalize_provider(settings.chat_llm_provider)
    if provider == "openai":
        api_key = (settings.openai_api_key or "").strip()
        if not api_key:
            return None
        return ChatLlmConfig(
            provider="openai",
            api_key=api_key,
            api_base=(settings.openai_api_base or "https://api.openai.com/v1").rstrip(
                "/"
            ),
        )
    if provider == "gemini":
        # Placeholder until Gemini adapter ships — treat as unconfigured.
        return None
    api_key = (settings.anthropic_api_key or "").strip()
    if not api_key:
        return None
    return ChatLlmConfig(
        provider="anthropic",
        api_key=api_key,
        api_base=(settings.anthropic_api_base or "https://api.anthropic.com").rstrip(
            "/"
        ),
    )


def extract_structured_json(
    *,
    settings: Settings,
    system: str,
    user: str,
    model: str,
    max_tokens: int = 4096,
    timeout_seconds: float = 120.0,
    temperature: float = 0.0,
    top_p: float = 1.0,
    cost_estimator: Any | None = None,
) -> StructuredLlmResult:
    """Sync structured JSON call via the configured chat provider."""
    cfg = resolve_chat_llm(settings)
    if cfg is None:
        raise ValueError("chat_llm_not_configured")
    if cfg.provider == "openai":
        return openai_chat.extract_structured_json(
            system=system,
            user=user,
            model=model,
            api_key=cfg.api_key,
            api_base=cfg.api_base,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
            temperature=temperature,
            top_p=top_p,
            cost_estimator=cost_estimator,
        )
    return anthropic_client.extract_structured_json(
        system=system,
        user=user,
        model=model,
        api_key=cfg.api_key,
        api_base=cfg.api_base,
        max_tokens=max_tokens,
        timeout_seconds=timeout_seconds,
    )


async def extract_structured_json_async(
    *,
    settings: Settings,
    system: str,
    user: str,
    model: str,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    top_p: float = 1.0,
    timeout_seconds: float = 120.0,
    cost_estimator: Any | None = None,
) -> StructuredLlmResult:
    """Async structured JSON call via the configured chat provider."""
    cfg = resolve_chat_llm(settings)
    if cfg is None:
        raise ValueError("chat_llm_not_configured")
    if cfg.provider == "openai":
        return await openai_chat.extract_structured_json_async(
            system=system,
            user=user,
            model=model,
            api_key=cfg.api_key,
            api_base=cfg.api_base,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            timeout_seconds=timeout_seconds,
            cost_estimator=cost_estimator,
        )
    return await anthropic_client.extract_structured_json_async(
        system=system,
        user=user,
        model=model,
        api_key=cfg.api_key,
        api_base=cfg.api_base,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        timeout_seconds=timeout_seconds,
        cost_estimator=cost_estimator,
    )


def _normalize_provider(raw: str | None) -> ChatLlmProvider:
    value = (raw or "anthropic").strip().lower()
    if value in {"openai", "gpt", "gpt-5", "chatgpt"}:
        return "openai"
    if value in {"gemini", "google"}:
        return "gemini"
    return "anthropic"
