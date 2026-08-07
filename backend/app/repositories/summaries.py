# =============================================================================
# File: summaries.py
# Module/Service: Summary Service (FR6)
# Layer: Repository
# Purpose: Async data access for summaries + topic context for by_topic style.
# Responsibilities:
#   - CRUD summaries scoped via document → workspace join
#   - List topics linked to chunks of a document_version (topic hierarchy)
# Dependencies:
#   - SQLAlchemy AsyncSession; artifacts / knowledge / documents models
# Public Exports:
#   - SummaryRepository, TopicContextRow
# Database/Table: summaries, topics, topic_chunks, document_chunks, documents
# Related Modules: app.services.summary.summary_service
# Important Notes: Always filter by workspace_id for multi-tenant isolation.
# =============================================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artifacts import Summary
from app.models.documents import Document
from app.models.enums import SummaryType
from app.models.knowledge import DocumentChunk, Topic, TopicChunk


@dataclass(frozen=True, slots=True)
class TopicContextRow:
    """Topic row linked to at least one chunk of a document version."""

    topic_id: uuid.UUID
    name: str
    level: int
    summary: str | None
    parent_topic_id: uuid.UUID | None


class SummaryRepository:
    """Postgres data access for FR6 summaries."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        document_id: uuid.UUID,
        created_by: uuid.UUID,
        source_version_id: uuid.UUID,
        type_: SummaryType,
        content: str,
        model_used: str | None,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: Decimal,
        latency_ms: int | None,
    ) -> Summary:
        row = Summary(
            document_id=document_id,
            created_by=created_by,
            source_version_id=source_version_id,
            type=type_,
            content=content,
            model_used=model_used,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(
        self,
        *,
        workspace_id: uuid.UUID,
        summary_id: uuid.UUID,
    ) -> Summary | None:
        stmt = (
            select(Summary)
            .join(Document, Document.id == Summary.document_id)
            .where(
                Summary.id == summary_id,
                Document.workspace_id == workspace_id,
            )
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_for_document(
        self,
        *,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> list[Summary]:
        stmt = (
            select(Summary)
            .join(Document, Document.id == Summary.document_id)
            .where(
                Summary.document_id == document_id,
                Document.workspace_id == workspace_id,
            )
            .order_by(Summary.created_at.desc())
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def delete(self, summary: Summary) -> None:
        await self._session.delete(summary)
        await self._session.flush()

    async def list_topics_for_version(
        self,
        *,
        workspace_id: uuid.UUID,
        document_version_id: uuid.UUID,
    ) -> list[TopicContextRow]:
        """Topics linked via topic_chunks to chunks of ``document_version_id``."""
        stmt = (
            select(Topic)
            .join(TopicChunk, TopicChunk.topic_id == Topic.id)
            .join(DocumentChunk, DocumentChunk.id == TopicChunk.chunk_id)
            .where(
                Topic.workspace_id == workspace_id,
                DocumentChunk.document_version_id == document_version_id,
            )
            .distinct()
            .order_by(Topic.level.asc(), Topic.name.asc())
        )
        topics = (await self._session.execute(stmt)).scalars().all()
        return [
            TopicContextRow(
                topic_id=t.id,
                name=t.name,
                level=int(t.level),
                summary=t.summary,
                parent_topic_id=t.parent_topic_id,
            )
            for t in topics
        ]
