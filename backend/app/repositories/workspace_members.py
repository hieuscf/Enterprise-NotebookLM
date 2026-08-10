# =============================================================================
# File: workspace_members.py
# Module/Service: Auth Service / Workspace Service
# Layer: Repository
# Purpose: Data access for workspace_members joined with roles.
# Responsibilities:
#   - List / resolve active memberships (deleted_at IS NULL)
#   - Add / update / soft-delete members; count admins
# Dependencies:
#   - SQLAlchemy AsyncSession, app.models.identity
# Public Exports:
#   - WorkspaceMemberRepository, MembershipRow, MemberDetailRow
# Database/Table: workspace_members, roles, users
# Related Modules: app.services.auth, app.services.workspaces, app.services.members
# Important Notes:
#   - role_id is FK → roles.id; role name comes from JOIN (OpenAPI string enum).
#   - Soft-delete: active queries filter deleted_at IS NULL (RBAC + lists).
# =============================================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import RoleName
from app.models.identity import Role, User, Workspace, WorkspaceMember


@dataclass(frozen=True, slots=True)
class MembershipRow:
    workspace_id: uuid.UUID
    role: RoleName


@dataclass(frozen=True, slots=True)
class MemberDetailRow:
    user_id: uuid.UUID
    email: str
    role: RoleName
    joined_at: datetime


@dataclass(frozen=True, slots=True)
class AdminScopedMemberRow:
    user_id: uuid.UUID
    email: str
    full_name: str
    workspace_id: uuid.UUID
    workspace_name: str
    role: RoleName
    joined_at: datetime


class WorkspaceMemberRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user(self, user_id: uuid.UUID) -> list[MembershipRow]:
        stmt = (
            select(WorkspaceMember.workspace_id, Role.name)
            .join(Role, Role.id == WorkspaceMember.role_id)
            .where(
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.deleted_at.is_(None),
            )
            .order_by(WorkspaceMember.joined_at.asc())
        )
        result = await self._session.execute(stmt)
        return [MembershipRow(workspace_id=row.workspace_id, role=row.name) for row in result.all()]

    async def get_role_for_user(
        self, *, user_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> RoleName | None:
        """Return the user's active role in a workspace, or None if not a member.

        Always query DB — do not trust JWT workspace claims (may be omitted when
        membership count exceeds JWT_WORKSPACE_EMBED_LIMIT). Soft-deleted rows
        are ignored so DELETE workspace / remove-member revoke access immediately.
        """
        stmt = (
            select(Role.name)
            .join(WorkspaceMember, WorkspaceMember.role_id == Role.id)
            .where(
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.deleted_at.is_(None),
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_workspace(self, workspace_id: uuid.UUID) -> list[MemberDetailRow]:
        stmt = (
            select(
                WorkspaceMember.user_id,
                User.email,
                Role.name,
                WorkspaceMember.joined_at,
            )
            .join(User, User.id == WorkspaceMember.user_id)
            .join(Role, Role.id == WorkspaceMember.role_id)
            .where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.deleted_at.is_(None),
            )
            .order_by(WorkspaceMember.joined_at.asc())
        )
        result = await self._session.execute(stmt)
        return [
            MemberDetailRow(
                user_id=row.user_id,
                email=row.email,
                role=row.name,
                joined_at=row.joined_at,
            )
            for row in result.all()
        ]

    async def get_active_member(
        self, *, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> WorkspaceMember | None:
        stmt = (
            select(WorkspaceMember)
            .where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.deleted_at.is_(None),
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_any_member_row(
        self, *, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> WorkspaceMember | None:
        """Active or soft-deleted row (for re-invite / 409 duplicate checks)."""
        stmt = (
            select(WorkspaceMember)
            .where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
            .order_by(WorkspaceMember.joined_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_member(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        role_id: uuid.UUID,
    ) -> WorkspaceMember:
        member = WorkspaceMember(
            workspace_id=workspace_id,
            user_id=user_id,
            role_id=role_id,
        )
        self._session.add(member)
        await self._session.flush()
        return member

    async def revive_member(
        self,
        member: WorkspaceMember,
        *,
        role_id: uuid.UUID,
    ) -> WorkspaceMember:
        """Re-activate a soft-deleted membership (re-invite after remove)."""
        member.role_id = role_id
        member.deleted_at = None
        member.joined_at = datetime.now(UTC)
        await self._session.flush()
        return member

    async def update_role(
        self,
        member: WorkspaceMember,
        *,
        role_id: uuid.UUID,
    ) -> WorkspaceMember:
        member.role_id = role_id
        await self._session.flush()
        return member

    async def soft_delete(self, member: WorkspaceMember) -> None:
        member.deleted_at = datetime.now(UTC)
        await self._session.flush()

    async def soft_delete_all_for_workspace(self, workspace_id: uuid.UUID) -> int:
        """Soft-delete every active member of a workspace (used with workspace soft-delete)."""
        stmt = (
            update(WorkspaceMember)
            .where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.deleted_at.is_(None),
            )
            .values(deleted_at=datetime.now(UTC))
        )
        result = await self._session.execute(stmt)
        return int(result.rowcount or 0)

    async def count_active_admins(self, workspace_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(WorkspaceMember)
            .join(Role, Role.id == WorkspaceMember.role_id)
            .where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.deleted_at.is_(None),
                Role.name == RoleName.admin,
            )
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def count_active_members(self, workspace_id: uuid.UUID) -> int:
        """Count non-deleted members in a workspace."""
        stmt = (
            select(func.count())
            .select_from(WorkspaceMember)
            .where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.deleted_at.is_(None),
            )
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def list_admin_workspace_ids(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        """Active workspaces where the user has role=admin (non-deleted WS)."""
        stmt = (
            select(WorkspaceMember.workspace_id)
            .join(Role, Role.id == WorkspaceMember.role_id)
            .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
            .where(
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.deleted_at.is_(None),
                Workspace.deleted_at.is_(None),
                Role.name == RoleName.admin,
            )
            .order_by(WorkspaceMember.joined_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_active_workspace_ids(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        """Active (non-soft-deleted) workspace ids for a user."""
        stmt = (
            select(WorkspaceMember.workspace_id)
            .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
            .where(
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.deleted_at.is_(None),
                Workspace.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_members_for_workspaces(
        self, workspace_ids: list[uuid.UUID]
    ) -> list[AdminScopedMemberRow]:
        """Active members across the given workspaces (admin-scoped directory)."""
        if not workspace_ids:
            return []
        stmt = (
            select(
                WorkspaceMember.user_id.label("user_id"),
                User.email.label("email"),
                User.full_name.label("full_name"),
                WorkspaceMember.workspace_id.label("workspace_id"),
                Workspace.name.label("workspace_name"),
                Role.name.label("role"),
                WorkspaceMember.joined_at.label("joined_at"),
            )
            .join(User, User.id == WorkspaceMember.user_id)
            .join(Role, Role.id == WorkspaceMember.role_id)
            .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
            .where(
                WorkspaceMember.workspace_id.in_(workspace_ids),
                WorkspaceMember.deleted_at.is_(None),
                Workspace.deleted_at.is_(None),
            )
            .order_by(User.email.asc(), WorkspaceMember.joined_at.asc())
        )
        result = await self._session.execute(stmt)
        return [
            AdminScopedMemberRow(
                user_id=row.user_id,
                email=row.email,
                full_name=row.full_name,
                workspace_id=row.workspace_id,
                workspace_name=row.workspace_name,
                role=row.role,
                joined_at=row.joined_at,
            )
            for row in result.all()
        ]
