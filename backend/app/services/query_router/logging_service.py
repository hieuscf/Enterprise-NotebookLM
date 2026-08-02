# =============================================================================
# File: logging_service.py
# Module/Service: Query Router — Unified Routing Logging (FR11)
# Layer: Service
# Purpose: Single entry point to persist query_logs for every route (0/1 LLM).
# Responsibilities:
#   - log_query_routing(context) → exactly one create_log attempt
#   - Best-effort: repository failures never crash the request
# Dependencies:
#   - QueryLogRepository Protocol, QueryRoutingLogContext
# Public Exports:
#   - log_query_routing, QueryRoutingLogger
# Database/Table: query_logs only (message_generations = Chat Service)
# Related Modules: orchestrator
# Important Notes:
#   - Handlers must NOT write query_logs themselves.
#   - Do not write message_generations here.
# =============================================================================

from __future__ import annotations

from app.core.logging import get_logger
from app.services.query_router.interfaces.query_log_repository import QueryLogRepository
from app.services.query_router.logging_models import (
    QueryRoutingLogContext,
    QueryRoutingLogResult,
)

logger = get_logger(__name__)

_QUERY_TEXT_MAX_CHARS = 4000


class QueryRoutingLogger:
    """Centralized Query Router logger (one row per query)."""

    def __init__(self, repository: QueryLogRepository) -> None:
        self._repo = repository

    async def log_query_routing(
        self,
        routing_context: QueryRoutingLogContext,
    ) -> QueryRoutingLogResult:
        """Persist exactly one ``query_logs`` row for the routed query.

        Args:
            routing_context: Fully populated routing outcome.

        Returns:
            ``QueryRoutingLogResult`` — ``persisted=False`` on repository errors.
        """
        ctx = routing_context
        safe_query = (ctx.query_text or "")[:_QUERY_TEXT_MAX_CHARS]
        try:
            row = await self._repo.create_log(
                workspace_id=ctx.workspace_id,
                user_id=ctx.user_id,
                query_text=safe_query,
                route_type=ctx.route_type,
                message_id=ctx.message_id,
                cache_id=ctx.cache_id,
                llm_calls_count=int(ctx.llm_calls_count),
                model_used=ctx.model_used,
                latency_ms=int(ctx.latency_ms),
            )
        except Exception as exc:  # noqa: BLE001 — best-effort observability
            logger.exception(
                "query_routing_log_failed",
                workspace_id=str(ctx.workspace_id),
                user_id=str(ctx.user_id),
                route_type=ctx.route_type.value,
                error=str(exc),
            )
            return QueryRoutingLogResult(
                query_log_id=None,
                persisted=False,
                error=str(exc),
            )

        logger.info(
            "query_routing_logged",
            workspace_id=str(ctx.workspace_id),
            user_id=str(ctx.user_id),
            route_type=ctx.route_type.value,
            latency_ms=ctx.latency_ms,
            llm_calls_count=ctx.llm_calls_count,
            cache_id=str(ctx.cache_id) if ctx.cache_id else None,
            model_used=ctx.model_used,
            session_id=str(ctx.session_id) if ctx.session_id else None,
            query_log_id=str(row.id),
        )
        return QueryRoutingLogResult(query_log_id=row.id, persisted=True, error=None)


async def log_query_routing(
    routing_context: QueryRoutingLogContext,
    *,
    repository: QueryLogRepository,
) -> QueryRoutingLogResult:
    """Module-level entry point — prefer injecting ``QueryRoutingLogger`` in DI."""
    return await QueryRoutingLogger(repository).log_query_routing(routing_context)
