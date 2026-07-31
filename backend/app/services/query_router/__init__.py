# =============================================================================
# File: __init__.py
# Module/Service: Query Router (FR11) + Execution (Part 4)
# Layer: Service
# Purpose: Package exports for Query Router classification and orchestration.
# Responsibilities:
#   - Expose QueryRouter, QueryOrchestrator, and shared schemas
# Dependencies:
#   - app.services.query_router.router, orchestrator, schemas
# Public Exports:
#   - QueryRouter, QueryOrchestrator, RouteDecision, QueryExecutionResult, …
# Database/Table: N/A
# Related Modules: Chat Service, Hybrid Retrieval
# Important Notes: Chat must call handle_query via QueryOrchestrator only.
# =============================================================================

from app.services.query_router.cache_writer import QueryCacheWriter, write_cache
from app.services.query_router.exceptions import QueryCacheRepositoryError, QueryRouterError
from app.services.query_router.orchestrator import COMPLEX_STATUS, QueryOrchestrator
from app.services.query_router.router import QueryRouter
from app.services.query_router.schemas import (
    CacheEntryView,
    CitationRef,
    QueryExecutionResult,
    RouteDecision,
)

__all__ = [
    "COMPLEX_STATUS",
    "CacheEntryView",
    "CitationRef",
    "QueryCacheRepositoryError",
    "QueryCacheWriter",
    "QueryExecutionResult",
    "QueryOrchestrator",
    "QueryRouter",
    "QueryRouterError",
    "RouteDecision",
    "write_cache",
]
