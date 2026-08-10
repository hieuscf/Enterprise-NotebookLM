# =============================================================================
# File: admin_documents.py
# Module/Service: Document Ingestion Service / Admin Console (FR2, FR12)
# Layer: Service
# Purpose: Platform Manage business orchestration for global document visibility.
# Responsibilities:
#   - List/detail/versions with enriched workspace + current version metadata
#   - Attach latest pipeline_run (+ stages) for diagnostic detail
# Dependencies:
#   - AdminDocumentRepository, PipelineRepository
# Public Exports:
#   - AdminDocumentService, AdminDocumentError
# Database/Table: documents, document_versions, workspaces, pipeline_runs
# Related Modules: app.api.admin_documents
# Important Notes: Authorization is enforced at the router (require_platform_manage).
# =============================================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.models.documents import DocumentVersion
from app.models.enums import DocumentVersionStatus, FileType
from app.models.pipeline import PipelineRun
from app.repositories.admin_documents import (
    AdminDocumentRepository,
    AdminDocumentRow,
    AdminDocumentSummaryCounts,
    SortField,
    SortOrder,
    filename_from_storage_path,
)
from app.repositories.pipeline import PipelineRepository


class AdminDocumentError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class AdminDocumentListResult:
    items: list[AdminDocumentRow]
    page: int
    page_size: int
    total: int
    summary: AdminDocumentSummaryCounts


@dataclass(frozen=True, slots=True)
class AdminDocumentDetailResult:
    row: AdminDocumentRow
    filename: str | None
    latest_pipeline_run: PipelineRun | None


class AdminDocumentService:
    def __init__(
        self,
        documents: AdminDocumentRepository,
        pipeline: PipelineRepository,
    ) -> None:
        self._documents = documents
        self._pipeline = pipeline

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
    ) -> AdminDocumentListResult:
        cleaned_search = search.strip() if search and search.strip() else None
        items, total = await self._documents.list_documents(
            page=page,
            page_size=page_size,
            workspace_id=workspace_id,
            status=status,
            file_type=file_type,
            search=cleaned_search,
            sort=sort,
            order=order,
        )
        summary = await self._documents.summarize(
            workspace_id=workspace_id,
            file_type=file_type,
            search=cleaned_search,
        )
        return AdminDocumentListResult(
            items=items,
            page=page,
            page_size=page_size,
            total=total,
            summary=summary,
        )

    async def get_document(self, document_id: uuid.UUID) -> AdminDocumentDetailResult:
        row = await self._documents.get_document(document_id)
        if row is None:
            raise AdminDocumentError(
                "not_found",
                "Document not found.",
                status_code=404,
            )
        filename = filename_from_storage_path(
            row.current_version.storage_path if row.current_version else None
        )
        pipeline_run: PipelineRun | None = None
        if row.current_version is not None:
            pipeline_run = await self._pipeline.get_latest_run_with_stages(
                row.current_version.id
            )
        return AdminDocumentDetailResult(
            row=row,
            filename=filename,
            latest_pipeline_run=pipeline_run,
        )

    async def list_versions(self, document_id: uuid.UUID) -> list[DocumentVersion]:
        row = await self._documents.get_document(document_id)
        if row is None:
            raise AdminDocumentError(
                "not_found",
                "Document not found.",
                status_code=404,
            )
        return await self._documents.list_versions(document_id)
