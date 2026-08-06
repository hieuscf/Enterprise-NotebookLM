# =============================================================================
# File: chat_messages.py
# Module/Service: Chat Service
# Layer: Repository
# Purpose: Read-only data access for chat_messages (+ nested generation/citations).
# Responsibilities:
#   - list() with created_at ASC pagination
#   - count() / latest() for Part 2 summary helpers
#   - Batch-load message_generations + citations (with document_id via joins)
# Dependencies:
#   - SQLAlchemy AsyncSession; chat / retrieval / knowledge / documents models
# Public Exports:
#   - ChatMessageRepository, CitationWithDocument, MessageWithRelations
# Database/Table: chat_messages, message_generations, citations, retrievals,
#   document_chunks, document_versions, entities
# Related Modules: app.services.chat.session_service
# Important Notes:
#   - Part 1: NO create(). Part 2 owns message insert + generation writes.
#   - document_id is not on citations; resolve via retrieval → chunk|entity → version.
# =============================================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.chat import ChatMessage, MessageGeneration
from app.models.documents import DocumentVersion
from app.models.knowledge import DocumentChunk, Entity
from app.models.retrieval import Citation, Retrieval


@dataclass(frozen=True, slots=True)
class CitationWithDocument:
    citation: Citation
    document_id: uuid.UUID | None


@dataclass(slots=True)
class MessageWithRelations:
    message: ChatMessage
    generation: MessageGeneration | None = None
    citations: list[CitationWithDocument] = field(default_factory=list)


class ChatMessageRepository:
    """Read helpers for conversation history (no writes in Part 1)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(
        self,
        *,
        session_id: uuid.UUID,
        page: int,
        page_size: int,
    ) -> list[MessageWithRelations]:
        """Messages oldest→newest with nested generation + citations."""
        offset = (page - 1) * page_size
        messages = (
            await self._session.execute(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at.asc())
                .offset(offset)
                .limit(page_size)
            )
        ).scalars().all()
        if not messages:
            return []

        message_ids = [m.id for m in messages]
        generations = await self._load_generations(message_ids)
        citations = await self._load_citations(message_ids)

        return [
            MessageWithRelations(
                message=m,
                generation=generations.get(m.id),
                citations=citations.get(m.id, []),
            )
            for m in messages
        ]

    async def count(self, *, session_id: uuid.UUID) -> int:
        """Total messages in a session (for Part 2 last_message summary)."""
        result = await self._session.execute(
            select(func.count())
            .select_from(ChatMessage)
            .where(ChatMessage.session_id == session_id)
        )
        return int(result.scalar_one())

    async def latest(self, *, session_id: uuid.UUID) -> ChatMessage | None:
        """Most recent message by created_at (Part 2 preview helper)."""
        result = await self._session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _load_generations(
        self, message_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, MessageGeneration]:
        rows = (
            await self._session.execute(
                select(MessageGeneration).where(
                    MessageGeneration.message_id.in_(message_ids)
                )
            )
        ).scalars().all()
        return {row.message_id: row for row in rows}

    async def _load_citations(
        self, message_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[CitationWithDocument]]:
        """Load citations ordered by order_index; resolve document_id via joins."""
        chunk_version = aliased(DocumentVersion)
        entity_version = aliased(DocumentVersion)

        document_id_expr = func.coalesce(
            chunk_version.document_id,
            entity_version.document_id,
        )

        stmt = (
            select(Citation, document_id_expr)
            .join(Retrieval, Citation.retrieval_id == Retrieval.id)
            .outerjoin(DocumentChunk, Retrieval.chunk_id == DocumentChunk.id)
            .outerjoin(
                chunk_version,
                DocumentChunk.document_version_id == chunk_version.id,
            )
            .outerjoin(Entity, Retrieval.entity_id == Entity.id)
            .outerjoin(
                entity_version,
                Entity.source_version_id == entity_version.id,
            )
            .where(Citation.message_id.in_(message_ids))
            .order_by(Citation.message_id, Citation.order_index.asc())
        )
        rows = (await self._session.execute(stmt)).all()

        by_message: dict[uuid.UUID, list[CitationWithDocument]] = {}
        for citation, document_id in rows:
            by_message.setdefault(citation.message_id, []).append(
                CitationWithDocument(citation=citation, document_id=document_id)
            )
        return by_message
