# =============================================================================
# File: chat.py
# Module/Service: Chat Service
# Layer: Presentation
# Purpose: FastAPI routes for Conversation Memory (FR4) + POST messages + FR14.
# Responsibilities:
#   - CRUD chat sessions (soft-delete) + GET message history
#   - POST .../messages — Query Router + Prompt Construction (SSE / JSON)
#   - GET /chat/messages/{messageId}/agent-events
# Dependencies:
#   - require_workspace_member_rl, ChatSessionService, MessageProcessingService,
#     AgentEventsService, get_query_orchestrator
# Public Exports:
#   - router
# Database/Table: chat_sessions, chat_messages, agent_events (via services)
# Related Modules: docs/Enterprise_notebooklm_openapi.yaml §Chat
# Important Notes:
#   - Default POST response is text/event-stream; Accept: application/json → JSON.
#   - Delete RBAC: owner or workspace admin (checked in service).
# =============================================================================

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db_session
from app.dependencies.query_orchestrator import get_query_orchestrator
from app.dependencies.rate_limit import require_workspace_member_rl
from app.dependencies.rbac import WorkspaceAccess
from app.repositories.agent_events import AgentEventRepository
from app.repositories.chat_messages import ChatMessageRepository
from app.repositories.chat_sessions import ChatSessionRepository
from app.repositories.citations import CitationRepository
from app.repositories.query_logs import QueryObservabilityRepository
from app.repositories.retrieval_records import RetrievalRecordRepository
from app.schemas.chat import (
    AgentEventResponse,
    ChatMessageCreateRequest,
    ChatMessageResponse,
    ChatSessionCreateRequest,
    ChatSessionResponse,
)
from app.schemas.common import ErrorResponse
from app.services.chat.agent_events_service import (
    AgentEventsService,
    AgentEventsServiceError,
)
from app.services.chat.message_service import MessageProcessingService, format_sse
from app.services.chat.session_service import ChatServiceError, ChatSessionService
from app.services.query_router.orchestrator import QueryOrchestrator

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


def get_message_processing_service(
    session: AsyncSession = Depends(get_db_session),
    orchestrator: QueryOrchestrator = Depends(get_query_orchestrator),
) -> MessageProcessingService:
    return MessageProcessingService(
        settings=get_settings(),
        session=session,
        sessions=ChatSessionRepository(session),
        messages=ChatMessageRepository(session),
        citations=CitationRepository(session),
        retrieval_records=RetrievalRecordRepository(session),
        observability=QueryObservabilityRepository(session),
        orchestrator=orchestrator,
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


def _wants_json(accept: str | None, request: Request) -> bool:
    """Prefer JSON only when client explicitly asks for application/json."""
    header = (accept or request.headers.get("accept") or "").lower()
    if not header or header == "*/*":
        return False
    if "text/event-stream" in header and "application/json" not in header:
        return False
    # Explicit JSON (and not primarily SSE).
    if header.strip().startswith("application/json"):
        return True
    if "application/json" in header and "text/event-stream" not in header.split(",")[0]:
        return True
    return False


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
# Messages
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


@router.post(
    "/{workspaceId}/chat/sessions/{sessionId}/messages",
    response_model=None,
    summary="Gửi câu hỏi (Query Router → answer; SSE mặc định)",
    operation_id="createChatSessionMessage",
    responses={
        status.HTTP_200_OK: {
            "description": "SSE stream or JSON ChatMessage",
            "content": {
                "text/event-stream": {"schema": {"type": "string"}},
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ChatMessage"}
                },
            },
        },
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": ErrorResponse},
    },
)
async def create_chat_session_message(
    request: Request,
    body: ChatMessageCreateRequest,
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    session_id: uuid.UUID = Path(..., alias="sessionId"),
    accept: str | None = Header(default=None, alias="Accept"),
    service: MessageProcessingService = Depends(get_message_processing_service),
) -> Response:
    """Process one user question via shared ``generate_answer`` business flow."""
    if _wants_json(accept, request):
        try:
            result = await service.generate_answer(
                workspace_id=access.workspace_id,
                session_id=session_id,
                user_id=access.user_id,
                content=body.content,
            )
        except ChatServiceError as exc:
            raise _chat_http_error(exc) from exc
        return JSONResponse(
            content=result.assistant.model_dump(mode="json"),
            media_type="application/json",
        )

    async def event_source() -> AsyncIterator[str]:
        async for event in service.stream_answer_events(
            workspace_id=access.workspace_id,
            session_id=session_id,
            user_id=access.user_id,
            content=body.content,
        ):
            yield format_sse(event)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


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
