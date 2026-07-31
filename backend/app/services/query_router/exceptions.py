# =============================================================================
# File: exceptions.py
# Module/Service: Query Router (FR11)
# Layer: Service
# Purpose: Query Router domain exceptions.
# Responsibilities:
#   - Signal router-internal failures (not HTTP mapping)
# Dependencies:
#   - N/A
# Public Exports:
#   - QueryRouterError
# Database/Table: N/A
# Related Modules: app.services.query_router.router
# Important Notes: Part 3 does not expose HTTP endpoints yet.
# =============================================================================

from __future__ import annotations


class QueryRouterError(Exception):
    """Raised when Query Router cannot complete cache/classify safely."""

    def __init__(self, message: str, *, code: str = "query_router_error") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# Re-export repository persistence error for service-layer callers.
from app.repositories.query_cache import QueryCacheRepositoryError as QueryCacheRepositoryError  # noqa: E402

__all__ = ["QueryRouterError", "QueryCacheRepositoryError"]
