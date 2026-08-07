# =============================================================================
# File: documents.py
# Module/Service: Document Ingestion Service
# Layer: Repository
# Purpose: Data access for documents + document_versions (FR2).
# Responsibilities:
#   - CRUD documents scoped by workspace_id; version history; set-current
# Dependencies:
#   - SQLAlchemy AsyncSession, app.models.documents
# Public Exports:
#   - DocumentRepository
# Database/Table: documents, document_versions
# Related Modules: app.services.documents
# Important Notes: Always filter by workspace_id; versions own storage_path.
# =============================================================================

from __future__ import annotations

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.documents import Document, DocumentVersion
from app.models.enums import DocumentVersionStatus, FileType


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_document(
        self,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> Document | None:
        stmt = select(Document).where(
            Document.id == document_id,
            Document.workspace_id == workspace_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_document_by_id(self, document_id: uuid.UUID) -> Document | None:
        """Load document by id (Celery worker — workspace known from row)."""
        return await self._session.get(Document, document_id)

    async def list_documents(
        self,
        workspace_id: uuid.UUID,
        *,
        page: int,
        page_size: int,
        file_type: FileType | None = None,
    ) -> tuple[list[Document], int]:
        filters = [Document.workspace_id == workspace_id]
        if file_type is not None:
            filters.append(Document.file_type == file_type)

        count_stmt = select(func.count()).select_from(Document).where(*filters)
        total = int((await self._session.execute(count_stmt)).scalar_one())

        list_stmt = (
            select(Document)
            .where(*filters)
            .order_by(Document.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self._session.execute(list_stmt)).scalars().all()
        return list(rows), total

    async def create_document(
        self,
        *,
        workspace_id: uuid.UUID,
        title: str,
        file_type: FileType,
    ) -> Document:
        doc = Document(
            workspace_id=workspace_id,
            title=title,
            file_type=file_type,
            current_version_id=None,
        )
        self._session.add(doc)
        await self._session.flush()
        return doc

    async def delete_document(self, document: Document) -> None:
        await self._session.delete(document)
        await self._session.flush()

    async def set_current_version(
        self,
        document: Document,
        version: DocumentVersion,
    ) -> Document:
        await self._session.execute(
            update(DocumentVersion)
            .where(
                DocumentVersion.document_id == document.id,
                DocumentVersion.is_current.is_(True),
            )
            .values(is_current=False)
        )
        version.is_current = True
        document.current_version_id = version.id
        await self._session.flush()
        return document

    async def get_version(
        self,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> DocumentVersion | None:
        stmt = (
            select(DocumentVersion)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(
                DocumentVersion.id == version_id,
                DocumentVersion.document_id == document_id,
                Document.workspace_id == workspace_id,
            )
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_versions(
        self,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> list[DocumentVersion]:
        stmt = (
            select(DocumentVersion)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(
                DocumentVersion.document_id == document_id,
                Document.workspace_id == workspace_id,
            )
            .order_by(DocumentVersion.version_number.desc())
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def clear_current_flags(self, document_id: uuid.UUID) -> None:
        """Set is_current=false for all versions of a document."""
        await self._session.execute(
            update(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .values(is_current=False)
        )

    async def next_version_number(self, document_id: uuid.UUID) -> int:
        stmt = select(func.coalesce(func.max(DocumentVersion.version_number), 0)).where(
            DocumentVersion.document_id == document_id
        )
        current = int((await self._session.execute(stmt)).scalar_one())
        return current + 1

    async def create_version(
        self,
        *,
        document_id: uuid.UUID,
        uploaded_by: uuid.UUID,
        version_number: int,
        storage_path: str,
        file_size_bytes: int,
        checksum_sha256: str,
        is_current: bool,
        status: DocumentVersionStatus = DocumentVersionStatus.processing,
    ) -> DocumentVersion:
        version = DocumentVersion(
            document_id=document_id,
            uploaded_by=uploaded_by,
            version_number=version_number,
            storage_path=storage_path,
            file_size_bytes=file_size_bytes,
            checksum_sha256=checksum_sha256,
            status=status,
            is_current=is_current,
        )
        self._session.add(version)
        await self._session.flush()
        return version
