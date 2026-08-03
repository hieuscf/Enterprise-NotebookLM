# =============================================================================
# File: agent_events.py
# Module/Service: Chat Service / Confidence Engine
# Layer: Schema
# Purpose: ORM model for event-driven Micro Agent activations (FR14).
# Responsibilities:
#   - Persist agent_type, trigger_reason, payloads, and cost/latency per activation
# Dependencies:
#   - app.db.base, app.models.enums, app.models.types
# Public Exports:
#   - AgentEvent
# Database/Table: agent_events
# Related Modules: database-design-enterprise-notebooklm.md §5b, message_generations
# Important Notes: 0–N per message — one row per Micro Agent activation
#   (e.g. Rewrite then Graph → 2 rows). Only written when Low Confidence.
# =============================================================================

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, Numeric, String, desc
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import AgentTriggerReason, AgentType
from app.models.types import (
    agent_trigger_reason_enum,
    agent_type_enum,
    created_at_col,
    uuid_pk,
)


class AgentEvent(Base):
    __tablename__ = "agent_events"
    __table_args__ = (
        Index("ix_agent_events_message_id", "message_id"),
        Index(
            "ix_agent_events_agent_type_created_at",
            "agent_type",
            desc("created_at"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_type: Mapped[AgentType] = mapped_column(agent_type_enum, nullable=False)
    trigger_reason: Mapped[AgentTriggerReason] = mapped_column(
        agent_trigger_reason_enum, nullable=False
    )
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    input_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    output_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    triggered_second_retrieval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    model_used: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False, server_default="0"
    )
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = created_at_col()
