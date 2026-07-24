# =============================================================================
# File: __init__.py
# Module/Service: Core
# Layer: Adapter
# Purpose: Package exports for config, logging, middleware, and tracing.
# Responsibilities:
#   - Re-export common observability hooks for services
# Dependencies:
#   - app.core.config, logging, middleware, tracing
# Public Exports:
#   - get_settings, get_logger, bind_log_context, get_tracer
# Database/Table: N/A
# Related Modules: app.main, app.services (later phases)
# Important Notes: Phase 1.1 FR13 foundation hooks.
# =============================================================================

from app.core.config import Settings, get_settings
from app.core.logging import bind_log_context, clear_log_context, get_logger
from app.core.tracing import get_tracer

__all__ = [
    "Settings",
    "get_settings",
    "get_logger",
    "bind_log_context",
    "clear_log_context",
    "get_tracer",
]
