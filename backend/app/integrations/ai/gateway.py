# =============================================================================
# File: gateway.py
# Module/Service: AI Integration Gateway
# Layer: Adapter
# Purpose: Protocol + factory — the only entry business services use for AI.
# Responsibilities:
#   - Expose generate / embed / require_enabled
#   - Return Disabled gateway when AI_ENABLED=false without importing providers
# Dependencies:
#   - app.core.config, app.integrations.ai.disabled
# Public Exports:
#   - AIGateway, get_ai_gateway
# Database/Table: N/A
# Related Modules: live.py, disabled.py
# Important Notes: Live provider modules are imported only when AI is enabled.
# =============================================================================

from __future__ import annotations

from typing import Any, Protocol

from app.core.config import Settings, get_settings
from app.integrations.ai.exceptions import (
    AI_DISABLED,
    AIGatewayError,
)


class AIGateway(Protocol):
    """Port implemented by DisabledAIGateway and LiveAIGateway."""

    def is_enabled(self) -> bool: ...

    def require_enabled(self, *, capability: str = "AI") -> None: ...

    def generate(self, **kwargs: Any) -> Any: ...

    async def generate_async(self, **kwargs: Any) -> Any: ...

    def embed(self, texts: list[str], **kwargs: Any) -> Any: ...


def get_ai_gateway(settings: Settings | None = None) -> AIGateway:
    """Return the active gateway. Never initializes providers when AI is off."""
    cfg = settings or get_settings()
    if not cfg.ai_enabled:
        from app.integrations.ai.disabled import DisabledAIGateway

        return DisabledAIGateway()
    from app.integrations.ai.live import LiveAIGateway

    return LiveAIGateway(cfg)


def raise_ai_disabled(*, capability: str = "AI") -> None:
    raise AIGatewayError(
        AI_DISABLED,
        f"{capability} is disabled (AI_ENABLED=false)",
        status_code=503,
    )
