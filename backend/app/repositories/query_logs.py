# =============================================================================
# File: query_logs.py
# Module/Service: Query Router / Observability
# Layer: Repository
# Purpose: Persist query_logs (+ optional message_generations for Chat Service).
# Responsibilities:
#   - QueryLogRepository.create_log — one query_logs row per routed request
#   - create_message_generation — Chat Service only (not Query Router logging)
# Dependencies:
#   - SQLAlchemy AsyncSession, app.models.query, app.models.chat
# Public Exports:
#   - QueryLogRepository, QueryObservabilityRepository
# Database/Table: query_logs, message_generations
# Related Modules: app.services.query_router.logging_service
# Important Notes: Schema fixed — no add/drop columns. Router uses create_log only.
# =============================================================================

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import MessageGeneration
from app.models.enums import RouteType
from app.models.query import QueryLog


class QueryLogRepository:
    """Postgres write access for ``query_logs`` (Task 4)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_log(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        query_text: str,
        route_type: RouteType,
        message_id: uuid.UUID | None,
        cache_id: uuid.UUID | None,
        llm_calls_count: int,
        model_used: str | None,
        latency_ms: int | None,
    ) -> QueryLog:
        """Insert exactly one ``query_logs`` row."""
        row = QueryLog(
            workspace_id=workspace_id,
            user_id=user_id,
            message_id=message_id,
            cache_id=cache_id,
            query_text=query_text,
            route_type=route_type,
            llm_calls_count=llm_calls_count,
            model_used=model_used,
            latency_ms=latency_ms,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    # Backward-compatible alias used by older call sites / fakes.
    async def create_query_log(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        query_text: str,
        route_type: RouteType,
        message_id: uuid.UUID | None,
        cache_id: uuid.UUID | None,
        llm_calls_count: int,
        model_used: str | None,
        latency_ms: int | None,
    ) -> QueryLog:
        return await self.create_log(
            workspace_id=workspace_id,
            user_id=user_id,
            query_text=query_text,
            route_type=route_type,
            message_id=message_id,
            cache_id=cache_id,
            llm_calls_count=llm_calls_count,
            model_used=model_used,
            latency_ms=latency_ms,
        )


class QueryObservabilityRepository(QueryLogRepository):
    """Extends ``QueryLogRepository`` with Chat-side ``message_generations``.

    Query Router Task-4 logging must use ``create_log`` only. Chat Service may
    call ``create_message_generation`` with tokens/cost after LLM / 0-LLM answers.
    """

    async def create_message_generation(
        self,
        *,
        message_id: uuid.UUID,
        route_type: RouteType,
        model_used: str | None,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        cost_usd: Decimal,
        latency_ms: int | None,
    ) -> MessageGeneration:
        row = MessageGeneration(
            message_id=message_id,
            route_type=route_type,
            confidence_level=None,
            confidence_score=None,
            agent_triggered=False,
            model_used=model_used,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            temperature=None,
            top_p=None,
            finish_reason=None,
        )
        self._session.add(row)
        await self._session.flush()
        return row
