# =============================================================================
# File: session_service.py
# Module/Service: Chat Service
# Layer: Service
# Purpose: Conversation Memory — session CRUD + message history (FR4 Part 1).
# Responsibilities:
#   - Create / list / get / soft-delete chat sessions
#   - List messages with nested generation + citations
#   - Enforce owner-scoped read; owner-or-admin delete
# Dependencies:
#   - ChatSessionRepository, ChatMessageRepository
# Public Exports:
#   - ChatSessionService, ChatServiceError
# Database/Table: chat_sessions, chat_messages, message_generations, citations
# Related Modules: app.api.chat
# Important Notes:
#   - Part 1: no POST message / Query Router / LLM / SSE.
#   - OpenAPI ChatSession has no denormalized preview fields — see TODO below.
# =============================================================================

from __future__ import annotations

import uuid
from decimal import Decimal

from app.core.logging import get_logger
from app.models.chat import ChatSession, MessageGeneration
from app.models.enums import MessageRole, RoleName
from app.repositories.chat_messages import ChatMessageRepository, CitationWithDocument
from app.repositories.chat_sessions import ChatSessionRepository
from app.schemas.canonical import CitationLocator
from app.schemas.chat import (
    ChatMessageResponse,
    ChatSessionResponse,
    CitationResponse,
    MessageGenerationResponse,
)

logger = get_logger(__name__)


class ChatServiceError(Exception):
    """Domain error mapped to HTTP by the presentation layer."""

    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ChatSessionService:
    """Application service for Conversation Memory (sessions + history)."""

    def __init__(
        self,
        sessions: ChatSessionRepository,
        messages: ChatMessageRepository,
    ) -> None:
        self._sessions = sessions
        self._messages = messages

    async def create_session(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        title: str | None = None,
    ) -> ChatSessionResponse:
        """Create an empty session; title stays NULL when omitted (Part 2 fills)."""
        cleaned = title.strip() if title is not None else None
        if cleaned == "":
            cleaned = None
        row = await self._sessions.create(
            workspace_id=workspace_id,
            user_id=user_id,
            title=cleaned,
        )
        logger.info(
            "chat_session_created",
            workspace_id=str(workspace_id),
            session_id=str(row.id),
            user_id=str(user_id),
        )
        return _session_response(row)

    async def list_sessions(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        page: int,
        page_size: int,
    ) -> list[ChatSessionResponse]:
        """Owner's active sessions, ``updated_at`` DESC, page/page_size.

        TODO(Part 2): OpenAPI ChatSession has no last_message_preview /
        message_count / last_message_at. When those denormalized columns (or
        computed fields) are added to the contract, enrich list items here via
        ChatMessageRepository.count()/latest() — do not invent extra response
        fields before OpenAPI updates.
        """
        rows, _total = await self._sessions.list(
            workspace_id=workspace_id,
            user_id=user_id,
            page=page,
            page_size=page_size,
        )
        return [_session_response(r) for r in rows]

    async def get_session(
        self,
        *,
        workspace_id: uuid.UUID,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ChatSessionResponse:
        """Return session detail for the owner; 404 when missing/deleted/foreign."""
        row = await self._require_readable_session(
            workspace_id=workspace_id,
            session_id=session_id,
            user_id=user_id,
        )
        return _session_response(row)

    async def delete_session(
        self,
        *,
        workspace_id: uuid.UUID,
        session_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        actor_role: RoleName,
    ) -> None:
        """Soft-delete: owner or workspace admin. Others → 403; missing → 404."""
        row = await self._sessions.get(
            session_id=session_id,
            workspace_id=workspace_id,
            include_deleted=False,
        )
        if row is None:
            raise ChatServiceError(
                "not_found",
                "Chat session not found in this workspace",
                status_code=404,
            )

        is_owner = row.user_id == actor_user_id
        is_admin = actor_role is RoleName.admin
        if not is_owner and not is_admin:
            raise ChatServiceError(
                "forbidden",
                "Only the session owner or a workspace admin can delete this session",
                status_code=403,
            )

        deleted = await self._sessions.soft_delete(
            session_id=session_id,
            workspace_id=workspace_id,
            deleted_by=actor_user_id,
        )
        if not deleted:
            raise ChatServiceError(
                "not_found",
                "Chat session not found in this workspace",
                status_code=404,
            )
        logger.info(
            "chat_session_soft_deleted",
            workspace_id=str(workspace_id),
            session_id=str(session_id),
            deleted_by=str(actor_user_id),
            was_owner=is_owner,
        )

    async def list_messages(
        self,
        *,
        workspace_id: uuid.UUID,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        page: int,
        page_size: int,
    ) -> list[ChatMessageResponse]:
        """History for an owned active session; created_at ASC (FE-ready order)."""
        await self._require_readable_session(
            workspace_id=workspace_id,
            session_id=session_id,
            user_id=user_id,
        )
        rows = await self._messages.list(
            session_id=session_id,
            page=page,
            page_size=page_size,
        )
        return [_message_response(r.message, r.generation, r.citations) for r in rows]

    async def _require_readable_session(
        self,
        *,
        workspace_id: uuid.UUID,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ChatSession:
        """Active session owned by user_id, else not_found (no existence leak)."""
        row = await self._sessions.get(
            session_id=session_id,
            workspace_id=workspace_id,
            include_deleted=False,
        )
        if row is None or row.user_id != user_id:
            raise ChatServiceError(
                "not_found",
                "Chat session not found in this workspace",
                status_code=404,
            )
        return row


def _session_response(row: ChatSession) -> ChatSessionResponse:
    return ChatSessionResponse(
        id=row.id,
        workspace_id=row.workspace_id,
        title=row.title,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _message_response(
    message,
    generation: MessageGeneration | None,
    citations: list[CitationWithDocument],
) -> ChatMessageResponse:
    role = message.role.value if hasattr(message.role, "value") else str(message.role)
    if role == MessageRole.user.value:
        return ChatMessageResponse(
            id=message.id,
            session_id=message.session_id,
            role="user",
            content=message.content,
            generation=None,
            citations=[],
            created_at=message.created_at,
        )
    return ChatMessageResponse(
        id=message.id,
        session_id=message.session_id,
        role="assistant",
        content=message.content,
        generation=_generation_response(generation) if generation else None,
        citations=[_citation_response(c) for c in citations],
        created_at=message.created_at,
    )


def _generation_response(gen: MessageGeneration) -> MessageGenerationResponse:
    return MessageGenerationResponse(
        route_type=gen.route_type.value,  # type: ignore[arg-type]
        confidence_level=(
            gen.confidence_level.value if gen.confidence_level is not None else None
        ),
        confidence_score=gen.confidence_score,
        agent_triggered=bool(gen.agent_triggered),
        model_used=gen.model_used,
        prompt_tokens=gen.prompt_tokens,
        completion_tokens=gen.completion_tokens,
        total_tokens=gen.total_tokens,
        cost_usd=_decimal_to_float(gen.cost_usd),
        latency_ms=gen.latency_ms,
        finish_reason=(
            gen.finish_reason.value if gen.finish_reason is not None else None
        ),
    )


def _citation_response(
    row: CitationWithDocument,
    *,
    locator: CitationLocator | None = None,
) -> CitationResponse:
    c = row.citation
    location = None
    if (
        row.page_number is not None
        or row.section_index is not None
        or (row.section or "").strip()
    ):
        from app.schemas.content_location import content_location_from_chunk

        location = content_location_from_chunk(
            page_number=row.page_number,
            section_index=row.section_index,
            section=row.section,
        )
    return CitationResponse(
        id=c.id,
        message_id=c.message_id,
        retrieval_id=c.retrieval_id,
        document_id=row.document_id,
        chunk_id=row.chunk_id,
        document_version_id=row.document_version_id,
        text_snippet=c.text_snippet,
        verified=bool(c.verified),
        order_index=c.order_index,
        location=location,
        locator=locator,
    )


def _decimal_to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)
