# =============================================================================
# File: documents.py
# Module/Service: Document Ingestion Service
# Layer: Presentation
# Purpose: FastAPI routes for Knowledge Base upload/versioning (FR2 / UC2).
# Responsibilities:
#   - GET/POST /workspaces/{id}/documents; GET/DELETE document
#   - Versions list/upload/set-current/rollback; classification; edit history
# Dependencies:
#   - require_workspace_*_rl, DocumentIngestionService, MinioStorageAdapter
# Public Exports:
#   - router
# Database/Table: documents, document_versions, pipeline_runs, pipeline_stage_logs
# Related Modules: docs/Enterprise_notebooklm_openapi.yaml (/workspaces/*/documents*)
# Important Notes: Upload returns 202 DocumentVersion; editor+ for mutate.
# =============================================================================

from __future__ import annotations

import re
import uuid
from urllib.parse import quote

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
from app.schemas.canonical import CanonicalDocumentResponse
from app.schemas.common import ErrorResponse
from app.integrations.ai.exceptions import AIGatewayError
from app.schemas.analysis import DocumentAnalysisResponse
from app.schemas.documents import (
    DocumentChunkListResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentVersionResponse,
    PipelineRunResponse,
    PipelineStageLogResponse,
    VersionCatalogItemResponse,
    VersionCatalogResponse,
    VersionClassificationUpdate,
    VersionEventListResponse,
    VersionEventResponse,
)
from app.services.analysis import AnalysisService, AnalysisServiceError
from app.services.documents import (
    DocumentIngestionError,
    DocumentIngestionService,
    iter_upload_file,
)
from app.services.versioning import UNSET, VersioningService

router = APIRouter(prefix="/workspaces", tags=["Documents"])


def get_document_service(
    session: AsyncSession = Depends(get_db_session),
    storage: MinioStorageAdapter = Depends(get_minio_storage),
) -> DocumentIngestionService:
    return DocumentIngestionService(session, storage)


def get_analysis_service(
    session: AsyncSession = Depends(get_db_session),
) -> AnalysisService:
    return AnalysisService(session)


def get_versioning_service(
    session: AsyncSession = Depends(get_db_session),
) -> VersioningService:
    return VersioningService(session)


def _string_map(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): item
        for key, item in value.items()
        if isinstance(item, str)
    }


def _tag_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _content_disposition(disposition: str, filename: str) -> str:
    """RFC 6266 header. Raw Unicode in header values raises HTTP 500 (latin-1)."""
    cleaned = (
        filename.replace("\r", "")
        .replace("\n", "")
        .replace('"', "")
        .replace("\\", "_")
        .replace("/", "-")
    )
    ascii_name = cleaned.encode("ascii", "replace").decode("ascii").replace("?", "_")
    stem, dot, ext = ascii_name.rpartition(".")
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._") or "document"
    ext = re.sub(r"[^A-Za-z0-9]+", "", ext)
    ascii_name = f"{stem}.{ext}" if dot and ext else stem
    encoded = quote(cleaned, safe="")
    return f"{disposition}; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"


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
        ai_analysis_status=ver.ai_analysis_status.value,  # type: ignore[arg-type]
        analyzed_at=ver.analyzed_at,
        analysis_error=ver.analysis_error,
        is_current=ver.is_current,
        created_at=ver.created_at,
        change_note=ver.change_note,
        tags=_tag_list(ver.tags),
        classification_metadata=_string_map(ver.classification_metadata),
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
    q: str | None = Query(None, max_length=200),
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    service: DocumentIngestionService = Depends(get_document_service),
) -> DocumentListResponse:
    del workspaceId
    result = await service.list_documents(
        access.workspace_id,
        page=page,
        page_size=page_size,
        file_type=file_type,
        query=q.strip() if q and q.strip() else None,
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
    "/{workspaceId}/documents/{documentId}/canonical",
    response_model=CanonicalDocumentResponse,
    summary="Canonical Knowledge Document (Markdown + blocks)",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def get_canonical_document(
    workspaceId: uuid.UUID,
    documentId: uuid.UUID,
    versionId: uuid.UUID | None = Query(
        None,
        description="Optional version override; default = current_version_id",
    ),
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    service: DocumentIngestionService = Depends(get_document_service),
) -> CanonicalDocumentResponse:
    """Return Canonical Markdown + structured blocks for Knowledge View."""
    del workspaceId
    try:
        return await service.get_canonical_document(
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
        "Content-Disposition": _content_disposition(disposition, payload.filename),
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
    change_note: str | None = Form(default=None),
    access: WorkspaceAccess = Depends(require_workspace_editor_rl),
    service: DocumentIngestionService = Depends(get_document_service),
) -> DocumentVersionResponse:
    """Upload a newer file for this document. The previous version stays for rollback."""
    del workspaceId
    try:
        result = await service.upload_new_version(
            workspace_id=access.workspace_id,
            document_id=documentId,
            uploaded_by=access.user_id,
            filename=file.filename or "upload.bin",
            file_chunks=iter_upload_file(file),
            change_note=change_note,
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
            actor_id=access.user_id,
        )
    except DocumentIngestionError as exc:
        raise _http_error(exc) from exc
    return _doc_response(doc)


@router.post(
    "/{workspaceId}/documents/{documentId}/versions/{versionId}/rollback",
    response_model=DocumentResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def rollback_version(
    workspaceId: uuid.UUID,
    documentId: uuid.UUID,
    versionId: uuid.UUID,
    access: WorkspaceAccess = Depends(require_workspace_editor_rl),
    service: DocumentIngestionService = Depends(get_document_service),
) -> DocumentResponse:
    """Restore an older ready version as the current version — admin | editor."""
    del workspaceId
    try:
        doc = await service.rollback_version(
            workspace_id=access.workspace_id,
            document_id=documentId,
            version_id=versionId,
            actor_id=access.user_id,
        )
    except DocumentIngestionError as exc:
        raise _http_error(exc) from exc
    return _doc_response(doc)


@router.patch(
    "/{workspaceId}/documents/{documentId}/versions/{versionId}",
    response_model=DocumentVersionResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def update_version_classification(
    workspaceId: uuid.UUID,
    documentId: uuid.UUID,
    versionId: uuid.UUID,
    body: VersionClassificationUpdate,
    access: WorkspaceAccess = Depends(require_workspace_editor_rl),
    service: VersioningService = Depends(get_versioning_service),
) -> DocumentVersionResponse:
    """Set tags, classification metadata, and the change note — admin | editor."""
    del workspaceId
    if not body.model_fields_set:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                code="empty_update",
                message="Provide tags, classification_metadata, or change_note",
            ).model_dump(),
        )
    try:
        version = await service.update_classification(
            workspace_id=access.workspace_id,
            document_id=documentId,
            version_id=versionId,
            actor_id=access.user_id,
            tags=body.tags,
            classification_metadata=body.classification_metadata,
            change_note=body.change_note if "change_note" in body.model_fields_set else UNSET,
        )
    except DocumentIngestionError as exc:
        raise _http_error(exc) from exc
    return _version_response(version)


def _catalog_item(entry) -> VersionCatalogItemResponse:
    version = entry.version
    document = entry.document
    return VersionCatalogItemResponse(
        id=version.id,
        document_id=document.id,
        document_title=document.title,
        file_type=document.file_type.value,  # type: ignore[arg-type]
        uploaded_by=version.uploaded_by,
        uploader_name=entry.uploader_name,
        uploader_email=entry.uploader_email,
        version_number=version.version_number,
        file_size_bytes=version.file_size_bytes,
        checksum_sha256=version.checksum_sha256,
        page_count=version.page_count,
        status=version.status.value,  # type: ignore[arg-type]
        ai_analysis_status=version.ai_analysis_status.value,  # type: ignore[arg-type]
        analyzed_at=version.analyzed_at,
        is_current=version.is_current,
        created_at=version.created_at,
        change_note=version.change_note,
        tags=_tag_list(version.tags),
        classification_metadata=_string_map(version.classification_metadata),
    )


@router.get(
    "/{workspaceId}/versions",
    response_model=VersionCatalogResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def list_workspace_versions(
    workspaceId: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, max_length=200),
    tag: str | None = Query(None, max_length=40),
    document_id: uuid.UUID | None = Query(None),
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    service: VersioningService = Depends(get_versioning_service),
) -> VersionCatalogResponse:
    """Every document version in the workspace, with tags and uploader."""
    del workspaceId
    try:
        page_result = await service.list_catalog(
            access.workspace_id,
            page=page,
            page_size=page_size,
            document_id=document_id,
            tag=tag,
            query=q,
        )
    except DocumentIngestionError as exc:
        raise _http_error(exc) from exc
    return VersionCatalogResponse(
        items=[_catalog_item(item) for item in page_result.items],
        page=page_result.page,
        page_size=page_result.page_size,
        total=page_result.total,
        available_tags=page_result.available_tags,
    )


@router.get(
    "/{workspaceId}/versions/history",
    response_model=VersionEventListResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def list_version_history(
    workspaceId: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, max_length=200),
    document_id: uuid.UUID | None = Query(None),
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    service: VersioningService = Depends(get_versioning_service),
) -> VersionEventListResponse:
    """Append-only edit history: uploads, rollbacks, tags, and metadata."""
    del workspaceId
    try:
        page_result = await service.list_history(
            access.workspace_id,
            page=page,
            page_size=page_size,
            document_id=document_id,
            query=q,
        )
    except DocumentIngestionError as exc:
        raise _http_error(exc) from exc
    return VersionEventListResponse(
        items=[
            VersionEventResponse(
                id=item.event.id,
                document_id=item.event.document_id,
                document_version_id=item.event.document_version_id,
                document_title=item.document_title,
                version_number=item.version_number,
                actor_id=item.event.actor_id,
                actor_name=item.actor_name,
                event_type=item.event.event_type,  # type: ignore[arg-type]
                summary=item.event.summary,
                payload=item.event.payload if isinstance(item.event.payload, dict) else None,
                created_at=item.event.created_at,
            )
            for item in page_result.items
        ],
        page=page_result.page,
        page_size=page_result.page_size,
        total=page_result.total,
    )


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


def _analysis_http_error(exc: AnalysisServiceError | AIGatewayError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail=ErrorResponse(code=exc.code, message=exc.message).model_dump(),
    )


def _analysis_response(snapshot) -> DocumentAnalysisResponse:
    ver = snapshot.version
    run = snapshot.pipeline_run
    return DocumentAnalysisResponse(
        document_id=ver.document_id,
        version_id=ver.id,
        status=ver.ai_analysis_status.value,  # type: ignore[arg-type]
        analyzed_at=ver.analyzed_at,
        error=ver.analysis_error,
        pipeline_run_id=run.id if run is not None else None,
    )


@router.get(
    "/{workspaceId}/documents/{documentId}/versions/{versionId}/analysis",
    response_model=DocumentAnalysisResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def get_document_analysis(
    workspaceId: uuid.UUID,
    documentId: uuid.UUID,
    versionId: uuid.UUID,
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    service: AnalysisService = Depends(get_analysis_service),
) -> DocumentAnalysisResponse:
    """Return AI analysis status. Does not trigger analysis."""
    del workspaceId
    try:
        snapshot = await service.get_status(
            workspace_id=access.workspace_id,
            document_id=documentId,
            version_id=versionId,
        )
    except AnalysisServiceError as exc:
        raise _analysis_http_error(exc) from exc
    return _analysis_response(snapshot)


@router.post(
    "/{workspaceId}/documents/{documentId}/versions/{versionId}/analysis",
    response_model=DocumentAnalysisResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
)
async def request_document_analysis(
    workspaceId: uuid.UUID,
    documentId: uuid.UUID,
    versionId: uuid.UUID,
    access: WorkspaceAccess = Depends(require_workspace_editor_rl),
    service: AnalysisService = Depends(get_analysis_service),
) -> DocumentAnalysisResponse:
    """Enqueue on-demand AI analysis. Idempotent if already READY or in-flight."""
    del workspaceId
    try:
        snapshot = await service.request_analysis(
            workspace_id=access.workspace_id,
            document_id=documentId,
            version_id=versionId,
        )
    except (AnalysisServiceError, AIGatewayError) as exc:
        raise _analysis_http_error(exc) from exc
    return _analysis_response(snapshot)
