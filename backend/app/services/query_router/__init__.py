# =============================================================================
# File: __init__.py
# Module/Service: Query Router (FR11)
# Layer: Service
# Purpose: Package exports for Query Router cache + classification.
# Responsibilities:
#   - Expose QueryRouter and RouteDecision as the public API
# Dependencies:
#   - app.services.query_router.router, schemas
# Public Exports:
#   - QueryRouter, RouteDecision, CacheEntryView, QueryRouterError
# Database/Table: N/A
# Related Modules: Chat Service (Part 4), Hybrid Retrieval
# Important Notes: 0 LLM. Does not answer — only routes.
# =============================================================================

from app.services.query_router.exceptions import QueryRouterError
from app.services.query_router.router import QueryRouter
from app.services.query_router.schemas import CacheEntryView, RouteDecision

__all__ = [
    "CacheEntryView",
    "QueryRouter",
    "QueryRouterError",
    "RouteDecision",
]
