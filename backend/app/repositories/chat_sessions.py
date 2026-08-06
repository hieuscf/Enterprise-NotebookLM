# =============================================================================
# File: chat_sessions.py
# Module/Service: Chat Service
# Layer: Repository
# Purpose: Data access for chat_sessions (Conversation Memory / FR4).
# Responsibilities:
#   - create / get / list / exists / touch / soft_delete
# Dependencies:
#   - SQLAlchemy AsyncSession, app.models.chat.ChatSession
# Public Exports:
#   - ChatSessionRepository
# Database/Table: chat_sessions
# Related Modules: app.services.chat.session_service, app.api.chat
# Important Notes:
#   - Active rows: deleted_at IS NULL. touch() bumps updated_at for Part 2.
#   - list() is scoped to workspace + owner user; sort updated_at DESC.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatSession


class ChatSessionRepository:
    """CRUD + soft-delete for ``chat_sessions`` (no business rules)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        title: str | None = None,
    ) -> ChatSession:
        """Insert a new session. Title may be NULL until Part 2 generates one."""
        row = ChatSession(
            workspace_id=workspace_id,
            user_id=user_id,
            title=title,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(
        self,
        *,
        session_id: uuid.UUID,
        workspace_id: uuid.UUID,
        include_deleted: bool = False,
    ) -> ChatSession | None:
        """Return session in workspace, or None when missing / wrong tenant."""
        stmt = select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.workspace_id == workspace_id,
        )
        if not include_deleted:
            stmt = stmt.where(ChatSession.deleted_at.is_(None))
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        page: int,
        page_size: int,
    ) -> tuple[list[ChatSession], int]:
        """Active sessions for one owner in workspace; ``updated_at`` DESC."""
        filters = (
            ChatSession.workspace_id == workspace_id,
            ChatSession.user_id == user_id,
            ChatSession.deleted_at.is_(None),
        )
        total = int(
            (
                await self._session.execute(
                    select(func.count()).select_from(ChatSession).where(*filters)
                )
            ).scalar_one()
        )
        offset = (page - 1) * page_size
        rows = (
            await self._session.execute(
                select(ChatSession)
                .where(*filters)
                .order_by(ChatSession.updated_at.desc())
                .offset(offset)
                .limit(page_size)
            )
        ).scalars().all()
        return list(rows), total

    async def exists(
        self,
        *,
        session_id: uuid.UUID,
        workspace_id: uuid.UUID,
        include_deleted: bool = False,
    ) -> bool:
        """True when an active (or include_deleted) session exists in workspace."""
        stmt = select(ChatSession.id).where(
            ChatSession.id == session_id,
            ChatSession.workspace_id == workspace_id,
        )
        if not include_deleted:
            stmt = stmt.where(ChatSession.deleted_at.is_(None))
        result = await self._session.execute(stmt.limit(1))
        return result.scalar_one_or_none() is not None

    async def touch(self, session_id: uuid.UUID) -> bool:
        """Bump ``updated_at`` after a new message (Part 2). Returns True if updated."""
        stmt = (
            update(ChatSession)
            .where(
                ChatSession.id == session_id,
                ChatSession.deleted_at.is_(None),
            )
            .values(updated_at=datetime.now(UTC))
        )
        result = await self._session.execute(stmt)
        return bool(result.rowcount)

    async def soft_delete(
        self,
        *,
        session_id: uuid.UUID,
        workspace_id: uuid.UUID,
        deleted_by: uuid.UUID,
    ) -> bool:
        """Set deleted_at/deleted_by when active. Returns True if a row changed."""
        stmt = (
            update(ChatSession)
            .where(
                ChatSession.id == session_id,
                ChatSession.workspace_id == workspace_id,
                ChatSession.deleted_at.is_(None),
            )
            .values(
                deleted_at=datetime.now(UTC),
                deleted_by=deleted_by,
            )
        )
        result = await self._session.execute(stmt)
        return bool(result.rowcount)
