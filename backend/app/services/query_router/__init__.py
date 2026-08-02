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
from app.services.query_router.classifier import (
    QueryClassifier,
    RuleBasedClassifier,
    build_rule_based_classifier,
)
from app.services.query_router.exceptions import QueryCacheRepositoryError, QueryRouterError
from app.services.query_router.handlers import FactoidHandler, MetadataHandler
from app.services.query_router.orchestrator import COMPLEX_STATUS, QueryOrchestrator
from app.services.query_router.response_models import QueryRouterResult
from app.services.query_router.router import QueryRouter
from app.services.query_router.schemas import (
    CacheEntryView,
    CitationRef,
    QueryExecutionResult,
    RouteDecision,
)

# Re-export cache helpers for Task-2 call sites.
from app.services.query_router.cache import (  # noqa: E402
    QueryCacheService,
    build_normalized_query,
    hash_query,
    normalize_query,
    save_query_cache,
)

__all__ = [
    "COMPLEX_STATUS",
    "CacheEntryView",
    "CitationRef",
    "FactoidHandler",
    "MetadataHandler",
    "QueryCacheRepositoryError",
    "QueryCacheService",
    "QueryCacheWriter",
    "QueryClassifier",
    "QueryExecutionResult",
    "QueryOrchestrator",
    "QueryRouter",
    "QueryRouterError",
    "QueryRouterResult",
    "RuleBasedClassifier",
    "RouteDecision",
    "build_normalized_query",
    "build_rule_based_classifier",
    "hash_query",
    "normalize_query",
    "save_query_cache",
    "write_cache",
]
