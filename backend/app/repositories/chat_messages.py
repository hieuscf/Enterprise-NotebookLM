# =============================================================================
# File: chat_messages.py
# Module/Service: Chat Service
# Layer: Repository
# Purpose: Read-only data access for chat_messages (+ nested generation/citations).
# Responsibilities:
#   - list() with created_at ASC pagination
#   - list_for_session() all messages ASC (report aggregation / export)
#   - get_with_relations_for_workspace() for GET .../messages/{id}
#   - count() / latest() for Part 2 summary helpers
#   - Batch-load message_generations + citations (with document_id via joins)
# Dependencies:
#   - SQLAlchemy AsyncSession; chat / retrieval / knowledge / documents models
# Public Exports:
#   - ChatMessageRepository, CitationWithDocument, MessageWithRelations
# Database/Table: chat_messages, message_generations, citations, retrievals,
#   document_chunks, document_versions, entities, chat_sessions
# Related Modules: app.services.chat.session_service, report_aggregation
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

from app.models.chat import ChatMessage, ChatSession, MessageGeneration
from app.models.documents import DocumentVersion
from app.models.enums import MessageRole
from app.models.knowledge import DocumentChunk, Entity
from app.models.retrieval import Citation, Retrieval


@dataclass(frozen=True, slots=True)
class CitationWithDocument:
    """Citation row + locator fields resolved via retrieval → chunk|entity joins."""

    citation: Citation
    document_id: uuid.UUID | None
    chunk_id: uuid.UUID | None = None
    document_version_id: uuid.UUID | None = None
    page_number: int | None = None
    section_index: int | None = None
    section: str | None = None
    chunk_content: str | None = None


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

    async def list_for_session(
        self,
        *,
        session_id: uuid.UUID,
    ) -> list[ChatMessage]:
        """All messages in a session, oldest→newest (no nested relations)."""
        result = await self._session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
        )
        return list(result.scalars().all())

    async def create(
        self,
        *,
        session_id: uuid.UUID,
        role: MessageRole,
        content: str,
    ) -> ChatMessage:
        """Insert a chat message (user or assistant)."""
        row = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def update_content(self, message_id: uuid.UUID, content: str) -> ChatMessage | None:
        """Replace assistant content after generation completes."""
        result = await self._session.execute(
            select(ChatMessage).where(ChatMessage.id == message_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        row.content = content
        await self._session.flush()
        return row

    async def get(self, message_id: uuid.UUID) -> ChatMessage | None:
        result = await self._session.execute(
            select(ChatMessage).where(ChatMessage.id == message_id)
        )
        return result.scalar_one_or_none()

    async def get_with_relations_for_workspace(
        self,
        *,
        workspace_id: uuid.UUID,
        message_id: uuid.UUID,
    ) -> MessageWithRelations | None:
        """Load one message (+ generation/citations) when it belongs to workspace.

        Returns ``None`` when the message is missing or outside ``workspace_id``.
        Soft-deleted sessions are still considered in-workspace (matches agent-events).
        """
        message = (
            await self._session.execute(
                select(ChatMessage)
                .join(ChatSession, ChatSession.id == ChatMessage.session_id)
                .where(
                    ChatMessage.id == message_id,
                    ChatSession.workspace_id == workspace_id,
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if message is None:
            return None

        generations = await self._load_generations([message.id])
        citations = await self._load_citations([message.id])
        return MessageWithRelations(
            message=message,
            generation=generations.get(message.id),
            citations=citations.get(message.id, []),
        )

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

    async def list_citations_for_message(
        self, message_id: uuid.UUID
    ) -> list[CitationWithDocument]:
        """Locator-enriched citations for one assistant message (post-persist)."""
        by_message = await self._load_citations([message_id])
        return by_message.get(message_id, [])

    async def _load_citations(
        self, message_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[CitationWithDocument]]:
        """Load citations ordered by order_index; resolve document + chunk locator."""
        chunk_version = aliased(DocumentVersion)
        entity_version = aliased(DocumentVersion)

        document_id_expr = func.coalesce(
            chunk_version.document_id,
            entity_version.document_id,
        )
        version_id_expr = func.coalesce(
            DocumentChunk.document_version_id,
            Entity.source_version_id,
        )

        stmt = (
            select(
                Citation,
                document_id_expr,
                Retrieval.chunk_id,
                version_id_expr,
                DocumentChunk.page_number,
                DocumentChunk.section_index,
                DocumentChunk.section,
                DocumentChunk.content,
            )
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
        for (
            citation,
            document_id,
            chunk_id,
            document_version_id,
            page_number,
            section_index,
            section,
            chunk_content,
        ) in rows:
            by_message.setdefault(citation.message_id, []).append(
                CitationWithDocument(
                    citation=citation,
                    document_id=document_id,
                    chunk_id=chunk_id,
                    document_version_id=document_version_id,
                    page_number=page_number,
                    section_index=section_index,
                    section=section,
                    chunk_content=chunk_content,
                )
            )
        return by_message
