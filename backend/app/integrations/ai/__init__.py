# =============================================================================
# File: __init__.py
# Module/Service: AI Integration Gateway
# Layer: Adapter
# Purpose: Public exports for the sole AI entry point used by business services.
# Responsibilities:
#   - Re-export gateway factory, protocol, and capability errors
# Dependencies:
#   - app.integrations.ai.gateway, exceptions
# Public Exports:
#   - AIGateway, get_ai_gateway, AIGatewayError, AI_DISABLED, AI_CAPABILITY_UNAVAILABLE
# Database/Table: N/A
# Related Modules: REFACTOR_PLAN.md
# Important Notes: Business services must not import provider SDKs.
# =============================================================================

from app.integrations.ai.exceptions import (
    AI_CAPABILITY_UNAVAILABLE,
    AI_DISABLED,
    DOCUMENT_NOT_ANALYZED,
    AIGatewayError,
)
from app.integrations.ai.gateway import AIGateway, get_ai_gateway

__all__ = [
    "AIGateway",
    "AIGatewayError",
    "AI_CAPABILITY_UNAVAILABLE",
    "AI_DISABLED",
    "DOCUMENT_NOT_ANALYZED",
    "get_ai_gateway",
]
