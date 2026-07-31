# =============================================================================
# File: logging.py
# Module/Service: Query Router Execution / Unified Logging
# Layer: Service
# Purpose: Persist query_logs (+ message_generations) for every route_type.
# Responsibilities:
#   - log_route_decision for cache_hit / metadata / factoid / complex
#   - 0-LLM branches: llm_calls_count=0, model_used=NULL, tokens/cost=0
# Dependencies:
#   - QueryObservabilityRepository
# Public Exports:
#   - log_route_decision, RouteLogResult
# Database/Table: query_logs, message_generations
# Related Modules: app.services.query_router.orchestrator
# Important Notes:
#   - message_generations.message_id is NOT NULL — requires Chat message id.
#   - Never log full document / chunk text bodies.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.core.logging import get_logger
from app.models.enums import RouteType
from app.repositories.query_logs import QueryObservabilityRepository

logger = get_logger(__name__)


@dataclass(slots=True)
class RouteLogResult:
    """Ids of observability rows written for one request."""

    query_log_id: UUID
    message_generation_id: UUID | None


async def log_route_decision(
    *,
    observability: QueryObservabilityRepository,
    workspace_id: UUID,
    user_id: UUID,
    query_text: str,
    route_type: RouteType,
    message_id: UUID | None,
    cache_id: UUID | None,
    latency_ms: int,
    llm_calls_count: int = 0,
    model_used: str | None = None,
) -> RouteLogResult:
    """Write one ``query_logs`` row and optionally one ``message_generations`` row.

    Always called for every route_type after branch execution. For 0-LLM routes
    callers must pass ``llm_calls_count=0`` and ``model_used=None``.

    Args:
        observability: Repository for query_logs / message_generations.
        workspace_id: Tenant scope.
        user_id: Authenticated user.
        query_text: User query (not document body).
        route_type: Final executed route (after metadata fallback if any).
        message_id: Assistant ``chat_messages.id`` when available (required for
            ``message_generations`` FK). Chat Service must supply this.
        cache_id: ``query_cache.id`` on cache_hit; else None.
        latency_ms: End-to-end orchestrator latency.
        llm_calls_count: Number of LLM calls (0 for Part 4 branches).
        model_used: Model name or None for 0-LLM.

    Returns:
        ``RouteLogResult`` with persisted ids.
    """
    # Truncate for storage safety — never treat as document content dump.
    safe_query = (query_text or "")[:4000]

    log_row = await observability.create_query_log(
        workspace_id=workspace_id,
        user_id=user_id,
        query_text=safe_query,
        route_type=route_type,
        message_id=message_id,
        cache_id=cache_id,
        llm_calls_count=llm_calls_count,
        model_used=model_used,
        latency_ms=latency_ms,
    )

    generation_id: UUID | None = None
    if message_id is not None:
        gen_row = await observability.create_message_generation(
            message_id=message_id,
            route_type=route_type,
            model_used=model_used,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            cost_usd=Decimal("0"),
            latency_ms=latency_ms,
        )
        generation_id = gen_row.id
    else:
        logger.debug(
            "message_generations_skipped_no_message_id",
            workspace_id=str(workspace_id),
            route_type=route_type.value,
        )

    logger.info(
        "query_route_logged",
        workspace_id=str(workspace_id),
        user_id=str(user_id),
        route_type=route_type.value,
        latency_ms=latency_ms,
        llm_calls_count=llm_calls_count,
        cache_hit=route_type == RouteType.cache_hit,
        query_log_id=str(log_row.id),
        message_generation_id=str(generation_id) if generation_id else None,
    )
    return RouteLogResult(
        query_log_id=log_row.id,
        message_generation_id=generation_id,
    )
