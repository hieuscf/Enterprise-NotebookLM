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
#   CMP-23 audit is GET/POST /audit; not included on ComparisonResponse.
# =============================================================================

from __future__ import annotations

import uuid
from typing import Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db_session
from app.dependencies.rate_limit import (
    require_workspace_editor_rl,
    require_workspace_member_rl,
)
from app.dependencies.auth import CurrentUser, get_current_user
from app.dependencies.rbac import WorkspaceAccess
from app.repositories.comparisons import ComparisonRepository, ComparisonWithDocuments
from app.repositories.documents import DocumentRepository
from app.repositories.retrieval import RetrievalRepository
from app.repositories.summaries import SummaryRepository
from app.schemas.common import ErrorResponse
from app.schemas.comparisons import (
    ComparisonAuditCreateRequest,
    ComparisonAuditEvent,
    ComparisonAuditTrailResponse,
    ComparisonComment,
    ComparisonCommentCreateRequest,
    ComparisonCommentUpdateRequest,
    ComparisonCreateRequest,
    ComparisonResponse,
    ComparisonResultPayload,
    ComparisonReviewDecision,
    ComparisonReviewUpdateRequest,
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


def _review_payload(raw: object) -> dict[str, ComparisonReviewDecision]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, ComparisonReviewDecision] = {}
    for key, value in raw.items():
        if not isinstance(value, dict):
            continue
        status_value = str(value.get("status") or "").upper()
        if status_value not in {"REVIEWED", "NEEDS_ATTENTION", "ACKNOWLEDGED"}:
            continue
        reviewer_id = value.get("reviewer_id")
        parsed_id = None
        if reviewer_id:
            try:
                parsed_id = uuid.UUID(str(reviewer_id))
            except ValueError:
                parsed_id = None
        reviewed_at = value.get("reviewed_at")
        parsed_at = None
        if isinstance(reviewed_at, str) and reviewed_at.strip():
            try:
                parsed_at = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
            except ValueError:
                parsed_at = None
        name = str(value.get("reviewer_name") or "").strip() or None
        out[str(key)] = ComparisonReviewDecision(
            status=status_value,  # type: ignore[arg-type]
            reviewer_id=parsed_id,
            reviewer_name=name,
            reviewed_at=parsed_at,
        )
    return out


def _parse_iso(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _comments_payload(raw: object) -> list[ComparisonComment]:
    if not isinstance(raw, list):
        return []
    out: list[ComparisonComment] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        if item.get("deleted_at"):
            continue
        comment_id = str(item.get("id") or "").strip()
        clause_id = str(item.get("clause_id") or "").strip()
        body = str(item.get("body") or "").strip()
        target_type = str(item.get("target_type") or "CLAUSE").upper()
        if target_type == "FINDING":
            target_type = "CLAUSE"
        if not comment_id or not clause_id or not body:
            continue
        if target_type not in {"CLAUSE", "EXACT_DIFFERENCE", "EVIDENCE"}:
            continue
        author_id = item.get("author_id")
        parsed_id = None
        if author_id:
            try:
                parsed_id = uuid.UUID(str(author_id))
            except ValueError:
                parsed_id = None
        target_id = str(item.get("target_id") or "").strip() or None
        if target_type == "CLAUSE":
            target_id = None
        name = str(item.get("author_name") or "").strip() or None
        out.append(
            ComparisonComment(
                id=comment_id,
                clause_id=clause_id,
                target_type=target_type,  # type: ignore[arg-type]
                target_id=target_id,
                body=body,
                author_id=parsed_id,
                author_name=name,
                created_at=_parse_iso(item.get("created_at")),
                updated_at=_parse_iso(item.get("updated_at")),
            )
        )
    return out


def _audit_payload(raw: object) -> list[ComparisonAuditEvent]:
    if not isinstance(raw, list):
        return []
    out: list[ComparisonAuditEvent] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        event_id = str(item.get("id") or "").strip()
        action = str(item.get("action") or "").upper()
        occurred_at = _parse_iso(item.get("occurred_at"))
        if not event_id or not occurred_at:
            continue
        if action not in {
            "CLAUSE_OPENED",
            "REVIEW_STATUS_CHANGED",
            "COMMENT_ADDED",
            "COMMENT_EDITED",
            "COMMENT_DELETED",
        }:
            continue
        actor_id = item.get("actor_id")
        parsed_id = None
        if actor_id:
            try:
                parsed_id = uuid.UUID(str(actor_id))
            except ValueError:
                parsed_id = None
        before = item.get("before")
        after = item.get("after")
        out.append(
            ComparisonAuditEvent(
                id=event_id,
                action=action,  # type: ignore[arg-type]
                clause_id=str(item.get("clause_id") or "").strip() or None,
                actor_id=parsed_id,
                actor_name=str(item.get("actor_name") or "").strip() or None,
                occurred_at=occurred_at,
                before=dict(before) if isinstance(before, dict) else None,
                after=dict(after) if isinstance(after, dict) else None,
                target_type=str(item.get("target_type") or "").strip() or None,
                target_id=str(item.get("target_id") or "").strip() or None,
                comment_id=str(item.get("comment_id") or "").strip() or None,
            )
        )
    return out


def _comparison_response(row: ComparisonWithDocuments) -> ComparisonResponse:
    result_payload: ComparisonResultPayload | None = None
    raw: dict[str, Any] | None = row.comparison.result
    if isinstance(raw, dict):
        sims = raw.get("similarities")
        diffs = raw.get("differences")
        result_payload = ComparisonResultPayload(
            similarities=[str(s) for s in sims] if isinstance(sims, list) else [],
            differences=[str(d) for d in diffs] if isinstance(diffs, list) else [],
            contract_comparison=(
                raw.get("contract_comparison")
                if isinstance(raw.get("contract_comparison"), dict)
                else None
            ),
        )
    return ComparisonResponse(
        id=row.comparison.id,
        workspace_id=row.comparison.workspace_id,
        document_ids=list(row.document_ids),
        status=row.comparison.status,
        result=result_payload,
        review=_review_payload(getattr(row.comparison, "review", None)),
        comments=_comments_payload(getattr(row.comparison, "comments", None)),
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


@router.patch(
    "/{workspaceId}/comparisons/{comparisonId}/review",
    response_model=ComparisonResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def update_comparison_review(
    workspaceId: uuid.UUID,
    comparisonId: uuid.UUID,
    body: ComparisonReviewUpdateRequest,
    access: WorkspaceAccess = Depends(require_workspace_editor_rl),
    current_user: CurrentUser = Depends(get_current_user),
    service: ComparisonService = Depends(get_comparison_service),
) -> ComparisonResponse:
    """Record a reviewer decision. Does not modify comparison analysis."""
    del workspaceId
    try:
        row = await service.set_review(
            workspace_id=access.workspace_id,
            comparison_id=comparisonId,
            clause_id=body.clause_id,
            status=body.status,
            reviewer_id=current_user.id,
            reviewer_name=current_user.full_name,
        )
    except ComparisonServiceError as exc:
        raise _http_error(exc) from exc
    return _comparison_response(row)


@router.post(
    "/{workspaceId}/comparisons/{comparisonId}/comments",
    response_model=ComparisonResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def create_comparison_comment(
    workspaceId: uuid.UUID,
    comparisonId: uuid.UUID,
    body: ComparisonCommentCreateRequest,
    access: WorkspaceAccess = Depends(require_workspace_editor_rl),
    current_user: CurrentUser = Depends(get_current_user),
    service: ComparisonService = Depends(get_comparison_service),
) -> ComparisonResponse:
    """Add a reviewer comment. Does not modify comparison analysis."""
    del workspaceId
    try:
        row = await service.add_comment(
            workspace_id=access.workspace_id,
            comparison_id=comparisonId,
            clause_id=body.clause_id,
            body=body.body,
            target_type=body.target_type,
            target_id=body.target_id,
            author_id=current_user.id,
            author_name=current_user.full_name,
        )
    except ComparisonServiceError as exc:
        raise _http_error(exc) from exc
    return _comparison_response(row)


@router.patch(
    "/{workspaceId}/comparisons/{comparisonId}/comments/{commentId}",
    response_model=ComparisonResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def update_comparison_comment(
    workspaceId: uuid.UUID,
    comparisonId: uuid.UUID,
    commentId: str,
    body: ComparisonCommentUpdateRequest,
    access: WorkspaceAccess = Depends(require_workspace_editor_rl),
    current_user: CurrentUser = Depends(get_current_user),
    service: ComparisonService = Depends(get_comparison_service),
) -> ComparisonResponse:
    """Edit a reviewer comment. Does not modify comparison analysis."""
    del workspaceId
    try:
        row = await service.edit_comment(
            workspace_id=access.workspace_id,
            comparison_id=comparisonId,
            comment_id=commentId,
            body=body.body,
            author_id=current_user.id,
        )
    except ComparisonServiceError as exc:
        raise _http_error(exc) from exc
    return _comparison_response(row)


@router.delete(
    "/{workspaceId}/comparisons/{comparisonId}/comments/{commentId}",
    response_model=ComparisonResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def delete_comparison_comment(
    workspaceId: uuid.UUID,
    comparisonId: uuid.UUID,
    commentId: str,
    access: WorkspaceAccess = Depends(require_workspace_editor_rl),
    current_user: CurrentUser = Depends(get_current_user),
    service: ComparisonService = Depends(get_comparison_service),
) -> ComparisonResponse:
    """Remove a reviewer comment. Does not modify comparison analysis."""
    del workspaceId
    try:
        row = await service.remove_comment(
            workspace_id=access.workspace_id,
            comparison_id=comparisonId,
            comment_id=commentId,
            actor_id=current_user.id,
            actor_name=current_user.full_name,
        )
    except ComparisonServiceError as exc:
        raise _http_error(exc) from exc
    return _comparison_response(row)


@router.get(
    "/{workspaceId}/comparisons/{comparisonId}/audit",
    response_model=ComparisonAuditTrailResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def get_comparison_audit(
    workspaceId: uuid.UUID,
    comparisonId: uuid.UUID,
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    service: ComparisonService = Depends(get_comparison_service),
) -> ComparisonAuditTrailResponse:
    """Return the append-only review audit trail. Does not modify analysis."""
    del workspaceId
    try:
        events = await service.list_audit(
            workspace_id=access.workspace_id,
            comparison_id=comparisonId,
        )
    except ComparisonServiceError as exc:
        raise _http_error(exc) from exc
    return ComparisonAuditTrailResponse(events=_audit_payload(events))


@router.post(
    "/{workspaceId}/comparisons/{comparisonId}/audit",
    response_model=ComparisonAuditTrailResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def create_comparison_audit_event(
    workspaceId: uuid.UUID,
    comparisonId: uuid.UUID,
    body: ComparisonAuditCreateRequest,
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    current_user: CurrentUser = Depends(get_current_user),
    service: ComparisonService = Depends(get_comparison_service),
) -> ComparisonAuditTrailResponse:
    """Record CLAUSE_OPENED. Review/comment mutations are audited server-side."""
    del workspaceId
    try:
        events = await service.record_clause_opened(
            workspace_id=access.workspace_id,
            comparison_id=comparisonId,
            clause_id=body.clause_id,
            actor_id=current_user.id,
            actor_name=current_user.full_name,
        )
    except ComparisonServiceError as exc:
        raise _http_error(exc) from exc
    return ComparisonAuditTrailResponse(events=_audit_payload(events))
