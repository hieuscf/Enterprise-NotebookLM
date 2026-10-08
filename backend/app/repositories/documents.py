# =============================================================================
# File: documents.py
# Module/Service: Document Ingestion Service
# Layer: Repository
# Purpose: Data access for documents + document_versions (FR2).
# Responsibilities:
#   - CRUD documents scoped by workspace_id; version history; set-current
#   - Workspace version catalog, classification labels, edit-history events
# Dependencies:
#   - SQLAlchemy AsyncSession, app.models.documents, app.models.identity
# Public Exports:
#   - DocumentRepository
# Database/Table: documents, document_versions, document_version_events
# Related Modules: app.services.documents
# Important Notes: Always filter by workspace_id; versions own storage_path.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import String, cast, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.documents import Document, DocumentVersion, DocumentVersionEvent
from app.models.enums import AiAnalysisStatus, DocumentVersionStatus, FileType
from app.models.identity import User


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
        query: str | None = None,
    ) -> tuple[list[Document], int]:
        filters = [Document.workspace_id == workspace_id]
        if file_type is not None:
            filters.append(Document.file_type == file_type)
        if query:
            filters.append(Document.title.ilike(f"%{query}%"))

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
        # Set updated_at in Python. Column.onupdate=func.now() expires the
        # attribute after flush; sync access in _doc_response then lazy-loads
        # and raises MissingGreenlet (HTTP 500 on rollback / set-current).
        document.updated_at = datetime.now(UTC)
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

    async def get_version_by_id(self, version_id: uuid.UUID) -> DocumentVersion | None:
        """Load a version by primary key (citation locator batching)."""
        return await self._session.get(DocumentVersion, version_id)

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
        status: DocumentVersionStatus = DocumentVersionStatus.ready,
        ai_analysis_status: AiAnalysisStatus = AiAnalysisStatus.not_analyzed,
    ) -> DocumentVersion:
        version = DocumentVersion(
            document_id=document_id,
            uploaded_by=uploaded_by,
            version_number=version_number,
            storage_path=storage_path,
            file_size_bytes=file_size_bytes,
            checksum_sha256=checksum_sha256,
            status=status,
            ai_analysis_status=ai_analysis_status,
            is_current=is_current,
        )
        self._session.add(version)
        await self._session.flush()
        return version

    async def count_analyzed_versions(self, workspace_id: uuid.UUID) -> int:
        """Count versions in this workspace whose AI analysis is READY."""
        stmt = (
            select(func.count())
            .select_from(DocumentVersion)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(
                Document.workspace_id == workspace_id,
                DocumentVersion.ai_analysis_status == AiAnalysisStatus.ready,
            )
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def add_version_event(
        self,
        *,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        document_version_id: uuid.UUID,
        actor_id: uuid.UUID,
        event_type: str,
        summary: str,
        payload: dict | None = None,
    ) -> DocumentVersionEvent:
        event = DocumentVersionEvent(
            workspace_id=workspace_id,
            document_id=document_id,
            document_version_id=document_version_id,
            actor_id=actor_id,
            event_type=event_type,
            summary=summary,
            payload=payload,
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def apply_version_labels(
        self,
        version: DocumentVersion,
        *,
        tags: list[str] | None = None,
        classification_metadata: dict | None = None,
        change_note: str | None = None,
        update_note: bool = False,
    ) -> DocumentVersion:
        if tags is not None:
            version.tags = tags
        if classification_metadata is not None:
            version.classification_metadata = classification_metadata
        if update_note:
            version.change_note = change_note
        await self._session.flush()
        return version

    def _catalog_filters(
        self,
        workspace_id: uuid.UUID,
        *,
        document_id: uuid.UUID | None,
        tag: str | None,
        query: str | None,
    ) -> list:
        filters: list = [Document.workspace_id == workspace_id]
        if document_id is not None:
            filters.append(Document.id == document_id)
        if tag:
            filters.append(DocumentVersion.tags.contains([tag]))
        if query:
            like = f"%{query}%"
            filters.append(
                or_(
                    Document.title.ilike(like),
                    DocumentVersion.change_note.ilike(like),
                    cast(DocumentVersion.tags, String).ilike(like),
                )
            )
        return filters

    async def list_workspace_versions(
        self,
        workspace_id: uuid.UUID,
        *,
        page: int,
        page_size: int,
        document_id: uuid.UUID | None = None,
        tag: str | None = None,
        query: str | None = None,
    ) -> tuple[list[tuple[DocumentVersion, Document, str | None, str | None]], int]:
        filters = self._catalog_filters(
            workspace_id,
            document_id=document_id,
            tag=tag,
            query=query,
        )
        count_stmt = (
            select(func.count())
            .select_from(DocumentVersion)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(*filters)
        )
        total = int((await self._session.execute(count_stmt)).scalar_one())
        list_stmt = (
            select(DocumentVersion, Document, User.full_name, User.email)
            .join(Document, Document.id == DocumentVersion.document_id)
            .outerjoin(User, User.id == DocumentVersion.uploaded_by)
            .where(*filters)
            .order_by(DocumentVersion.created_at.desc(), DocumentVersion.version_number.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self._session.execute(list_stmt)).all()
        return [(row[0], row[1], row[2], row[3]) for row in rows], total

    async def list_workspace_tags(self, workspace_id: uuid.UUID) -> list[str]:
        stmt = (
            select(DocumentVersion.tags)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(Document.workspace_id == workspace_id)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        found: set[str] = set()
        for raw in rows:
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, str) and item.strip():
                        found.add(item)
        return sorted(found, key=str.casefold)

    async def list_version_events(
        self,
        workspace_id: uuid.UUID,
        *,
        page: int,
        page_size: int,
        document_id: uuid.UUID | None = None,
        query: str | None = None,
    ) -> tuple[list[tuple[DocumentVersionEvent, str, int, str | None]], int]:
        filters = [
            DocumentVersionEvent.workspace_id == workspace_id,
            Document.workspace_id == workspace_id,
        ]
        if document_id is not None:
            filters.append(DocumentVersionEvent.document_id == document_id)
        if query:
            like = f"%{query}%"
            filters.append(
                or_(
                    DocumentVersionEvent.summary.ilike(like),
                    Document.title.ilike(like),
                )
            )
        total = int(
            (
                await self._session.execute(
                    select(func.count())
                    .select_from(DocumentVersionEvent)
                    .join(Document, Document.id == DocumentVersionEvent.document_id)
                    .where(*filters)
                )
            ).scalar_one()
        )
        list_stmt = (
            select(
                DocumentVersionEvent,
                Document.title,
                DocumentVersion.version_number,
                User.full_name,
            )
            .join(Document, Document.id == DocumentVersionEvent.document_id)
            .join(
                DocumentVersion,
                DocumentVersion.id == DocumentVersionEvent.document_version_id,
            )
            .outerjoin(User, User.id == DocumentVersionEvent.actor_id)
            .where(*filters)
            .order_by(DocumentVersionEvent.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self._session.execute(list_stmt)).all()
        return [(row[0], row[1], row[2], row[3]) for row in rows], total
