# =============================================================================
# File: documents.py
# Module/Service: Document Ingestion Service
# Layer: Presentation
# Purpose: FastAPI routes for Knowledge Base upload/versioning (FR2 / UC2).
# Responsibilities:
#   - GET/POST /workspaces/{id}/documents; GET/DELETE document
#   - Versions list/upload/set-current; pipeline-status
# Dependencies:
#   - require_workspace_*_rl, DocumentIngestionService, MinioStorageAdapter
# Public Exports:
#   - router
# Database/Table: documents, document_versions, pipeline_runs, pipeline_stage_logs
# Related Modules: docs/Enterprise_notebooklm_openapi.yaml (/workspaces/*/documents*)
# Important Notes: Upload returns 202 DocumentVersion; editor+ for mutate.
# =============================================================================

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.minio_storage import MinioStorageAdapter, get_minio_storage
from app.db.session import get_db_session
from app.dependencies.rate_limit import (
    require_workspace_admin_rl,
    require_workspace_editor_rl,
    require_workspace_member_rl,
)
from app.dependencies.rbac import WorkspaceAccess
from app.models.documents import Document, DocumentVersion
from app.models.enums import FileType
from app.models.pipeline import PipelineRun, PipelineStageLog
from app.schemas.common import ErrorResponse
from app.schemas.documents import (
    DocumentChunkListResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentVersionResponse,
    PipelineRunResponse,
    PipelineStageLogResponse,
)
from app.services.documents import (
    DocumentIngestionError,
    DocumentIngestionService,
    iter_upload_file,
)

router = APIRouter(prefix="/workspaces", tags=["Documents"])


def get_document_service(
    session: AsyncSession = Depends(get_db_session),
    storage: MinioStorageAdapter = Depends(get_minio_storage),
) -> DocumentIngestionService:
    return DocumentIngestionService(session, storage)


def _doc_response(doc: Document) -> DocumentResponse:
    return DocumentResponse(
        id=doc.id,
        workspace_id=doc.workspace_id,
        title=doc.title,
        file_type=doc.file_type.value,  # type: ignore[arg-type]
        current_version_id=doc.current_version_id,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
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


def _http_error(exc: DocumentIngestionError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail=ErrorResponse(code=exc.code, message=exc.message).model_dump(),
    )


@router.get(
    "/{workspaceId}/documents",
    response_model=DocumentListResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def list_documents(
    workspaceId: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    file_type: FileType | None = Query(None),
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    service: DocumentIngestionService = Depends(get_document_service),
) -> DocumentListResponse:
    del workspaceId
    result = await service.list_documents(
        access.workspace_id,
        page=page,
        page_size=page_size,
        file_type=file_type,
    )
    return DocumentListResponse(
        items=[_doc_response(d) for d in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@router.post(
    "/{workspaceId}/documents",
    response_model=DocumentVersionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def upload_document(
    workspaceId: uuid.UUID,
    title: str = Form(...),
    file: UploadFile = File(...),
    access: WorkspaceAccess = Depends(require_workspace_editor_rl),
    service: DocumentIngestionService = Depends(get_document_service),
) -> DocumentVersionResponse:
    """Upload tài liệu mới — admin | editor (viewer → 403)."""
    del workspaceId
    try:
        result = await service.upload_new(
            workspace_id=access.workspace_id,
            uploaded_by=access.user_id,
            title=title,
            filename=file.filename or "upload.bin",
            file_chunks=iter_upload_file(file),
        )
    except DocumentIngestionError as exc:
        raise _http_error(exc) from exc
    return _version_response(result.version)


@router.get(
    "/{workspaceId}/documents/{documentId}",
    response_model=DocumentResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def get_document(
    workspaceId: uuid.UUID,
    documentId: uuid.UUID,
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    service: DocumentIngestionService = Depends(get_document_service),
) -> DocumentResponse:
    del workspaceId
    try:
        doc = await service.get_document(access.workspace_id, documentId)
    except DocumentIngestionError as exc:
        raise _http_error(exc) from exc
    return _doc_response(doc)


@router.get(
    "/{workspaceId}/documents/{documentId}/chunks",
    response_model=DocumentChunkListResponse,
    summary="Danh sách chunk của bản hiện hành (Document Viewer / deep-link)",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def list_document_chunks(
    workspaceId: uuid.UUID,
    documentId: uuid.UUID,
    versionId: uuid.UUID | None = Query(
        None,
        description="Optional version override; default = current_version_id",
    ),
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    service: DocumentIngestionService = Depends(get_document_service),
) -> DocumentChunkListResponse:
    """Return chunks for viewer navigation — no retrieval / no LLM."""
    del workspaceId
    try:
        return await service.list_document_chunks(
            access.workspace_id,
            documentId,
            version_id=versionId,
        )
    except DocumentIngestionError as exc:
        raise _http_error(exc) from exc


@router.get(
    "/{workspaceId}/documents/{documentId}/content",
    summary="Stream original file (or preview PDF) for Document Viewer",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
        status.HTTP_502_BAD_GATEWAY: {"model": ErrorResponse},
    },
)
async def get_document_content(
    workspaceId: uuid.UUID,
    documentId: uuid.UUID,
    versionId: uuid.UUID | None = Query(None),
    download: bool = Query(
        False,
        description="If true, Content-Disposition=attachment (Download Original).",
    ),
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    service: DocumentIngestionService = Depends(get_document_service),
) -> Response:
    """Serve original representation bytes — never markdown."""
    del workspaceId
    try:
        payload = await service.get_document_content(
            access.workspace_id,
            documentId,
            version_id=versionId,
            # Download Original must return the uploaded file (e.g. DOCX), not preview PDF.
            prefer_preview_pdf=not download,
        )
    except DocumentIngestionError as exc:
        raise _http_error(exc) from exc

    disposition = "attachment" if download else "inline"
    headers = {
        "Content-Disposition": f'{disposition}; filename="{payload.filename}"',
        "X-Viewer-Kind": payload.viewer_kind,
        "Cache-Control": "private, max-age=60",
    }
    return Response(
        content=payload.data,
        media_type=payload.content_type,
        headers=headers,
    )


@router.delete(
    "/{workspaceId}/documents/{documentId}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def delete_document(
    workspaceId: uuid.UUID,
    documentId: uuid.UUID,
    access: WorkspaceAccess = Depends(require_workspace_admin_rl),
    service: DocumentIngestionService = Depends(get_document_service),
) -> None:
    """Xoá tài liệu — admin only (destructive across all versions)."""
    del workspaceId
    try:
        await service.delete_document(access.workspace_id, documentId)
    except DocumentIngestionError as exc:
        raise _http_error(exc) from exc


@router.get(
    "/{workspaceId}/documents/{documentId}/versions",
    response_model=list[DocumentVersionResponse],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def list_versions(
    workspaceId: uuid.UUID,
    documentId: uuid.UUID,
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    service: DocumentIngestionService = Depends(get_document_service),
) -> list[DocumentVersionResponse]:
    del workspaceId
    try:
        versions = await service.list_versions(access.workspace_id, documentId)
    except DocumentIngestionError as exc:
        raise _http_error(exc) from exc
    return [_version_response(v) for v in versions]


@router.post(
    "/{workspaceId}/documents/{documentId}/versions",
    response_model=DocumentVersionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def upload_new_version(
    workspaceId: uuid.UUID,
    documentId: uuid.UUID,
    file: UploadFile = File(...),
    access: WorkspaceAccess = Depends(require_workspace_editor_rl),
    service: DocumentIngestionService = Depends(get_document_service),
) -> DocumentVersionResponse:
    """Upload lại → version mới — admin | editor."""
    del workspaceId
    try:
        result = await service.upload_new_version(
            workspace_id=access.workspace_id,
            document_id=documentId,
            uploaded_by=access.user_id,
            filename=file.filename or "upload.bin",
            file_chunks=iter_upload_file(file),
        )
    except DocumentIngestionError as exc:
        raise _http_error(exc) from exc
    return _version_response(result.version)


@router.get(
    "/{workspaceId}/documents/{documentId}/versions/{versionId}",
    response_model=DocumentVersionResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def get_version(
    workspaceId: uuid.UUID,
    documentId: uuid.UUID,
    versionId: uuid.UUID,
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    service: DocumentIngestionService = Depends(get_document_service),
) -> DocumentVersionResponse:
    del workspaceId
    try:
        version = await service.get_version(access.workspace_id, documentId, versionId)
    except DocumentIngestionError as exc:
        raise _http_error(exc) from exc
    return _version_response(version)


@router.post(
    "/{workspaceId}/documents/{documentId}/versions/{versionId}/set-current",
    response_model=DocumentResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def set_current_version(
    workspaceId: uuid.UUID,
    documentId: uuid.UUID,
    versionId: uuid.UUID,
    access: WorkspaceAccess = Depends(require_workspace_editor_rl),
    service: DocumentIngestionService = Depends(get_document_service),
) -> DocumentResponse:
    del workspaceId
    try:
        doc = await service.set_current_version(
            workspace_id=access.workspace_id,
            document_id=documentId,
            version_id=versionId,
        )
    except DocumentIngestionError as exc:
        raise _http_error(exc) from exc
    return _doc_response(doc)


@router.get(
    "/{workspaceId}/documents/{documentId}/versions/{versionId}/pipeline-status",
    response_model=PipelineRunResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def get_pipeline_status(
    workspaceId: uuid.UUID,
    documentId: uuid.UUID,
    versionId: uuid.UUID,
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    service: DocumentIngestionService = Depends(get_document_service),
) -> PipelineRunResponse:
    del workspaceId
    try:
        run = await service.get_pipeline_status(
            workspace_id=access.workspace_id,
            document_id=documentId,
            version_id=versionId,
        )
    except DocumentIngestionError as exc:
        raise _http_error(exc) from exc
    return _pipeline_response(run)
