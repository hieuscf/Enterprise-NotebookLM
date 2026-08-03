# =============================================================================
# File: agent_events.py
# Module/Service: Chat Service / Observability (FR14)
# Layer: Repository
# Purpose: Persist and list agent_events rows for Complex Query audit trail.
# Responsibilities:
#   - insert_from_event_data — map AgentEventData → AgentEvent (1:1)
#   - list_by_message — public GET fields only (no JSON payloads)
#   - mark_second_retrieval — set triggered_second_retrieval after pass=2
# Dependencies:
#   - SQLAlchemy AsyncSession, app.models.agent_events, AgentEventData
# Public Exports:
#   - AgentEventRepository, AgentEventListRow
# Database/Table: agent_events, chat_messages, chat_sessions
# Related Modules: ComplexQueryPipeline, AgentEventsService
# Important Notes: Persistence failures must not crash the chat request (caller).
# =============================================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_events import AgentEvent
from app.models.chat import ChatMessage, ChatSession
from app.models.enums import AgentTriggerReason, AgentType

# Avoid importing event_policy package here (circular with ComplexQueryPipeline).
# Callers pass AgentEventData-compatible objects (duck-typed attributes).


@dataclass(frozen=True, slots=True)
class AgentEventListRow:
    """Columns exposed by GET agent-events (no payloads)."""

    id: uuid.UUID
    agent_type: AgentType
    trigger_reason: AgentTriggerReason
    confidence_score: float | None
    triggered_second_retrieval: bool
    model_used: str | None
    cost_usd: Decimal
    latency_ms: int
    created_at: datetime


class AgentEventRepository:
    """Postgres access for ``agent_events`` (workspace-scoped reads)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert_from_event_data(
        self,
        *,
        message_id: uuid.UUID,
        event: Any,
        triggered_second_retrieval: bool | None = None,
    ) -> AgentEvent:
        """Insert one ``agent_events`` row from agent output (schema-aligned).

        ``event`` is typically ``AgentEventData`` (attribute-compatible).
        """
        second = (
            event.triggered_second_retrieval
            if triggered_second_retrieval is None
            else triggered_second_retrieval
        )
        row = AgentEvent(
            id=uuid.uuid4(),
            message_id=message_id,
            agent_type=event.agent_type,
            trigger_reason=event.trigger_reason,
            confidence_score=event.confidence_score,
            input_payload=event.input_payload,
            output_payload=event.output_payload,
            triggered_second_retrieval=bool(second),
            model_used=event.model_used,
            cost_usd=event.cost_usd if event.cost_usd is not None else Decimal("0"),
            latency_ms=int(event.latency_ms),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def mark_second_retrieval(self, event_id: uuid.UUID, *, value: bool = True) -> None:
        """Update ``triggered_second_retrieval`` after Second Retrieval runs."""
        row = await self._session.get(AgentEvent, event_id)
        if row is None:
            return
        row.triggered_second_retrieval = value
        await self._session.flush()

    async def list_by_message(
        self,
        *,
        workspace_id: uuid.UUID,
        message_id: uuid.UUID,
    ) -> list[AgentEventListRow] | None:
        """Return events for ``message_id`` if it belongs to ``workspace_id``.

        Returns:
            ``None`` when the message is missing / outside the workspace.
            Empty list when the message exists but has no agent events.
        """
        owned = await self._session.scalar(
            select(ChatMessage.id)
            .join(ChatSession, ChatSession.id == ChatMessage.session_id)
            .where(
                ChatMessage.id == message_id,
                ChatSession.workspace_id == workspace_id,
            )
            .limit(1)
        )
        if owned is None:
            return None

        stmt = (
            select(
                AgentEvent.id,
                AgentEvent.agent_type,
                AgentEvent.trigger_reason,
                AgentEvent.confidence_score,
                AgentEvent.triggered_second_retrieval,
                AgentEvent.model_used,
                AgentEvent.cost_usd,
                AgentEvent.latency_ms,
                AgentEvent.created_at,
            )
            .where(AgentEvent.message_id == message_id)
            .order_by(AgentEvent.created_at.asc())
        )
        result = await self._session.execute(stmt)
        rows: list[AgentEventListRow] = []
        for r in result.all():
            rows.append(
                AgentEventListRow(
                    id=r.id,
                    agent_type=r.agent_type,
                    trigger_reason=r.trigger_reason,
                    confidence_score=r.confidence_score,
                    triggered_second_retrieval=bool(r.triggered_second_retrieval),
                    model_used=r.model_used,
                    cost_usd=r.cost_usd if r.cost_usd is not None else Decimal("0"),
                    latency_ms=int(r.latency_ms),
                    created_at=r.created_at,
                )
            )
        return rows
