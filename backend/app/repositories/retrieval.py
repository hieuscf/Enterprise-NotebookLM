# =============================================================================
# File: retrieval.py
# Module/Service: Search Service / Hybrid Retrieval
# Layer: Repository
# Purpose: Async Postgres lookups to hydrate chunks/documents for retrieval (FR3).
# Responsibilities:
#   - Resolve chunk content + document_id scoped by workspace_id
#   - Metadata queries (document list/count/stats) for Metadata Retrieval
# Dependencies:
#   - SQLAlchemy AsyncSession, app.models.documents, app.models.knowledge
# Public Exports:
#   - ChunkHydrationRow, MetadataDocumentRow, RetrievalRepository
# Database/Table: document_chunks, document_versions, documents, entities, users
# Related Modules: app.services.retrieval.*
# Important Notes: Always filter by workspace_id — multi-tenant isolation.
# =============================================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.documents import Document, DocumentVersion
from app.models.enums import FileType
from app.models.knowledge import DocumentChunk, Entity


@dataclass(frozen=True, slots=True)
class ChunkHydrationRow:
    """Chunk fields needed to build a RetrievalCandidate."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    workspace_id: uuid.UUID
    content: str
    title: str | None = None


@dataclass(frozen=True, slots=True)
class MetadataDocumentRow:
    """Document metadata row for Metadata Retrieval / Query Router."""

    document_id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    file_type: FileType
    created_at: datetime
    updated_at: datetime
    uploaded_by: uuid.UUID | None
    version_number: int | None
    status: str | None


class RetrievalRepository:
    """Postgres data access for Hybrid Retrieval hydration + metadata queries."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def hydrate_chunks(
        self,
        workspace_id: uuid.UUID,
        chunk_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, ChunkHydrationRow]:
        """Load chunk content + document_id for ids belonging to ``workspace_id``."""
        if not chunk_ids:
            return {}
        stmt: Select[tuple[DocumentChunk, Document, DocumentVersion]] = (
            select(DocumentChunk, Document, DocumentVersion)
            .join(
                DocumentVersion,
                DocumentVersion.id == DocumentChunk.document_version_id,
            )
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(
                Document.workspace_id == workspace_id,
                DocumentChunk.id.in_(chunk_ids),
            )
        )
        rows = (await self._session.execute(stmt)).all()
        out: dict[uuid.UUID, ChunkHydrationRow] = {}
        for chunk, document, version in rows:
            out[chunk.id] = ChunkHydrationRow(
                chunk_id=chunk.id,
                document_id=document.id,
                document_version_id=version.id,
                workspace_id=document.workspace_id,
                content=chunk.content or "",
                title=document.title,
            )
        return out

    async def chunks_for_entity_versions(
        self,
        workspace_id: uuid.UUID,
        source_version_ids: list[uuid.UUID],
        *,
        entity_names: list[str],
        limit: int = 20,
    ) -> list[ChunkHydrationRow]:
        """Fallback graph hydration: chunks of entity versions mentioning entity names."""
        if not source_version_ids:
            return []
        name_filters = [
            DocumentChunk.content.ilike(f"%{name}%") for name in entity_names if name.strip()
        ]
        conditions = [
            Document.workspace_id == workspace_id,
            DocumentChunk.document_version_id.in_(source_version_ids),
        ]
        if name_filters:
            conditions.append(or_(*name_filters))
        stmt = (
            select(DocumentChunk, Document, DocumentVersion)
            .join(
                DocumentVersion,
                DocumentVersion.id == DocumentChunk.document_version_id,
            )
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(*conditions)
            .order_by(DocumentChunk.chunk_index.asc())
            .limit(max(1, limit))
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            ChunkHydrationRow(
                chunk_id=chunk.id,
                document_id=document.id,
                document_version_id=version.id,
                workspace_id=document.workspace_id,
                content=chunk.content or "",
                title=document.title,
            )
            for chunk, document, version in rows
        ]

    async def document_id_for_version(
        self,
        workspace_id: uuid.UUID,
        document_version_id: uuid.UUID,
    ) -> uuid.UUID | None:
        stmt = (
            select(Document.id)
            .join(DocumentVersion, DocumentVersion.document_id == Document.id)
            .where(
                Document.workspace_id == workspace_id,
                DocumentVersion.id == document_version_id,
            )
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_documents_metadata(
        self,
        workspace_id: uuid.UUID,
        *,
        file_type: FileType | None = None,
        uploaded_after: datetime | None = None,
        uploaded_before: datetime | None = None,
        title_contains: str | None = None,
        limit: int = 50,
    ) -> list[MetadataDocumentRow]:
        """List documents with current-version upload metadata (Postgres only)."""
        filters = [Document.workspace_id == workspace_id]
        if file_type is not None:
            filters.append(Document.file_type == file_type)
        if uploaded_after is not None:
            filters.append(Document.created_at >= uploaded_after)
        if uploaded_before is not None:
            filters.append(Document.created_at <= uploaded_before)
        if title_contains:
            filters.append(Document.title.ilike(f"%{title_contains.strip()}%"))

        stmt = (
            select(Document, DocumentVersion)
            .outerjoin(
                DocumentVersion,
                DocumentVersion.id == Document.current_version_id,
            )
            .where(*filters)
            .order_by(Document.created_at.desc())
            .limit(max(1, limit))
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            MetadataDocumentRow(
                document_id=doc.id,
                workspace_id=doc.workspace_id,
                title=doc.title,
                file_type=doc.file_type,
                created_at=doc.created_at,
                updated_at=doc.updated_at,
                uploaded_by=version.uploaded_by if version else None,
                version_number=version.version_number if version else None,
                status=version.status.value if version else None,
            )
            for doc, version in rows
        ]

    async def count_documents(
        self,
        workspace_id: uuid.UUID,
        *,
        file_type: FileType | None = None,
    ) -> int:
        filters = [Document.workspace_id == workspace_id]
        if file_type is not None:
            filters.append(Document.file_type == file_type)
        stmt = select(func.count()).select_from(Document).where(*filters)
        return int((await self._session.execute(stmt)).scalar_one())

    async def count_by_file_type(
        self,
        workspace_id: uuid.UUID,
    ) -> dict[str, int]:
        stmt = (
            select(Document.file_type, func.count())
            .where(Document.workspace_id == workspace_id)
            .group_by(Document.file_type)
        )
        rows = (await self._session.execute(stmt)).all()
        return {str(ft.value if hasattr(ft, "value") else ft): int(cnt) for ft, cnt in rows}

    async def find_entities_by_name(
        self,
        workspace_id: uuid.UUID,
        query_text: str,
        *,
        limit: int = 20,
    ) -> list[Entity]:
        """Postgres entity fallback when Neo4j returns entity-only (no chunk link)."""
        q = (query_text or "").strip()
        if not q:
            return []
        stmt = (
            select(Entity)
            .where(
                Entity.workspace_id == workspace_id,
                Entity.name.ilike(f"%{q}%"),
            )
            .order_by(Entity.name.asc())
            .limit(max(1, limit))
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def documents_meta_by_ids(
        self,
        workspace_id: uuid.UUID,
        document_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, MetadataDocumentRow]:
        """Load document metadata for filter / title hydration (workspace-scoped)."""
        if not document_ids:
            return {}
        stmt = (
            select(Document, DocumentVersion)
            .outerjoin(
                DocumentVersion,
                DocumentVersion.id == Document.current_version_id,
            )
            .where(
                Document.workspace_id == workspace_id,
                Document.id.in_(document_ids),
            )
        )
        rows = (await self._session.execute(stmt)).all()
        out: dict[uuid.UUID, MetadataDocumentRow] = {}
        for doc, version in rows:
            out[doc.id] = MetadataDocumentRow(
                document_id=doc.id,
                workspace_id=doc.workspace_id,
                title=doc.title,
                file_type=doc.file_type,
                created_at=doc.created_at,
                updated_at=doc.updated_at,
                uploaded_by=version.uploaded_by if version else None,
                version_number=version.version_number if version else None,
                status=version.status.value if version else None,
            )
        return out
