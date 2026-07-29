# =============================================================================
# File: llamaparse.py
# Module/Service: Pipeline Worker — Document Understanding ([AI])
# Layer: Adapter
# Purpose: Backward-compatible re-export of the LlamaParse client module.
# Responsibilities:
#   - Preserve existing import paths under app.adapters.llamaparse
# Dependencies:
#   - app.clients.llamaparse_client
# Public Exports:
#   - Same symbols as app.clients.llamaparse_client
# Database/Table: N/A
# Related Modules: app.clients.llamaparse_client, app.services.document_understanding
# Important Notes: Implementation lives in app.clients.llamaparse_client.
# =============================================================================

from app.clients.llamaparse_client import (
    CONTENT_TYPES,
    FILES_ENDPOINT,
    LLAMAPARSE_CB_OPEN_MESSAGE,
    PARSE_ENDPOINT,
    LlamaParseCircuitOpenError,
    LlamaParseClient,
    LlamaParseError,
    LlamaParseRequestError,
    LlamaParseResult,
    LlamaParseServiceError,
    LlamaParseTimeoutError,
    build_llamaparse_circuit_breaker,
    get_llamaparse_circuit_breaker_metrics,
    get_llamaparse_client,
)

__all__ = [
    "CONTENT_TYPES",
    "FILES_ENDPOINT",
    "LLAMAPARSE_CB_OPEN_MESSAGE",
    "PARSE_ENDPOINT",
    "LlamaParseCircuitOpenError",
    "LlamaParseClient",
    "LlamaParseError",
    "LlamaParseRequestError",
    "LlamaParseResult",
    "LlamaParseServiceError",
    "LlamaParseTimeoutError",
    "build_llamaparse_circuit_breaker",
    "get_llamaparse_circuit_breaker_metrics",
    "get_llamaparse_client",
]
