# =============================================================================
# File: chat.py
# Module/Service: Chat Service
# Layer: Presentation
# Purpose: FastAPI routes for chat agent-events (FR14) and future chat APIs.
# Responsibilities:
#   - GET /workspaces/{workspaceId}/chat/messages/{messageId}/agent-events
# Dependencies:
#   - require_workspace_member_rl, AgentEventsService, get_db_session
# Public Exports:
#   - router
# Database/Table: agent_events (via service/repository)
# Related Modules: docs/Enterprise_notebooklm_openapi.yaml §Chat
# Important Notes: Empty list → 200 []; missing message → 404; RBAC via member.
# =============================================================================

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.dependencies.rate_limit import require_workspace_member_rl
from app.dependencies.rbac import WorkspaceAccess
from app.repositories.agent_events import AgentEventRepository
from app.schemas.chat import AgentEventResponse
from app.schemas.common import ErrorResponse
from app.services.chat.agent_events_service import (
    AgentEventsService,
    AgentEventsServiceError,
)

router = APIRouter(prefix="/workspaces", tags=["Chat"])


def get_agent_events_service(
    session: AsyncSession = Depends(get_db_session),
) -> AgentEventsService:
    return AgentEventsService(AgentEventRepository(session))


def _http_error(exc: AgentEventsServiceError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail=ErrorResponse(code=exc.code, message=exc.message).model_dump(),
    )


@router.get(
    "/{workspaceId}/chat/messages/{messageId}/agent-events",
    response_model=list[AgentEventResponse],
    summary="Chi tiết Micro Agent đã kích hoạt cho message (FR14)",
    operation_id="listMessageAgentEvents",
    responses={
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    },
)
async def list_message_agent_events(
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    message_id: uuid.UUID = Path(..., alias="messageId"),
    service: AgentEventsService = Depends(get_agent_events_service),
) -> list[AgentEventResponse]:
    """Return agent_events for a message; ``[]`` when none (never 404 for empty)."""
    try:
        return await service.list_for_message(
            workspace_id=access.workspace_id,
            message_id=message_id,
        )
    except AgentEventsServiceError as exc:
        raise _http_error(exc) from exc
