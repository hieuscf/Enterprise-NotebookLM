# =============================================================================
# File: chat.py
# Module/Service: Chat Service
# Layer: Schema
# Purpose: ORM models for chat sessions, messages, and LLM generation metrics.
# Responsibilities:
#   - Persist conversation memory (FR4, FR10) and generation metrics (FR13)
# Dependencies:
#   - app.db.base, app.models.enums, app.models.types
# Public Exports:
#   - ChatSession, ChatMessage, MessageGeneration
# Database/Table: chat_sessions, chat_messages, message_generations
# Related Modules: database-design-enterprise-notebooklm.md §5
# Important Notes: chat_messages hold content only; metrics live in
#   message_generations (1–1 optional via UNIQUE message_id).
# =============================================================================

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, Float, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import ConfidenceLevel, FinishReason, MessageRole, RouteType
from app.models.types import (
    confidence_level_enum,
    created_at_col,
    finish_reason_enum,
    message_role_enum,
    route_type_enum,
    updated_at_col,
    uuid_pk,
)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[MessageRole] = mapped_column(message_role_enum, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = created_at_col()


class MessageGeneration(Base):
    __tablename__ = "message_generations"

    id: Mapped[uuid.UUID] = uuid_pk()
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    route_type: Mapped[RouteType] = mapped_column(route_type_enum, nullable=False)
    confidence_level: Mapped[ConfidenceLevel | None] = mapped_column(
        confidence_level_enum, nullable=True
    )
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    agent_triggered: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    model_used: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    top_p: Mapped[float | None] = mapped_column(Float, nullable=True)
    finish_reason: Mapped[FinishReason | None] = mapped_column(finish_reason_enum, nullable=True)
    created_at: Mapped[datetime] = created_at_col()
