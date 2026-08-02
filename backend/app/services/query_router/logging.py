# =============================================================================
# File: logging.py
# Module/Service: Query Router Execution / Unified Logging (compat facade)
# Layer: Service
# Purpose: Re-export Task-4 logging entry points; thin legacy wrapper.
# Responsibilities:
#   - Expose log_query_routing / QueryRoutingLogContext
#   - log_route_decision → delegates to log_query_routing (query_logs only)
# Dependencies:
#   - logging_service, logging_models, QueryLogRepository
# Public Exports:
#   - log_query_routing, log_route_decision, QueryRoutingLogContext, RouteLogResult
# Database/Table: query_logs
# Related Modules: orchestrator
# Important Notes: message_generations is Chat Service responsibility (Task 4).
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.models.enums import RouteType
from app.services.query_router.interfaces.query_log_repository import QueryLogRepository
from app.services.query_router.logging_models import (
    QueryRoutingLogContext,
    QueryRoutingLogResult,
)
from app.services.query_router.logging_service import (
    QueryRoutingLogger,
    log_query_routing,
)

__all__ = [
    "QueryRoutingLogContext",
    "QueryRoutingLogResult",
    "QueryRoutingLogger",
    "RouteLogResult",
    "log_query_routing",
    "log_route_decision",
]


@dataclass(slots=True)
class RouteLogResult:
    """Legacy result shape for orchestrator / tests."""

    query_log_id: UUID | None
    message_generation_id: UUID | None = None
    persisted: bool = True


async def log_route_decision(
    *,
    observability: QueryLogRepository,
    workspace_id: UUID,
    user_id: UUID,
    query_text: str,
    route_type: RouteType,
    message_id: UUID | None,
    cache_id: UUID | None,
    latency_ms: int,
    llm_calls_count: int = 0,
    model_used: str | None = None,
    session_id: UUID | None = None,
) -> RouteLogResult:
    """Compat wrapper — writes ``query_logs`` only via ``log_query_routing``.

    Does **not** write ``message_generations`` (Chat Service owns that table).
    """
    result = await log_query_routing(
        QueryRoutingLogContext(
            workspace_id=workspace_id,
            user_id=user_id,
            query_text=query_text,
            route_type=route_type,
            latency_ms=latency_ms,
            llm_calls_count=llm_calls_count,
            cache_id=cache_id,
            message_id=message_id,
            model_used=model_used,
            session_id=session_id,
        ),
        repository=observability,
    )
    return RouteLogResult(
        query_log_id=result.query_log_id,
        message_generation_id=None,
        persisted=result.persisted,
    )
