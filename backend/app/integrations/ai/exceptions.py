# =============================================================================
# File: exceptions.py
# Module/Service: AI Integration Gateway
# Layer: Domain
# Purpose: Stable business error codes when AI is off or a capability is missing.
# Responsibilities:
#   - Raise typed errors instead of crashing the process
# Dependencies:
#   - None
# Public Exports:
#   - AIGatewayError, AI_DISABLED, AI_CAPABILITY_UNAVAILABLE, DOCUMENT_NOT_ANALYZED
# Database/Table: N/A
# Related Modules: app.integrations.ai.gateway
# Important Notes: Codes are API contract — do not rename without frontend update.
# =============================================================================

from __future__ import annotations

AI_DISABLED = "AI_DISABLED"
AI_CAPABILITY_UNAVAILABLE = "AI_CAPABILITY_UNAVAILABLE"
DOCUMENT_NOT_ANALYZED = "DOCUMENT_NOT_ANALYZED"


class AIGatewayError(Exception):
    """Capability error mapped to HTTP by presentation / application services."""

    def __init__(self, code: str, message: str, *, status_code: int = 503) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)
