# =============================================================================
# File: workspaces.py
# Module/Service: Workspace Service
# Layer: Repository
# Purpose: Data access for the workspaces table (FR1 CRUD + soft-delete).
# Responsibilities:
#   - Fetch / create / update / soft-delete workspaces
#   - List active workspaces for a member with pagination
# Dependencies:
#   - SQLAlchemy AsyncSession, app.models.identity.Workspace
# Public Exports:
#   - WorkspaceRepository
# Database/Table: workspaces, workspace_members
# Related Modules: app.services.workspaces, app.api.workspaces
# Important Notes:
#   - Soft-delete: set deleted_at; list/get active rows filter deleted_at IS NULL.
#   - Multi-tenant: list_for_member always joins workspace_members by user_id.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import Workspace, WorkspaceMember


class WorkspaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(
        self,
        workspace_id: uuid.UUID,
        *,
        include_deleted: bool = False,
    ) -> Workspace | None:
        stmt = select(Workspace).where(Workspace.id == workspace_id)
        if not include_deleted:
            stmt = stmt.where(Workspace.deleted_at.is_(None))
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_member(
        self,
        user_id: uuid.UUID,
        *,
        page: int,
        page_size: int,
    ) -> tuple[list[Workspace], int]:
        """Return active workspaces the user belongs to, plus total count."""
        membership = WorkspaceMember.workspace_id == Workspace.id
        active = Workspace.deleted_at.is_(None)
        member_filter = WorkspaceMember.user_id == user_id
        active_member = WorkspaceMember.deleted_at.is_(None)

        count_stmt = (
            select(func.count())
            .select_from(Workspace)
            .join(WorkspaceMember, membership)
            .where(member_filter, active, active_member)
        )
        total = int((await self._session.execute(count_stmt)).scalar_one())

        offset = (page - 1) * page_size
        list_stmt = (
            select(Workspace)
            .join(WorkspaceMember, membership)
            .where(member_filter, active, active_member)
            .order_by(Workspace.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await self._session.execute(list_stmt)).scalars().all()
        return list(rows), total

    async def list_all_active(
        self,
        *,
        page: int,
        page_size: int,
    ) -> tuple[list[Workspace], int]:
        """Return all active workspaces (Platform Manage enterprise directory)."""
        active = Workspace.deleted_at.is_(None)
        count_stmt = select(func.count()).select_from(Workspace).where(active)
        total = int((await self._session.execute(count_stmt)).scalar_one())

        offset = (page - 1) * page_size
        list_stmt = (
            select(Workspace)
            .where(active)
            .order_by(Workspace.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await self._session.execute(list_stmt)).scalars().all()
        return list(rows), total

    async def count_owned_by_user(self, user_id: uuid.UUID) -> int:
        """Count workspaces owned by user (includes soft-deleted — owner_id RESTRICT)."""
        stmt = select(func.count()).select_from(Workspace).where(Workspace.owner_id == user_id)
        return int((await self._session.execute(stmt)).scalar_one())

    async def create(
        self,
        *,
        name: str,
        description: str | None,
        owner_id: uuid.UUID,
    ) -> Workspace:
        workspace = Workspace(
            name=name,
            description=description,
            owner_id=owner_id,
        )
        self._session.add(workspace)
        await self._session.flush()
        return workspace

    async def update(
        self,
        workspace: Workspace,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> Workspace:
        if name is not None:
            workspace.name = name
        if description is not None:
            workspace.description = description
        await self._session.flush()
        return workspace

    async def soft_delete(self, workspace: Workspace) -> None:
        """Mark workspace deleted; does not remove the row (schema v2 extension)."""
        workspace.deleted_at = datetime.now(UTC)
        await self._session.flush()

    async def soft_delete_by_id(self, workspace_id: uuid.UUID) -> bool:
        """Soft-delete by id if active. Returns True when a row was updated."""
        stmt = (
            update(Workspace)
            .where(Workspace.id == workspace_id, Workspace.deleted_at.is_(None))
            .values(deleted_at=datetime.now(UTC))
        )
        result = await self._session.execute(stmt)
        return bool(result.rowcount)
