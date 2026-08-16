# =============================================================================
# File: reports.py
# Module/Service: Report Service (FR9)
# Layer: Presentation
# Purpose: FastAPI routes for async Report CRUD + export (FR9 / UC8).
# Responsibilities:
#   - POST 202 pending; GET list/detail; GET export stream; DELETE 204
#   - RBAC: member read/export; editor+ mutate; map domain errors to ErrorResponse
#   - Export streams the stored artifact (CMP-26); never regenerates content
# Dependencies:
#   - require_workspace_*_rl, ReportService, Pydantic Report schemas
# Public Exports:
#   - router
# Database/Table: reports, report_items
# Related Modules: docs/Enterprise_notebooklm_openapi.yaml (/workspaces/*/reports*)
# Important Notes: POST returns 202 pending; generation runs in Celery.
#   Router does not render files or contain aggregation business logic.
# =============================================================================

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.minio_storage import get_minio_storage
from app.db.session import get_db_session
from app.dependencies.rate_limit import (
    require_workspace_editor_rl,
    require_workspace_member_rl,
)
from app.dependencies.rbac import WorkspaceAccess
from app.repositories.chat_messages import ChatMessageRepository
from app.repositories.chat_sessions import ChatSessionRepository
from app.repositories.comparisons import ComparisonRepository
from app.repositories.documents import DocumentRepository
from app.repositories.extractions import ExtractionRepository
from app.repositories.reports import ReportRepository, ReportWithItems
from app.repositories.summaries import SummaryRepository
from app.schemas.common import ErrorResponse
from app.schemas.reports import ReportCreateRequest, ReportResponse, ReportSourceRef
from app.services.report_aggregation import (
    ReportAggregationService,
    ReportItemInput as AggregationItem,
)
from app.services.report_service import (
    ReportService,
    ReportServiceError,
    report_file_url,
)

router = APIRouter(prefix="/workspaces", tags=["Reports"])


def get_report_service(
    session: AsyncSession = Depends(get_db_session),
) -> ReportService:
    comparisons = ComparisonRepository(session)
    aggregation = ReportAggregationService(
        summaries=SummaryRepository(session),
        extractions=ExtractionRepository(session),
        comparisons=comparisons,
        chat_sessions=ChatSessionRepository(session),
        chat_messages=ChatMessageRepository(session),
        documents=DocumentRepository(session),
    )
    return ReportService(
        session=session,
        reports=ReportRepository(session),
        aggregation=aggregation,
        storage=get_minio_storage(),
        comparisons=comparisons,
    )


def _report_response(
    row: ReportWithItems,
    *,
    preview: dict | None = None,
) -> ReportResponse:
    report = row.report
    items = [
        ReportSourceRef(
            source_type=item.source_type,
            source_id=item.source_id,
            order_index=item.order_index,
        )
        for item in row.items
    ]
    return ReportResponse(
        id=report.id,
        workspace_id=report.workspace_id,
        title=report.title,
        export_format=report.format,
        status=report.status,
        file_url=report_file_url(
            workspace_id=report.workspace_id,
            report_id=report.id,
            status=report.status,
        ),
        created_at=report.created_at,
        items=items,
        preview=preview,
    )


def _http_error(exc: ReportServiceError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail=ErrorResponse(code=exc.code, message=exc.message).model_dump(),
    )


@router.get(
    "/{workspaceId}/reports",
    response_model=list[ReportResponse],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def list_reports(
    workspaceId: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    service: ReportService = Depends(get_report_service),
) -> list[ReportResponse]:
    del workspaceId
    rows = await service.list_reports(
        workspace_id=access.workspace_id,
        page=page,
        page_size=page_size,
    )
    return [_report_response(r) for r in rows]


@router.post(
    "/{workspaceId}/reports",
    response_model=ReportResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def create_report(
    workspaceId: uuid.UUID,
    body: ReportCreateRequest,
    access: WorkspaceAccess = Depends(require_workspace_editor_rl),
    service: ReportService = Depends(get_report_service),
) -> ReportResponse:
    """Enqueue async report generation — admin | editor (viewer → 403)."""
    del workspaceId
    items = [
        AggregationItem(
            source_type=item.source_type,
            source_id=item.source_id,
            order_index=item.order_index,
        )
        for item in body.items
    ]
    try:
        row = await service.request_report(
            workspace_id=access.workspace_id,
            created_by=access.user_id,
            title=body.title,
            export_format=body.export_format,
            items=items,
        )
    except ReportServiceError as exc:
        raise _http_error(exc) from exc
    return _report_response(row)


@router.get(
    "/{workspaceId}/reports/{reportId}",
    response_model=ReportResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def get_report(
    workspaceId: uuid.UUID,
    reportId: uuid.UUID,
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    service: ReportService = Depends(get_report_service),
) -> ReportResponse:
    del workspaceId
    try:
        row = await service.get_report(
            workspace_id=access.workspace_id,
            report_id=reportId,
        )
    except ReportServiceError as exc:
        raise _http_error(exc) from exc
    preview = await service.comparison_preview(row)
    return _report_response(row, preview=preview)


@router.get(
    "/{workspaceId}/reports/{reportId}/export",
    responses={
        status.HTTP_200_OK: {
            "content": {
                "application/pdf": {},
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {},
                "text/markdown": {},
            }
        },
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
)
async def export_report(
    workspaceId: uuid.UUID,
    reportId: uuid.UUID,
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    service: ReportService = Depends(get_report_service),
) -> StreamingResponse:
    del workspaceId
    try:
        payload = await service.export_report(
            workspace_id=access.workspace_id,
            report_id=reportId,
            actor_id=access.user_id,
        )
    except ReportServiceError as exc:
        raise _http_error(exc) from exc
    headers = {
        "Content-Disposition": payload.content_disposition,
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    }
    if payload.content_length is not None:
        headers["Content-Length"] = str(payload.content_length)
    return StreamingResponse(
        payload.iterator,
        media_type=payload.content_type,
        headers=headers,
    )


@router.delete(
    "/{workspaceId}/reports/{reportId}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def delete_report(
    workspaceId: uuid.UUID,
    reportId: uuid.UUID,
    access: WorkspaceAccess = Depends(require_workspace_editor_rl),
    service: ReportService = Depends(get_report_service),
) -> None:
    del workspaceId
    try:
        await service.delete_report(
            workspace_id=access.workspace_id,
            report_id=reportId,
        )
    except ReportServiceError as exc:
        raise _http_error(exc) from exc
