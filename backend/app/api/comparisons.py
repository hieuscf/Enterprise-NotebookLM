# =============================================================================
# File: comparisons.py
# Module/Service: Comparison Service (FR8)
# Layer: Presentation
# Purpose: FastAPI routes for async multi-document Comparison CRUD (FR8 / UC7).
# Responsibilities:
#   - GET/POST workspace comparisons; GET/DELETE comparison by id
#   - RBAC: member read; editor+ mutate; map domain errors to ErrorResponse
# Dependencies:
#   - require_workspace_*_rl, ComparisonService, Pydantic Comparison schemas
# Public Exports:
#   - router
# Database/Table: comparisons, comparison_documents
# Related Modules: docs/Enterprise_notebooklm_openapi.yaml (/workspaces/*/comparisons*)
# Important Notes: POST returns 202 processing; generation runs in Celery.
#   Router does not call LLM or contain comparison business logic.
# =============================================================================

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db_session
from app.dependencies.rate_limit import (
    require_workspace_editor_rl,
    require_workspace_member_rl,
)
from app.dependencies.rbac import WorkspaceAccess
from app.repositories.comparisons import ComparisonRepository, ComparisonWithDocuments
from app.repositories.documents import DocumentRepository
from app.repositories.retrieval import RetrievalRepository
from app.repositories.summaries import SummaryRepository
from app.schemas.common import ErrorResponse
from app.schemas.comparisons import (
    ComparisonCreateRequest,
    ComparisonResponse,
    ComparisonResultPayload,
)
from app.services.comparison.comparison_service import (
    ComparisonService,
    ComparisonServiceError,
)

router = APIRouter(prefix="/workspaces", tags=["Comparisons"])


def get_comparison_service(
    session: AsyncSession = Depends(get_db_session),
) -> ComparisonService:
    return ComparisonService(
        settings=get_settings(),
        session=session,
        documents=DocumentRepository(session),
        retrieval=RetrievalRepository(session),
        summaries=SummaryRepository(session),
        comparisons=ComparisonRepository(session),
    )


def _comparison_response(row: ComparisonWithDocuments) -> ComparisonResponse:
    result_payload: ComparisonResultPayload | None = None
    raw: dict[str, Any] | None = row.comparison.result
    if isinstance(raw, dict):
        sims = raw.get("similarities")
        diffs = raw.get("differences")
        result_payload = ComparisonResultPayload(
            similarities=[str(s) for s in sims] if isinstance(sims, list) else [],
            differences=[str(d) for d in diffs] if isinstance(diffs, list) else [],
        )
    return ComparisonResponse(
        id=row.comparison.id,
        workspace_id=row.comparison.workspace_id,
        document_ids=list(row.document_ids),
        status=row.comparison.status,
        result=result_payload,
        created_at=row.comparison.created_at,
    )


def _http_error(exc: ComparisonServiceError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail=ErrorResponse(code=exc.code, message=exc.message).model_dump(),
    )


@router.get(
    "/{workspaceId}/comparisons",
    response_model=list[ComparisonResponse],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def list_comparisons(
    workspaceId: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    service: ComparisonService = Depends(get_comparison_service),
) -> list[ComparisonResponse]:
    del workspaceId
    rows = await service.list_comparisons(
        workspace_id=access.workspace_id,
        page=page,
        page_size=page_size,
    )
    return [_comparison_response(r) for r in rows]


@router.post(
    "/{workspaceId}/comparisons",
    response_model=ComparisonResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def create_comparison(
    workspaceId: uuid.UUID,
    body: ComparisonCreateRequest,
    access: WorkspaceAccess = Depends(require_workspace_editor_rl),
    service: ComparisonService = Depends(get_comparison_service),
) -> ComparisonResponse:
    """Enqueue async comparison — admin | editor (viewer → 403)."""
    del workspaceId
    try:
        row = await service.request_comparison(
            workspace_id=access.workspace_id,
            document_ids=body.document_ids,
            focus=body.focus,
            created_by=access.user_id,
        )
    except ComparisonServiceError as exc:
        raise _http_error(exc) from exc
    return _comparison_response(row)


@router.get(
    "/{workspaceId}/comparisons/{comparisonId}",
    response_model=ComparisonResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def get_comparison(
    workspaceId: uuid.UUID,
    comparisonId: uuid.UUID,
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    service: ComparisonService = Depends(get_comparison_service),
) -> ComparisonResponse:
    del workspaceId
    try:
        row = await service.get_comparison(
            workspace_id=access.workspace_id,
            comparison_id=comparisonId,
        )
    except ComparisonServiceError as exc:
        raise _http_error(exc) from exc
    return _comparison_response(row)


@router.delete(
    "/{workspaceId}/comparisons/{comparisonId}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def delete_comparison(
    workspaceId: uuid.UUID,
    comparisonId: uuid.UUID,
    access: WorkspaceAccess = Depends(require_workspace_editor_rl),
    service: ComparisonService = Depends(get_comparison_service),
) -> None:
    del workspaceId
    try:
        await service.delete_comparison(
            workspace_id=access.workspace_id,
            comparison_id=comparisonId,
        )
    except ComparisonServiceError as exc:
        raise _http_error(exc) from exc
