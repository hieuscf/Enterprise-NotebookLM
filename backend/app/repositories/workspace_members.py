# =============================================================================
# File: workspace_members.py
# Module/Service: Auth Service / Workspace Service
# Layer: Repository
# Purpose: Data access for workspace_members joined with roles.
# Responsibilities:
#   - List memberships (workspace_id, role name) for a user
# Dependencies:
#   - SQLAlchemy AsyncSession, app.models.identity
# Public Exports:
#   - WorkspaceMemberRepository, MembershipRow
# Database/Table: workspace_members, roles
# Related Modules: app.services.auth, app.dependencies.auth
# Important Notes: Always source of truth for RBAC (do not trust JWT alone).
# =============================================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import RoleName
from app.models.identity import Role, WorkspaceMember


@dataclass(frozen=True, slots=True)
class MembershipRow:
    workspace_id: uuid.UUID
    role: RoleName


class WorkspaceMemberRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user(self, user_id: uuid.UUID) -> list[MembershipRow]:
        stmt = (
            select(WorkspaceMember.workspace_id, Role.name)
            .join(Role, Role.id == WorkspaceMember.role_id)
            .where(WorkspaceMember.user_id == user_id)
            .order_by(WorkspaceMember.joined_at.asc())
        )
        result = await self._session.execute(stmt)
        return [MembershipRow(workspace_id=row.workspace_id, role=row.name) for row in result.all()]

    async def get_role_for_user(
        self, *, user_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> RoleName | None:
        """Return the user's role in a workspace, or None if not a member.

        Always query DB — do not trust JWT workspace claims (may be omitted when
        membership count exceeds JWT_WORKSPACE_EMBED_LIMIT).
        """
        stmt = (
            select(Role.name)
            .join(WorkspaceMember, WorkspaceMember.role_id == Role.id)
            .where(
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.workspace_id == workspace_id,
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
