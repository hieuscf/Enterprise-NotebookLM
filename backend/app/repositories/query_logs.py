# =============================================================================
# File: query_logs.py
# Module/Service: Query Router / Observability
# Layer: Repository
# Purpose: Persist query_logs and message_generations for router execution (FR11/FR13).
# Responsibilities:
#   - Insert one query_logs row per routed request
#   - Insert one message_generations row when message_id is provided (FK required)
# Dependencies:
#   - SQLAlchemy AsyncSession, app.models.query, app.models.chat
# Public Exports:
#   - QueryObservabilityRepository
# Database/Table: query_logs, message_generations
# Related Modules: app.services.query_router.logging
# Important Notes: message_generations.message_id is NOT NULL — skip if absent.
# =============================================================================

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import MessageGeneration
from app.models.enums import RouteType
from app.models.query import QueryLog


class QueryObservabilityRepository:
    """Write-side repository for router observability tables."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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
