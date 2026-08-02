# =============================================================================
# File: query_log_repository.py
# Module/Service: Query Router — Unified Routing Logging (FR11)
# Layer: Adapter (Protocol)
# Purpose: QueryLogRepository Protocol — persist one query_logs row.
# Responsibilities:
#   - Define create_log(...) without leaking ORM into the logging service
# Dependencies:
#   - N/A (Protocol only)
# Public Exports:
#   - QueryLogRepository
# Database/Table: query_logs
# Related Modules: logging_service, repositories.query_logs
# Important Notes: Schema is fixed — no extra columns.
# =============================================================================

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from app.models.enums import RouteType
from app.models.query import QueryLog


@runtime_checkable
class QueryLogRepository(Protocol):
    """Write-side access for ``query_logs`` (exactly one row per routed query)."""

    async def create_log(
        self,
        *,
        workspace_id: UUID,
        user_id: UUID,
        query_text: str,
        route_type: RouteType,
        message_id: UUID | None,
        cache_id: UUID | None,
        llm_calls_count: int,
        model_used: str | None,
        latency_ms: int | None,
    ) -> QueryLog:
        """Insert one ``query_logs`` row and return the persisted entity."""
        ...
