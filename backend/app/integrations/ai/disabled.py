# =============================================================================
# File: disabled.py
# Module/Service: AI Integration Gateway
# Layer: Adapter
# Purpose: No-op gateway used when AI_ENABLED=false — never loads providers.
# Responsibilities:
#   - Raise AI_DISABLED / AI_CAPABILITY_UNAVAILABLE on generate/embed
# Dependencies:
#   - app.integrations.ai.exceptions
# Public Exports:
#   - DisabledAIGateway
# Database/Table: N/A
# Related Modules: gateway.py
# Important Notes: Must not import chat_llm, embedding, llamaparse, or vendor SDKs.
# =============================================================================

from __future__ import annotations

from typing import Any

from app.integrations.ai.exceptions import (
    AI_CAPABILITY_UNAVAILABLE,
    AI_DISABLED,
    AIGatewayError,
)


class DisabledAIGateway:
    """Gateway that keeps the process up while refusing AI capabilities."""

    def is_enabled(self) -> bool:
        return False

    def require_enabled(self, *, capability: str = "AI") -> None:
        raise AIGatewayError(
            AI_DISABLED,
            f"{capability} is disabled (AI_ENABLED=false)",
            status_code=503,
        )

    def generate(self, **kwargs: Any) -> Any:
        del kwargs
        raise AIGatewayError(
            AI_CAPABILITY_UNAVAILABLE,
            "LLM generation is unavailable because AI is disabled",
            status_code=503,
        )

    async def generate_async(self, **kwargs: Any) -> Any:
        del kwargs
        raise AIGatewayError(
            AI_CAPABILITY_UNAVAILABLE,
            "LLM generation is unavailable because AI is disabled",
            status_code=503,
        )

    def embed(self, texts: list[str], **kwargs: Any) -> Any:
        del texts, kwargs
        raise AIGatewayError(
            AI_CAPABILITY_UNAVAILABLE,
            "Embeddings are unavailable because AI is disabled",
            status_code=503,
        )
