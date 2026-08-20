# =============================================================================
# File: extractions.py
# Module/Service: Extraction Service (FR7)
# Layer: Presentation
# Purpose: FastAPI routes for async Information Extraction CRUD (FR7 / UC6).
# Responsibilities:
#   - GET/POST document extractions; GET/DELETE extraction by id
#   - RBAC: member read; editor+ mutate; map domain errors to ErrorResponse
# Dependencies:
#   - require_workspace_*_rl, ExtractionService, Pydantic Extraction schemas
# Public Exports:
#   - router
# Database/Table: extractions
# Related Modules: docs/Enterprise_notebooklm_openapi.yaml (/workspaces/*/extractions*)
# Important Notes: POST returns 202 processing; generation runs in Celery.
#   Router does not call LLM or contain extraction business logic.
# =============================================================================

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db_session
from app.dependencies.rate_limit import (
    require_workspace_editor_rl,
    require_workspace_member_rl,
)
from app.dependencies.rbac import WorkspaceAccess
from app.models.artifacts import Extraction
from app.models.enums import TargetLanguage
from app.repositories.documents import DocumentRepository
from app.repositories.extractions import ExtractionRepository
from app.repositories.retrieval import RetrievalRepository
from app.schemas.common import ErrorResponse
from app.schemas.extractions import ExtractionCreateRequest, ExtractionResponse
from app.services.extraction.extraction_service import (
    ExtractionService,
    ExtractionServiceError,
)

router = APIRouter(prefix="/workspaces", tags=["Extractions"])


def get_extraction_service(
    session: AsyncSession = Depends(get_db_session),
) -> ExtractionService:
    return ExtractionService(
        settings=get_settings(),
        session=session,
        documents=DocumentRepository(session),
        retrieval=RetrievalRepository(session),
        extractions=ExtractionRepository(session),
    )


def _extraction_response(row: Extraction) -> ExtractionResponse:
    result: dict[str, Any] | None = row.result_json
    language = row.target_language or TargetLanguage.vi
    return ExtractionResponse(
        id=row.id,
        document_id=row.document_id,
        source_version_id=row.source_version_id,
        extraction_type=row.extraction_type,
        output_format=row.output_format,
        target_language=language,
        status=row.status,
        result=result,
        created_at=row.created_at,
    )


def _http_error(exc: ExtractionServiceError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail=ErrorResponse(code=exc.code, message=exc.message).model_dump(),
    )


@router.get(
    "/{workspaceId}/documents/{documentId}/extractions",
    response_model=list[ExtractionResponse],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def list_document_extractions(
    workspaceId: uuid.UUID,
    documentId: uuid.UUID,
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    service: ExtractionService = Depends(get_extraction_service),
) -> list[ExtractionResponse]:
    del workspaceId
    try:
        rows = await service.list_extractions(
            workspace_id=access.workspace_id,
            document_id=documentId,
        )
    except ExtractionServiceError as exc:
        raise _http_error(exc) from exc
    return [_extraction_response(r) for r in rows]


@router.post(
    "/{workspaceId}/documents/{documentId}/extractions",
    response_model=ExtractionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def create_document_extraction(
    workspaceId: uuid.UUID,
    documentId: uuid.UUID,
    body: ExtractionCreateRequest,
    access: WorkspaceAccess = Depends(require_workspace_editor_rl),
    service: ExtractionService = Depends(get_extraction_service),
) -> ExtractionResponse:
    """Enqueue async extraction — admin | editor (viewer → 403)."""
    del workspaceId
    try:
        row = await service.request_extraction(
            workspace_id=access.workspace_id,
            document_id=documentId,
            extraction_type=body.extraction_type,
            output_format=body.output_format,
            target_language=body.target_language,
            created_by=access.user_id,
        )
    except ExtractionServiceError as exc:
        raise _http_error(exc) from exc
    return _extraction_response(row)


@router.get(
    "/{workspaceId}/extractions/{extractionId}",
    response_model=ExtractionResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def get_extraction(
    workspaceId: uuid.UUID,
    extractionId: uuid.UUID,
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    service: ExtractionService = Depends(get_extraction_service),
) -> ExtractionResponse:
    del workspaceId
    try:
        row = await service.get_extraction(
            workspace_id=access.workspace_id,
            extraction_id=extractionId,
        )
    except ExtractionServiceError as exc:
        raise _http_error(exc) from exc
    return _extraction_response(row)


@router.delete(
    "/{workspaceId}/extractions/{extractionId}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def delete_extraction(
    workspaceId: uuid.UUID,
    extractionId: uuid.UUID,
    access: WorkspaceAccess = Depends(require_workspace_editor_rl),
    service: ExtractionService = Depends(get_extraction_service),
) -> None:
    del workspaceId
    try:
        await service.delete_extraction(
            workspace_id=access.workspace_id,
            extraction_id=extractionId,
        )
    except ExtractionServiceError as exc:
        raise _http_error(exc) from exc
