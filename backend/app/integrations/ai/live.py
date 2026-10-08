# =============================================================================
# File: live.py
# Module/Service: AI Integration Gateway
# Layer: Adapter
# Purpose: Live AI Gateway that delegates to existing httpx adapters.
# Responsibilities:
#   - generate / generate_async → chat_llm
#   - embed → app.ai.embedding
# Dependencies:
#   - app.adapters.chat_llm, app.ai.embedding, Settings
# Public Exports:
#   - LiveAIGateway
# Database/Table: N/A
# Related Modules: gateway.py
# Important Notes: Imported only when AI_ENABLED=true.
# =============================================================================

from __future__ import annotations

from typing import Any

from app.adapters.chat_llm import extract_structured_json, extract_structured_json_async
from app.ai.embedding import embed_texts_batch
from app.core.config import Settings
from app.integrations.ai.exceptions import AI_CAPABILITY_UNAVAILABLE, AIGatewayError


class LiveAIGateway:
    """Provider-backed gateway. Business layer still must not import SDKs."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def is_enabled(self) -> bool:
        return True

    def require_enabled(self, *, capability: str = "AI") -> None:
        del capability

    def generate(self, **kwargs: Any) -> Any:
        kwargs.setdefault("settings", self._settings)
        try:
            return extract_structured_json(**kwargs)
        except ValueError as exc:
            raise AIGatewayError(
                AI_CAPABILITY_UNAVAILABLE,
                str(exc) or "Chat LLM provider is not configured",
                status_code=503,
            ) from exc

    async def generate_async(self, **kwargs: Any) -> Any:
        kwargs.setdefault("settings", self._settings)
        try:
            return await extract_structured_json_async(**kwargs)
        except ValueError as exc:
            raise AIGatewayError(
                AI_CAPABILITY_UNAVAILABLE,
                str(exc) or "Chat LLM provider is not configured",
                status_code=503,
            ) from exc

    def embed(self, texts: list[str], **kwargs: Any) -> Any:
        s = self._settings
        return embed_texts_batch(
            texts,
            model_name=kwargs.get("model_name", s.embedding_model_name),
            dimension=int(kwargs.get("dimension", s.embedding_dimension)),
            provider=kwargs.get("provider", s.embedding_provider),
            api_key=kwargs.get("api_key", s.embedding_api_key),
            batch_size=int(kwargs.get("batch_size", s.embedding_batch_size)),
        )
