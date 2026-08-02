# =============================================================================
# File: metadata_query.py
# Module/Service: Query Router — Metadata Branch (FR11)
# Layer: Repository
# Purpose: Postgres MetadataRepository implementation (whitelist methods only).
# Responsibilities:
#   - count/list/latest/oldest documents; chunks/pages; members; owner
# Dependencies:
#   - SQLAlchemy AsyncSession, Document / DocumentChunk / DocumentVersion models
# Public Exports:
#   - PostgresMetadataRepository
# Database/Table: documents, document_versions, document_chunks, workspace_members
# Related Modules: query_router.interfaces.metadata_repository
# Important Notes: Always filter by workspace_id; no dynamic SQL from user text.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.documents import Document, DocumentVersion
from app.models.enums import FileType
from app.models.knowledge import DocumentChunk
from app.repositories.workspace_members import WorkspaceMemberRepository
from app.services.query_router.interfaces.metadata_repository import MetadataDocumentInfo


class PostgresMetadataRepository:
    """Async SQLAlchemy implementation of ``MetadataRepository``."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        member_repo: WorkspaceMemberRepository | None = None,
    ) -> None:
        self._session = session
        self._members = member_repo or WorkspaceMemberRepository(session)

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

    async def count_files(
        self,
        workspace_id: uuid.UUID,
        *,
        file_type: FileType | None = None,
    ) -> int:
        return await self.count_documents(workspace_id, file_type=file_type)

    async def count_pdf(self, workspace_id: uuid.UUID) -> int:
        return await self.count_documents(workspace_id, file_type=FileType.pdf)

    async def list_documents(
        self,
        workspace_id: uuid.UUID,
        *,
        file_type: FileType | None = None,
        limit: int = 50,
    ) -> list[MetadataDocumentInfo]:
        return await self._list(
            workspace_id,
            file_type=file_type,
            limit=limit,
            order=desc(Document.created_at),
        )

    async def latest_documents(
        self,
        workspace_id: uuid.UUID,
        *,
        limit: int = 10,
    ) -> list[MetadataDocumentInfo]:
        return await self._list(
            workspace_id,
            limit=limit,
            order=desc(Document.created_at),
        )

    async def oldest_documents(
        self,
        workspace_id: uuid.UUID,
        *,
        limit: int = 10,
    ) -> list[MetadataDocumentInfo]:
        return await self._list(
            workspace_id,
            limit=limit,
            order=asc(Document.created_at),
        )

    async def count_chunks(self, workspace_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(DocumentChunk)
            .join(DocumentVersion, DocumentVersion.id == DocumentChunk.document_version_id)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(Document.workspace_id == workspace_id)
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def count_pages(self, workspace_id: uuid.UUID) -> int:
        stmt = (
            select(func.count(func.distinct(DocumentChunk.page_number)))
            .select_from(DocumentChunk)
            .join(DocumentVersion, DocumentVersion.id == DocumentChunk.document_version_id)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(
                Document.workspace_id == workspace_id,
                DocumentChunk.page_number.is_not(None),
            )
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def count_members(self, workspace_id: uuid.UUID) -> int:
        return int(await self._members.count_active_members(workspace_id))

    async def stats_by_file_type(self, workspace_id: uuid.UUID) -> dict[str, int]:
        stmt = (
            select(Document.file_type, func.count())
            .where(Document.workspace_id == workspace_id)
            .group_by(Document.file_type)
        )
        rows = (await self._session.execute(stmt)).all()
        return {str(ft.value if hasattr(ft, "value") else ft): int(cnt) for ft, cnt in rows}

    async def document_owner(
        self,
        workspace_id: uuid.UUID,
        *,
        document_id: uuid.UUID | None = None,
    ) -> MetadataDocumentInfo | None:
        filters = [Document.workspace_id == workspace_id]
        if document_id is not None:
            filters.append(Document.id == document_id)
        stmt = (
            select(Document, DocumentVersion)
            .outerjoin(DocumentVersion, DocumentVersion.id == Document.current_version_id)
            .where(*filters)
            .order_by(desc(Document.created_at))
            .limit(1)
        )
        row = (await self._session.execute(stmt)).first()
        if row is None:
            return None
        doc, version = row
        return MetadataDocumentInfo(
            document_id=doc.id,
            title=doc.title,
            file_type=doc.file_type.value,
            created_at=doc.created_at,
            uploaded_by=version.uploaded_by if version else None,
        )

    async def _list(
        self,
        workspace_id: uuid.UUID,
        *,
        file_type: FileType | None = None,
        limit: int = 50,
        order: object,
    ) -> list[MetadataDocumentInfo]:
        filters = [Document.workspace_id == workspace_id]
        if file_type is not None:
            filters.append(Document.file_type == file_type)
        stmt = (
            select(Document, DocumentVersion)
            .outerjoin(DocumentVersion, DocumentVersion.id == Document.current_version_id)
            .where(*filters)
            .order_by(order)  # type: ignore[arg-type]
            .limit(max(1, limit))
        )
        rows = (await self._session.execute(stmt)).all()
        out: list[MetadataDocumentInfo] = []
        for doc, version in rows:
            created: datetime | None = doc.created_at
            out.append(
                MetadataDocumentInfo(
                    document_id=doc.id,
                    title=doc.title,
                    file_type=doc.file_type.value,
                    created_at=created,
                    uploaded_by=version.uploaded_by if version else None,
                )
            )
        return out
