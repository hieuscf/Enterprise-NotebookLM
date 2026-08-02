# =============================================================================
# File: __init__.py
# Module/Service: Query Router — Handlers (FR11)
# Layer: Service
# Purpose: Export MetadataHandler and FactoidHandler.
# Responsibilities:
#   - Package re-exports for DI / orchestrator
# Dependencies:
#   - handlers.metadata_handler, handlers.factoid_handler
# Public Exports:
#   - MetadataHandler, FactoidHandler
# Database/Table: N/A
# Related Modules: orchestrator
# Important Notes: Both handlers guarantee 0 LLM calls.
# =============================================================================

from app.services.query_router.handlers.factoid_handler import FactoidHandler
from app.services.query_router.handlers.metadata_handler import MetadataHandler

__all__ = ["FactoidHandler", "MetadataHandler"]
