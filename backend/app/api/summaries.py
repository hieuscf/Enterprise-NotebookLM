# =============================================================================
# File: summaries.py
# Module/Service: Summary Service (FR6)
# Layer: Presentation
# Purpose: FastAPI routes for async AI Summary CRUD (FR6 / UC5).
# Responsibilities:
#   - GET/POST document summaries; GET/DELETE summary by id
#   - RBAC: member read; editor+ mutate; map domain errors to ErrorResponse
# Dependencies:
#   - require_workspace_*_rl, SummaryService, Pydantic Summary schemas
# Public Exports:
#   - router
# Database/Table: summaries
# Related Modules: docs/Enterprise_notebooklm_openapi.yaml (/workspaces/*/summaries*)
# Important Notes: POST returns 202 processing; generation runs in Celery.
# =============================================================================

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db_session
from app.dependencies.rate_limit import (
    require_workspace_editor_rl,
    require_workspace_member_rl,
)
from app.dependencies.rbac import WorkspaceAccess
from app.models.artifacts import Summary
from app.repositories.documents import DocumentRepository
from app.repositories.retrieval import RetrievalRepository
from app.repositories.summaries import SummaryRepository
from app.schemas.common import ErrorResponse
from app.schemas.summaries import SummaryCreateRequest, SummaryResponse
from app.services.summary.summary_service import SummaryService, SummaryServiceError

router = APIRouter(prefix="/workspaces", tags=["Summaries"])


def get_summary_service(
    session: AsyncSession = Depends(get_db_session),
) -> SummaryService:
    return SummaryService(
        settings=get_settings(),
        session=session,
        documents=DocumentRepository(session),
        retrieval=RetrievalRepository(session),
        summaries=SummaryRepository(session),
    )


def _summary_response(row: Summary) -> SummaryResponse:
    sections_raw = row.sections
    sections = None
    if isinstance(sections_raw, list) and sections_raw:
        from app.schemas.summaries import SummaryTopicSection

        parsed: list[SummaryTopicSection] = []
        for item in sections_raw:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            content = str(item.get("content") or "").strip()
            if not title and not content:
                continue
            topic_id = item.get("topic_id")
            parsed.append(
                SummaryTopicSection(
                    topic_id=uuid.UUID(str(topic_id)) if topic_id else None,
                    title=title or "Chủ đề",
                    content=content,
                )
            )
        sections = parsed or None
    return SummaryResponse(
        id=row.id,
        document_id=row.document_id,
        source_version_id=row.source_version_id,
        style=row.type,  # ORM ``type`` → OpenAPI ``style``
        status=row.status,
        content=row.content,
        sections=sections,
        created_at=row.created_at,
    )


def _http_error(exc: SummaryServiceError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail=ErrorResponse(code=exc.code, message=exc.message).model_dump(),
    )


@router.get(
    "/{workspaceId}/documents/{documentId}/summaries",
    response_model=list[SummaryResponse],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def list_document_summaries(
    workspaceId: uuid.UUID,
    documentId: uuid.UUID,
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    service: SummaryService = Depends(get_summary_service),
) -> list[SummaryResponse]:
    del workspaceId
    try:
        rows = await service.list_summaries(
            workspace_id=access.workspace_id,
            document_id=documentId,
        )
    except SummaryServiceError as exc:
        raise _http_error(exc) from exc
    return [_summary_response(r) for r in rows]


@router.post(
    "/{workspaceId}/documents/{documentId}/summaries",
    response_model=SummaryResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def create_document_summary(
    workspaceId: uuid.UUID,
    documentId: uuid.UUID,
    body: SummaryCreateRequest,
    access: WorkspaceAccess = Depends(require_workspace_editor_rl),
    service: SummaryService = Depends(get_summary_service),
) -> SummaryResponse:
    """Enqueue async summary generation — admin | editor (viewer → 403)."""
    del workspaceId
    try:
        row = await service.request_summary(
            workspace_id=access.workspace_id,
            document_id=documentId,
            style=body.style,
            created_by=access.user_id,
        )
    except SummaryServiceError as exc:
        raise _http_error(exc) from exc
    return _summary_response(row)


@router.get(
    "/{workspaceId}/summaries/{summaryId}",
    response_model=SummaryResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def get_summary(
    workspaceId: uuid.UUID,
    summaryId: uuid.UUID,
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    service: SummaryService = Depends(get_summary_service),
) -> SummaryResponse:
    del workspaceId
    try:
        row = await service.get_summary(
            workspace_id=access.workspace_id,
            summary_id=summaryId,
        )
    except SummaryServiceError as exc:
        raise _http_error(exc) from exc
    return _summary_response(row)


@router.delete(
    "/{workspaceId}/summaries/{summaryId}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def delete_summary(
    workspaceId: uuid.UUID,
    summaryId: uuid.UUID,
    access: WorkspaceAccess = Depends(require_workspace_editor_rl),
    service: SummaryService = Depends(get_summary_service),
) -> None:
    del workspaceId
    try:
        await service.delete_summary(
            workspace_id=access.workspace_id,
            summary_id=summaryId,
        )
    except SummaryServiceError as exc:
        raise _http_error(exc) from exc
