# =============================================================================
# File: retrieval.py
# Module/Service: Search Service / Citation Verification Layer
# Layer: Schema
# Purpose: ORM models for retrievals and citations (FR3, FR5).
# Responsibilities:
#   - Persist all retrieval candidates and verified citation subset
# Dependencies:
#   - app.db.base, app.models.enums, app.models.types
# Public Exports:
#   - Retrieval, Citation
# Database/Table: retrievals, citations
# Related Modules: database-design-enterprise-notebooklm.md §6
# Important Notes: citations.retrieval_id → retrievals; no document_id on citations.
# =============================================================================

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import RetrievalMethod
from app.models.types import created_at_col, retrieval_method_enum, uuid_pk


class Retrieval(Base):
    __tablename__ = "retrievals"
    __table_args__ = (
        Index("ix_retrievals_message_id_rank", "message_id", "rank"),
        Index("ix_retrievals_message_id_retrieval_pass", "message_id", "retrieval_pass"),
        Index(
            "ix_retrievals_message_id_retrieval_pass_rank",
            "message_id",
            "retrieval_pass",
            "rank",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="SET NULL"), nullable=True
    )
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL"), nullable=True
    )
    retrieval_method: Mapped[RetrievalMethod] = mapped_column(retrieval_method_enum, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    retrieval_pass: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = created_at_col()


class Citation(Base):
    __tablename__ = "citations"

    id: Mapped[uuid.UUID] = uuid_pk()
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    retrieval_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("retrievals.id", ondelete="CASCADE"), nullable=False
    )
    text_snippet: Mapped[str] = mapped_column(Text, nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
