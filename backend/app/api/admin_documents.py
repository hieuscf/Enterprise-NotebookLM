# =============================================================================
# File: admin_documents.py
# Module/Service: Document Ingestion Service / Admin Console (FR2, FR12)
# Layer: Presentation
# Purpose: Platform Manage endpoints for enterprise-wide document operations.
# Responsibilities:
#   - GET /admin/documents
#   - GET /admin/documents/{documentId}
#   - GET /admin/documents/{documentId}/versions
# Dependencies:
#   - require_platform_manage, AdminDocumentService, get_db_session
# Public Exports:
#   - router
# Database/Table: documents, document_versions, workspaces, pipeline_runs
# Related Modules: docs/Enterprise_notebooklm_openapi.yaml §Admin/Documents
# Important Notes:
#   - platform_role == manage only. Workspace Admin → 403.
#   - Does not expose storage credentials, content, or raw stack traces.
# =============================================================================

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.dependencies.auth import CurrentUser
from app.dependencies.rbac import require_platform_manage
from app.models.documents import DocumentVersion
from app.models.enums import DocumentVersionStatus, FileType
from app.models.pipeline import PipelineRun, PipelineStageLog
from app.repositories.admin_documents import (
    AdminDocumentRepository,
    AdminDocumentRow,
    filename_from_storage_path,
)
from app.repositories.pipeline import PipelineRepository
from app.schemas.admin_documents import (
    AdminDocumentDetailResponse,
    AdminDocumentListItem,
    AdminDocumentListResponse,
    AdminDocumentSummary,
)
from app.schemas.common import ErrorResponse
from app.schemas.documents import (
    DocumentVersionResponse,
    PipelineRunResponse,
    PipelineStageLogResponse,
)
from app.services.admin_documents import AdminDocumentError, AdminDocumentService

router = APIRouter(prefix="/admin/documents", tags=["Admin/Documents"])


def get_admin_document_service(
    session: AsyncSession = Depends(get_db_session),
) -> AdminDocumentService:
    return AdminDocumentService(
        AdminDocumentRepository(session),
        PipelineRepository(session),
    )


def _http_error(exc: AdminDocumentError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail=ErrorResponse(code=exc.code, message=exc.message).model_dump(),
    )


def _version_response(ver: DocumentVersion) -> DocumentVersionResponse:
    return DocumentVersionResponse(
        id=ver.id,
        document_id=ver.document_id,
        uploaded_by=ver.uploaded_by,
        version_number=ver.version_number,
        file_size_bytes=ver.file_size_bytes,
        checksum_sha256=ver.checksum_sha256,
        page_count=ver.page_count,
        status=ver.status.value,  # type: ignore[arg-type]
        is_current=ver.is_current,
        created_at=ver.created_at,
        preview_status=ver.preview_status.value,  # type: ignore[arg-type]
        preview_type=ver.preview_type.value if ver.preview_type else None,  # type: ignore[arg-type]
        preview_generated_at=ver.preview_generated_at,
    )


def _stage_response(log: PipelineStageLog) -> PipelineStageLogResponse:
    return PipelineStageLogResponse(
        id=log.id,
        stage=log.stage.value,  # type: ignore[arg-type]
        status=log.status.value,  # type: ignore[arg-type]
        duration_ms=log.duration_ms,
        metadata=log.metadata_,
        error_message=log.error_message,
    )


def _pipeline_response(run: PipelineRun) -> PipelineRunResponse:
    stages = getattr(run, "stages", []) or []
    return PipelineRunResponse(
        id=run.id,
        document_version_id=run.document_version_id,
        status=run.status.value,  # type: ignore[arg-type]
        retry_count=run.retry_count,
        error_message=run.error_message,
        stages=[_stage_response(s) for s in stages],
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


def _list_item(row: AdminDocumentRow) -> AdminDocumentListItem:
    ver = row.current_version
    return AdminDocumentListItem(
        id=row.document.id,
        title=row.document.title,
        filename=filename_from_storage_path(ver.storage_path if ver else None),
        workspace_id=row.document.workspace_id,
        workspace_name=row.workspace_name,
        file_type=row.document.file_type.value,  # type: ignore[arg-type]
        current_version_id=row.document.current_version_id,
        version_number=ver.version_number if ver else None,
        file_size_bytes=ver.file_size_bytes if ver else None,
        page_count=ver.page_count if ver else None,
        status=ver.status.value if ver else None,  # type: ignore[arg-type]
        created_at=row.document.created_at,
        updated_at=row.document.updated_at,
    )


@router.get(
    "",
    response_model=AdminDocumentListResponse,
    summary="List all enterprise documents (Manage)",
    operation_id="listAdminDocuments",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    },
)
async def list_admin_documents(
    _manage: CurrentUser = Depends(require_platform_manage),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    workspace_id: uuid.UUID | None = Query(
        None, description="Filter by workspace UUID"
    ),
    status_filter: DocumentVersionStatus | None = Query(
        None,
        alias="status",
        description="Filter by current DocumentVersion.status",
    ),
    file_type: FileType | None = Query(None),
    search: str | None = Query(
        None,
        max_length=200,
        description="Search title, filename (storage basename), or workspace name",
    ),
    sort: Literal["updated_at", "title", "size", "status", "name"] = Query(
        "updated_at"
    ),
    order: Literal["asc", "desc"] = Query("desc"),
    service: AdminDocumentService = Depends(get_admin_document_service),
) -> AdminDocumentListResponse:
    result = await service.list_documents(
        page=page,
        page_size=page_size,
        workspace_id=workspace_id,
        status=status_filter,
        file_type=file_type,
        search=search,
        sort=sort,
        order=order,
    )
    return AdminDocumentListResponse(
        items=[_list_item(row) for row in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
        summary=AdminDocumentSummary(
            total=result.summary.total,
            processing=result.summary.processing,
            ready=result.summary.ready,
            failed=result.summary.failed,
        ),
    )


@router.get(
    "/{documentId}",
    response_model=AdminDocumentDetailResponse,
    summary="Get enterprise document detail (Manage)",
    operation_id="getAdminDocument",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    },
)
async def get_admin_document(
    documentId: uuid.UUID = Path(..., description="Document UUID"),
    _manage: CurrentUser = Depends(require_platform_manage),
    service: AdminDocumentService = Depends(get_admin_document_service),
) -> AdminDocumentDetailResponse:
    try:
        detail = await service.get_document(documentId)
    except AdminDocumentError as exc:
        raise _http_error(exc) from exc

    row = detail.row
    return AdminDocumentDetailResponse(
        id=row.document.id,
        title=row.document.title,
        filename=detail.filename,
        workspace_id=row.document.workspace_id,
        workspace_name=row.workspace_name,
        file_type=row.document.file_type.value,  # type: ignore[arg-type]
        current_version_id=row.document.current_version_id,
        created_at=row.document.created_at,
        updated_at=row.document.updated_at,
        current_version=(
            _version_response(row.current_version) if row.current_version else None
        ),
        latest_pipeline_run=(
            _pipeline_response(detail.latest_pipeline_run)
            if detail.latest_pipeline_run
            else None
        ),
    )


@router.get(
    "/{documentId}/versions",
    response_model=list[DocumentVersionResponse],
    summary="List document versions across workspaces (Manage)",
    operation_id="listAdminDocumentVersions",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    },
)
async def list_admin_document_versions(
    documentId: uuid.UUID = Path(..., description="Document UUID"),
    _manage: CurrentUser = Depends(require_platform_manage),
    service: AdminDocumentService = Depends(get_admin_document_service),
) -> list[DocumentVersionResponse]:
    try:
        versions = await service.list_versions(documentId)
    except AdminDocumentError as exc:
        raise _http_error(exc) from exc
    return [_version_response(v) for v in versions]
