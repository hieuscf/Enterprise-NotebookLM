# =============================================================================
# File: admin_documents.py
# Module/Service: Document Ingestion Service / Admin Console (FR2, FR12)
# Layer: Repository
# Purpose: Cross-workspace document queries for Platform Manage only.
# Responsibilities:
#   - Paginated global list with search/filter/sort + status summary
#   - Load document + workspace + current version by document id
#   - List versions without workspace membership gate
# Dependencies:
#   - SQLAlchemy AsyncSession, Document/DocumentVersion/Workspace models
# Public Exports:
#   - AdminDocumentRepository, AdminDocumentRow, AdminDocumentSummaryCounts
# Database/Table: documents, document_versions, workspaces
# Related Modules: app.services.admin_documents
# Important Notes:
#   - Intentionally omits workspace_id membership filter — caller must be Manage.
#   - Excludes soft-deleted workspaces (deleted_at IS NOT NULL).
# =============================================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.documents import Document, DocumentVersion
from app.models.enums import DocumentVersionStatus, FileType
from app.models.identity import Workspace

SortField = Literal["updated_at", "title", "size", "status", "name"]
SortOrder = Literal["asc", "desc"]


@dataclass(frozen=True, slots=True)
class AdminDocumentRow:
    document: Document
    workspace_name: str
    current_version: DocumentVersion | None


@dataclass(frozen=True, slots=True)
class AdminDocumentSummaryCounts:
    total: int
    processing: int
    ready: int
    failed: int


def filename_from_storage_path(storage_path: str | None) -> str | None:
    """Return basename of MinIO key; never the full path."""
    if not storage_path:
        return None
    name = storage_path.rsplit("/", 1)[-1].strip()
    return name or None


class AdminDocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _base_join(self) -> tuple[type[DocumentVersion], Select]:
        """documents ⋈ workspaces ⋈ current version (outer)."""
        current_version = aliased(DocumentVersion, name="current_version")
        stmt: Select = (
            select(Document, Workspace.name, current_version)
            .join(Workspace, Workspace.id == Document.workspace_id)
            .outerjoin(
                current_version,
                current_version.id == Document.current_version_id,
            )
            .where(Workspace.deleted_at.is_(None))
        )
        return current_version, stmt

    def _apply_filters(
        self,
        stmt: Select,
        current_version: type[DocumentVersion],
        *,
        workspace_id: uuid.UUID | None,
        status: DocumentVersionStatus | None,
        file_type: FileType | None,
        search: str | None,
        include_status_filter: bool = True,
    ) -> Select:
        if workspace_id is not None:
            stmt = stmt.where(Document.workspace_id == workspace_id)
        if file_type is not None:
            stmt = stmt.where(Document.file_type == file_type)
        if include_status_filter and status is not None:
            stmt = stmt.where(current_version.status == status)
        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    Document.title.ilike(pattern),
                    current_version.storage_path.ilike(pattern),
                    Workspace.name.ilike(pattern),
                )
            )
        return stmt

    def _apply_sort(
        self,
        stmt: Select,
        current_version: type[DocumentVersion],
        *,
        sort: SortField,
        order: SortOrder,
    ) -> Select:
        if sort in ("title", "name"):
            col = Document.title
        elif sort == "size":
            col = current_version.file_size_bytes
        elif sort == "status":
            col = current_version.status
        else:
            col = Document.updated_at

        ordered = col.asc() if order == "asc" else col.desc()
        # Stable tie-breaker
        return stmt.order_by(ordered.nullslast(), Document.id.desc())

    async def list_documents(
        self,
        *,
        page: int,
        page_size: int,
        workspace_id: uuid.UUID | None = None,
        status: DocumentVersionStatus | None = None,
        file_type: FileType | None = None,
        search: str | None = None,
        sort: SortField = "updated_at",
        order: SortOrder = "desc",
    ) -> tuple[list[AdminDocumentRow], int]:
        page = max(1, page)
        page_size = min(100, max(1, page_size))

        current_version, stmt = self._base_join()
        stmt = self._apply_filters(
            stmt,
            current_version,
            workspace_id=workspace_id,
            status=status,
            file_type=file_type,
            search=search,
        )

        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = int((await self._session.execute(count_stmt)).scalar_one())

        list_stmt = self._apply_sort(
            stmt, current_version, sort=sort, order=order
        ).offset((page - 1) * page_size).limit(page_size)

        rows = (await self._session.execute(list_stmt)).all()
        items = [
            AdminDocumentRow(
                document=doc,
                workspace_name=ws_name,
                current_version=ver,
            )
            for doc, ws_name, ver in rows
        ]
        return items, total

    async def summarize(
        self,
        *,
        workspace_id: uuid.UUID | None = None,
        file_type: FileType | None = None,
        search: str | None = None,
    ) -> AdminDocumentSummaryCounts:
        """Counts by current version status; ignores status filter so UI can show breakdown."""
        current_version, stmt = self._base_join()
        stmt = self._apply_filters(
            stmt,
            current_version,
            workspace_id=workspace_id,
            status=None,
            file_type=file_type,
            search=search,
            include_status_filter=False,
        )
        subq = stmt.with_only_columns(
            Document.id.label("doc_id"),
            current_version.status.label("ver_status"),
        ).order_by(None).subquery()

        agg_stmt = select(
            func.count().label("total"),
            func.coalesce(
                func.sum(
                    case(
                        (subq.c.ver_status == DocumentVersionStatus.processing, 1),
                        else_=0,
                    )
                ),
                0,
            ).label("processing"),
            func.coalesce(
                func.sum(
                    case(
                        (subq.c.ver_status == DocumentVersionStatus.ready, 1),
                        else_=0,
                    )
                ),
                0,
            ).label("ready"),
            func.coalesce(
                func.sum(
                    case(
                        (subq.c.ver_status == DocumentVersionStatus.failed, 1),
                        else_=0,
                    )
                ),
                0,
            ).label("failed"),
        ).select_from(subq)

        row = (await self._session.execute(agg_stmt)).one()
        return AdminDocumentSummaryCounts(
            total=int(row.total),
            processing=int(row.processing),
            ready=int(row.ready),
            failed=int(row.failed),
        )

    async def get_document(self, document_id: uuid.UUID) -> AdminDocumentRow | None:
        current_version, stmt = self._base_join()
        stmt = stmt.where(Document.id == document_id)
        row = (await self._session.execute(stmt)).one_or_none()
        if row is None:
            return None
        doc, ws_name, ver = row
        return AdminDocumentRow(
            document=doc,
            workspace_name=ws_name,
            current_version=ver,
        )

    async def list_versions(self, document_id: uuid.UUID) -> list[DocumentVersion]:
        stmt = (
            select(DocumentVersion)
            .join(Document, Document.id == DocumentVersion.document_id)
            .join(Workspace, Workspace.id == Document.workspace_id)
            .where(
                DocumentVersion.document_id == document_id,
                Workspace.deleted_at.is_(None),
            )
            .order_by(DocumentVersion.version_number.desc())
        )
        return list((await self._session.execute(stmt)).scalars().all())
