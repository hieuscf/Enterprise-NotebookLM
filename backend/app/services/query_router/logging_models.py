# =============================================================================
# File: logging_models.py
# Module/Service: Query Router — Unified Routing Logging (FR11)
# Layer: Schema
# Purpose: QueryRoutingLogContext — single payload for query_logs persistence.
# Responsibilities:
#   - Carry all fields needed to write one query_logs row
# Dependencies:
#   - pydantic, app.models.enums.RouteType
# Public Exports:
#   - QueryRoutingLogContext, QueryRoutingLogResult
# Database/Table: query_logs (context maps to columns; session_id not persisted)
# Related Modules: logging_service, orchestrator
# Important Notes: Do not add DB columns — session_id is contextual only.
# =============================================================================

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import RouteType


class QueryRoutingLogContext(BaseModel):
    """Immutable context for a single Query Router log write."""

    model_config = ConfigDict(frozen=True)

    workspace_id: UUID
    user_id: UUID
    query_text: str
    route_type: RouteType
    latency_ms: int = Field(ge=0)
    llm_calls_count: int = Field(default=0, ge=0)
    cache_id: UUID | None = None
    message_id: UUID | None = None
    model_used: str | None = None
    # Optional Chat session id for correlation — not a query_logs column.
    session_id: UUID | None = None


class QueryRoutingLogResult(BaseModel):
    """Outcome of ``log_query_routing`` (best-effort)."""

    model_config = ConfigDict(frozen=True)

    query_log_id: UUID | None = None
    persisted: bool = False
    error: str | None = None
