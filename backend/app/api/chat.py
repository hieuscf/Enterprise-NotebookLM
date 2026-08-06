# =============================================================================
# File: chat.py
# Module/Service: Chat Service
# Layer: Presentation
# Purpose: FastAPI routes for Conversation Memory (FR4) + agent-events (FR14).
# Responsibilities:
#   - CRUD chat sessions (soft-delete) + GET message history
#   - GET /chat/messages/{messageId}/agent-events
# Dependencies:
#   - require_workspace_member_rl, ChatSessionService, AgentEventsService
# Public Exports:
#   - router
# Database/Table: chat_sessions, chat_messages, agent_events (via services)
# Related Modules: docs/Enterprise_notebooklm_openapi.yaml §Chat
# Important Notes:
#   - Part 1: NO POST .../messages (Query Router / LLM / SSE = Part 2).
#   - Delete RBAC: owner or workspace admin (checked in service).
# =============================================================================

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.dependencies.rate_limit import require_workspace_member_rl
from app.dependencies.rbac import WorkspaceAccess
from app.repositories.agent_events import AgentEventRepository
from app.repositories.chat_messages import ChatMessageRepository
from app.repositories.chat_sessions import ChatSessionRepository
from app.schemas.chat import (
    AgentEventResponse,
    ChatMessageResponse,
    ChatSessionCreateRequest,
    ChatSessionResponse,
)
from app.schemas.common import ErrorResponse
from app.services.chat.agent_events_service import (
    AgentEventsService,
    AgentEventsServiceError,
)
from app.services.chat.session_service import ChatServiceError, ChatSessionService

router = APIRouter(prefix="/workspaces", tags=["Chat"])


def get_agent_events_service(
    session: AsyncSession = Depends(get_db_session),
) -> AgentEventsService:
    return AgentEventsService(AgentEventRepository(session))


def get_chat_session_service(
    session: AsyncSession = Depends(get_db_session),
) -> ChatSessionService:
    return ChatSessionService(
        ChatSessionRepository(session),
        ChatMessageRepository(session),
    )


def _agent_http_error(exc: AgentEventsServiceError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail=ErrorResponse(code=exc.code, message=exc.message).model_dump(),
    )


def _chat_http_error(exc: ChatServiceError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail=ErrorResponse(code=exc.code, message=exc.message).model_dump(),
    )


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


@router.get(
    "/{workspaceId}/chat/sessions",
    response_model=list[ChatSessionResponse],
    summary="Danh sách phiên chat của user (Conversation Memory)",
    operation_id="listChatSessions",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    },
)
async def list_chat_sessions(
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    page: int = Query(1, ge=1, description="Page number (OpenAPI PageParam)"),
    page_size: int = Query(
        20, ge=1, le=100, description="Page size (OpenAPI PageSizeParam, max 100)"
    ),
    service: ChatSessionService = Depends(get_chat_session_service),
) -> list[ChatSessionResponse]:
    """List the current user's active sessions in the workspace."""
    try:
        return await service.list_sessions(
            workspace_id=access.workspace_id,
            user_id=access.user_id,
            page=page,
            page_size=page_size,
        )
    except ChatServiceError as exc:
        raise _chat_http_error(exc) from exc


@router.post(
    "/{workspaceId}/chat/sessions",
    response_model=ChatSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Tạo phiên chat mới",
    operation_id="createChatSession",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    },
)
async def create_chat_session(
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    body: ChatSessionCreateRequest | None = None,
    service: ChatSessionService = Depends(get_chat_session_service),
) -> ChatSessionResponse:
    """Create an empty session; optional title (NULL when omitted)."""
    title = body.title if body is not None else None
    try:
        return await service.create_session(
            workspace_id=access.workspace_id,
            user_id=access.user_id,
            title=title,
        )
    except ChatServiceError as exc:
        raise _chat_http_error(exc) from exc


@router.get(
    "/{workspaceId}/chat/sessions/{sessionId}",
    response_model=ChatSessionResponse,
    summary="Chi tiết phiên chat (để tiếp tục ngữ cảnh cũ)",
    operation_id="getChatSession",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    },
)
async def get_chat_session(
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    session_id: uuid.UUID = Path(..., alias="sessionId"),
    service: ChatSessionService = Depends(get_chat_session_service),
) -> ChatSessionResponse:
    """Return one owned active session; otherwise 404."""
    try:
        return await service.get_session(
            workspace_id=access.workspace_id,
            session_id=session_id,
            user_id=access.user_id,
        )
    except ChatServiceError as exc:
        raise _chat_http_error(exc) from exc


@router.delete(
    "/{workspaceId}/chat/sessions/{sessionId}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Xoá phiên chat",
    operation_id="deleteChatSession",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    },
)
async def delete_chat_session(
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    session_id: uuid.UUID = Path(..., alias="sessionId"),
    service: ChatSessionService = Depends(get_chat_session_service),
) -> Response:
    """Soft-delete: owner or workspace admin."""
    try:
        await service.delete_session(
            workspace_id=access.workspace_id,
            session_id=session_id,
            actor_user_id=access.user_id,
            actor_role=access.role,
        )
    except ChatServiceError as exc:
        raise _chat_http_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Messages (history only — Part 1)
# ---------------------------------------------------------------------------


@router.get(
    "/{workspaceId}/chat/sessions/{sessionId}/messages",
    response_model=list[ChatMessageResponse],
    summary="Lịch sử tin nhắn trong phiên",
    operation_id="listChatSessionMessages",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    },
)
async def list_chat_session_messages(
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    session_id: uuid.UUID = Path(..., alias="sessionId"),
    page: int = Query(1, ge=1, description="Page number (OpenAPI PageParam)"),
    page_size: int = Query(
        20, ge=1, le=100, description="Page size (OpenAPI PageSizeParam, max 100)"
    ),
    service: ChatSessionService = Depends(get_chat_session_service),
) -> list[ChatMessageResponse]:
    """Messages oldest→newest with nested generation/citations for assistants."""
    try:
        return await service.list_messages(
            workspace_id=access.workspace_id,
            session_id=session_id,
            user_id=access.user_id,
            page=page,
            page_size=page_size,
        )
    except ChatServiceError as exc:
        raise _chat_http_error(exc) from exc


# ---------------------------------------------------------------------------
# Agent events (FR14 — existing)
# ---------------------------------------------------------------------------


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
        raise _agent_http_error(exc) from exc
