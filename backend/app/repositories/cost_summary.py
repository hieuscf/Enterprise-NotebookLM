# =============================================================================
# File: cost_summary.py
# Module/Service: Observability Module (FR13 + FR14)
# Layer: Repository
# Purpose: Aggregate LLM + Micro Agent cost/latency/tokens for admin cost-summary.
# Responsibilities:
#   - Summarize message_generations by model / route_type (workspace-scoped)
#   - Sum prompt/completion/total tokens (NULL → 0)
#   - Summarize agent_events by agent_type (by_agent_type extension)
# Dependencies:
#   - SQLAlchemy AsyncSession, chat + agent_events models
# Public Exports:
#   - CostSummaryRepository, AgentTypeCostAgg, ModelCostAgg, RouteTypeAgg,
#     GenerationTotals
# Database/Table: message_generations, agent_events, chat_messages, chat_sessions
# Related Modules: CostSummaryService, OpenAPI CostSummary
# Important Notes: Multi-tenant filter via chat_sessions.workspace_id always.
# =============================================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time
from datetime import timezone as tz
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_events import AgentEvent
from app.models.chat import ChatMessage, ChatSession, MessageGeneration
from app.models.enums import AgentType


@dataclass(frozen=True, slots=True)
class ModelCostAgg:
    model_used: str
    calls: int
    cost_usd: Decimal
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True, slots=True)
class RouteTypeAgg:
    route_type: str
    count: int


@dataclass(frozen=True, slots=True)
class GenerationTotals:
    total_cost_usd: Decimal
    total_llm_calls: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int


@dataclass(frozen=True, slots=True)
class AgentTypeCostAgg:
    agent_type: str
    count: int
    total_cost_usd: Decimal
    total_latency_ms: int
    average_latency_ms: float


class CostSummaryRepository:
    """Read-only aggregates for ``GET /admin/.../cost-summary``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def summarize_generations(
        self,
        *,
        workspace_id: uuid.UUID,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> tuple[GenerationTotals, list[ModelCostAgg], list[RouteTypeAgg]]:
        """Aggregate ``message_generations`` scoped to workspace chat sessions."""
        date_filters = _created_at_filters(MessageGeneration.created_at, date_from, date_to)

        totals_row = (
            await self._session.execute(
                select(
                    func.coalesce(func.sum(MessageGeneration.cost_usd), 0).label("cost"),
                    func.count().label("calls"),
                    func.coalesce(func.sum(MessageGeneration.prompt_tokens), 0).label(
                        "prompt_tokens"
                    ),
                    func.coalesce(func.sum(MessageGeneration.completion_tokens), 0).label(
                        "completion_tokens"
                    ),
                    func.coalesce(func.sum(MessageGeneration.total_tokens), 0).label(
                        "total_tokens"
                    ),
                )
                .select_from(MessageGeneration)
                .join(ChatMessage, ChatMessage.id == MessageGeneration.message_id)
                .join(ChatSession, ChatSession.id == ChatMessage.session_id)
                .where(ChatSession.workspace_id == workspace_id, *date_filters)
            )
        ).one()

        totals = GenerationTotals(
            total_cost_usd=Decimal(str(totals_row.cost or 0)),
            total_llm_calls=int(totals_row.calls or 0),
            total_prompt_tokens=int(totals_row.prompt_tokens or 0),
            total_completion_tokens=int(totals_row.completion_tokens or 0),
            total_tokens=int(totals_row.total_tokens or 0),
        )

        model_rows = await self._session.execute(
            select(
                MessageGeneration.model_used,
                func.count().label("calls"),
                func.coalesce(func.sum(MessageGeneration.cost_usd), 0).label("cost_usd"),
                func.coalesce(func.sum(MessageGeneration.prompt_tokens), 0).label(
                    "prompt_tokens"
                ),
                func.coalesce(func.sum(MessageGeneration.completion_tokens), 0).label(
                    "completion_tokens"
                ),
                func.coalesce(func.sum(MessageGeneration.total_tokens), 0).label(
                    "total_tokens"
                ),
            )
            .join(ChatMessage, ChatMessage.id == MessageGeneration.message_id)
            .join(ChatSession, ChatSession.id == ChatMessage.session_id)
            .where(ChatSession.workspace_id == workspace_id, *date_filters)
            .group_by(MessageGeneration.model_used)
        )
        by_model = [
            ModelCostAgg(
                model_used=str(r.model_used or "unknown"),
                calls=int(r.calls),
                cost_usd=Decimal(str(r.cost_usd or 0)),
                prompt_tokens=int(r.prompt_tokens or 0),
                completion_tokens=int(r.completion_tokens or 0),
                total_tokens=int(r.total_tokens or 0),
            )
            for r in model_rows.all()
        ]

        route_rows = await self._session.execute(
            select(
                MessageGeneration.route_type,
                func.count().label("count"),
            )
            .join(ChatMessage, ChatMessage.id == MessageGeneration.message_id)
            .join(ChatSession, ChatSession.id == ChatMessage.session_id)
            .where(ChatSession.workspace_id == workspace_id, *date_filters)
            .group_by(MessageGeneration.route_type)
        )
        by_route = [
            RouteTypeAgg(
                route_type=r.route_type.value
                if hasattr(r.route_type, "value")
                else str(r.route_type),
                count=int(r.count),
            )
            for r in route_rows.all()
        ]
        return totals, by_model, by_route

    async def summarize_agents(
        self,
        *,
        workspace_id: uuid.UUID,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[str, AgentTypeCostAgg]:
        """Group ``agent_events`` by agent_type for ``by_agent_type``."""
        date_filters = _created_at_filters(AgentEvent.created_at, date_from, date_to)
        rows = await self._session.execute(
            select(
                AgentEvent.agent_type,
                func.count().label("count"),
                func.coalesce(func.sum(AgentEvent.cost_usd), 0).label("total_cost_usd"),
                func.coalesce(func.sum(AgentEvent.latency_ms), 0).label("total_latency_ms"),
            )
            .join(ChatMessage, ChatMessage.id == AgentEvent.message_id)
            .join(ChatSession, ChatSession.id == ChatMessage.session_id)
            .where(ChatSession.workspace_id == workspace_id, *date_filters)
            .group_by(AgentEvent.agent_type)
        )
        out: dict[str, AgentTypeCostAgg] = {}
        for r in rows.all():
            agent = (
                r.agent_type.value
                if isinstance(r.agent_type, AgentType)
                else str(r.agent_type)
            )
            count = int(r.count)
            total_latency = int(r.total_latency_ms or 0)
            out[agent] = AgentTypeCostAgg(
                agent_type=agent,
                count=count,
                total_cost_usd=Decimal(str(r.total_cost_usd or 0)),
                total_latency_ms=total_latency,
                average_latency_ms=(total_latency / count) if count else 0.0,
            )
        return out


def _created_at_filters(
    column: Any,
    date_from: date | None,
    date_to: date | None,
) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = []
    if date_from is not None:
        start = datetime.combine(date_from, time.min, tzinfo=tz.utc)
        filters.append(column >= start)
    if date_to is not None:
        end = datetime.combine(date_to, time.max, tzinfo=tz.utc)
        filters.append(column <= end)
    return filters
