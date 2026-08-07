# =============================================================================
# File: summaries.py
# Module/Service: Summary Service (FR6)
# Layer: Repository
# Purpose: Async data access for summaries + topic context for by_topic style.
# Responsibilities:
#   - Create processing summaries; update completed/failed results
#   - Workspace-scoped get/list/delete; worker get_by_id
#   - List topics linked to chunks of a document_version
# Dependencies:
#   - SQLAlchemy AsyncSession; artifacts / knowledge / documents models
# Public Exports:
#   - SummaryRepository, TopicContextRow
# Database/Table: summaries, topics, topic_chunks, document_chunks, documents
# Related Modules: app.services.summary.summary_service
# Important Notes:
#   - Always filter by workspace_id for HTTP multi-tenant isolation.
#   - Status transitions: processing → completed|failed only (optimistic WHERE).
# =============================================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artifacts import Summary
from app.models.documents import Document
from app.models.enums import SummaryStatus, SummaryType
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

    async def create_processing(
        self,
        *,
        document_id: uuid.UUID,
        created_by: uuid.UUID,
        source_version_id: uuid.UUID,
        type_: SummaryType,
    ) -> Summary:
        """Insert a processing Summary with null content (POST / 202 path)."""
        row = Summary(
            document_id=document_id,
            created_by=created_by,
            source_version_id=source_version_id,
            type=type_,
            status=SummaryStatus.processing,
            content=None,
            sections=None,
            model_used=None,
            prompt_tokens=0,
            completion_tokens=0,
            cost_usd=Decimal("0"),
            latency_ms=None,
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

    async def get_by_id(self, summary_id: uuid.UUID) -> Summary | None:
        """Load by primary key (Celery worker — no workspace filter)."""
        return await self._session.get(Summary, summary_id)

    async def list_for_document(
        self,
        *,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> list[Summary]:
        """All summary history for a document (all styles / versions), newest first."""
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

    async def update_generation_result(
        self,
        *,
        summary_id: uuid.UUID,
        content: str,
        model_used: str | None,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: Decimal,
        latency_ms: int | None,
        sections: list[dict] | None = None,
    ) -> bool:
        """processing → completed. Returns False if row missing or not processing."""
        stmt = (
            update(Summary)
            .where(
                Summary.id == summary_id,
                Summary.status == SummaryStatus.processing,
            )
            .values(
                content=content,
                sections=sections,
                model_used=model_used,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
                status=SummaryStatus.completed,
            )
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return bool(result.rowcount)

    async def mark_failed(self, *, summary_id: uuid.UUID) -> bool:
        """processing → failed. Safe public API: no error payload persisted."""
        stmt = (
            update(Summary)
            .where(
                Summary.id == summary_id,
                Summary.status == SummaryStatus.processing,
            )
            .values(
                status=SummaryStatus.failed,
                content=None,
            )
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return bool(result.rowcount)

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
