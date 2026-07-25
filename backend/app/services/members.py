# =============================================================================
# File: members.py
# Module/Service: Workspace Service
# Layer: Service
# Purpose: Business logic for workspace member management (FR1 / UC10).
# Responsibilities:
#   - List members; add / change role / remove with admin-only rules at API layer
#   - Block demote/remove of the last remaining admin
#   - 409 on duplicate active membership; revive soft-deleted rows on re-invite
# Dependencies:
#   - app.repositories.workspace_members, roles, users, workspaces
# Public Exports:
#   - WorkspaceMemberService, MemberError
# Database/Table: workspace_members, roles, users, workspaces
# Related Modules: app.api.workspaces, docs/Enterprise_notebooklm_openapi.yaml
# Important Notes:
#   - 409 Conflict for duplicate member is an extension beyond OpenAPI (needed).
#   - Last-admin guard is a business rule not in OpenAPI — prevents orphan WS.
# =============================================================================

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import RoleName
from app.repositories.roles import RoleRepository
from app.repositories.users import UserRepository
from app.repositories.workspace_members import MemberDetailRow, WorkspaceMemberRepository
from app.repositories.workspaces import WorkspaceRepository


class MemberError(Exception):
    """Domain error mapped to HTTP by the presentation layer."""

    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class WorkspaceMemberService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._members = WorkspaceMemberRepository(session)
        self._roles = RoleRepository(session)
        self._users = UserRepository(session)
        self._workspaces = WorkspaceRepository(session)

    async def _require_active_workspace(self, workspace_id: uuid.UUID) -> None:
        if await self._workspaces.get_by_id(workspace_id) is None:
            raise MemberError("not_found", "Workspace not found", status_code=404)

    async def _role_id(self, role: RoleName) -> uuid.UUID:
        row = await self._roles.get_by_name(role)
        if row is None:
            raise MemberError(
                "roles_not_seeded",
                f"System role '{role.value}' is missing; run DB migrations",
                status_code=500,
            )
        return row.id

    async def _detail(self, *, workspace_id: uuid.UUID, user_id: uuid.UUID) -> MemberDetailRow:
        rows = await self._members.list_for_workspace(workspace_id)
        for row in rows:
            if row.user_id == user_id:
                return row
        raise MemberError("not_found", "Workspace member not found", status_code=404)

    async def list_members(self, workspace_id: uuid.UUID) -> list[MemberDetailRow]:
        await self._require_active_workspace(workspace_id)
        return await self._members.list_for_workspace(workspace_id)

    async def add_member(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        role: RoleName,
    ) -> MemberDetailRow:
        await self._require_active_workspace(workspace_id)

        user = await self._users.get_by_id(user_id)
        if user is None:
            raise MemberError("user_not_found", "User not found", status_code=404)

        role_id = await self._role_id(role)
        existing = await self._members.get_any_member_row(
            workspace_id=workspace_id, user_id=user_id
        )
        if existing is not None and existing.deleted_at is None:
            # Decision: 409 Conflict — not in OpenAPI but required to avoid silent
            # UniqueViolation / ambiguous 500 when re-adding an active member.
            raise MemberError(
                "member_exists",
                "User is already a member of this workspace",
                status_code=409,
            )

        if existing is not None and existing.deleted_at is not None:
            await self._members.revive_member(existing, role_id=role_id)
        else:
            await self._members.add_member(
                workspace_id=workspace_id,
                user_id=user_id,
                role_id=role_id,
            )
        return await self._detail(workspace_id=workspace_id, user_id=user_id)

    async def update_role(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        role: RoleName,
        actor_user_id: uuid.UUID,
    ) -> MemberDetailRow:
        """Change a member's role.

        Decision (not in OpenAPI): refuse demoting the last admin so the
        workspace cannot lose all administrators. Applies when the target is
        currently admin and the new role is not admin, regardless of whether
        the actor is demoting themselves or another admin.
        """
        del actor_user_id  # reserved for future audit; last-admin is count-based
        await self._require_active_workspace(workspace_id)

        member = await self._members.get_active_member(workspace_id=workspace_id, user_id=user_id)
        if member is None:
            raise MemberError("not_found", "Workspace member not found", status_code=404)

        current_role = await self._members.get_role_for_user(
            user_id=user_id, workspace_id=workspace_id
        )
        if current_role == RoleName.admin and role != RoleName.admin:
            admin_count = await self._members.count_active_admins(workspace_id)
            if admin_count <= 1:
                raise MemberError(
                    "last_admin",
                    "Cannot demote the last admin of this workspace",
                    status_code=400,
                )

        role_id = await self._role_id(role)
        await self._members.update_role(member, role_id=role_id)
        return await self._detail(workspace_id=workspace_id, user_id=user_id)

    async def remove_member(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Soft-delete membership.

        Decision (not in OpenAPI): refuse removing the last admin.
        """
        await self._require_active_workspace(workspace_id)

        member = await self._members.get_active_member(workspace_id=workspace_id, user_id=user_id)
        if member is None:
            raise MemberError("not_found", "Workspace member not found", status_code=404)

        current_role = await self._members.get_role_for_user(
            user_id=user_id, workspace_id=workspace_id
        )
        if current_role == RoleName.admin:
            admin_count = await self._members.count_active_admins(workspace_id)
            if admin_count <= 1:
                raise MemberError(
                    "last_admin",
                    "Cannot remove the last admin of this workspace",
                    status_code=400,
                )

        await self._members.soft_delete(member)
