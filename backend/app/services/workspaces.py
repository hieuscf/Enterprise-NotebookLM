# =============================================================================
# File: workspaces.py
# Module/Service: Workspace Service
# Layer: Service
# Purpose: Business logic for Workspace CRUD (FR1, UC1).
# Responsibilities:
#   - List workspaces for current user (membership filter + pagination)
#   - Create workspace + auto-add creator as admin (single DB transaction)
#   - Get / update / soft-delete with active-row checks
# Dependencies:
#   - app.repositories.workspaces, workspace_members, roles
# Public Exports:
#   - WorkspaceService, WorkspaceError
# Database/Table: workspaces, workspace_members, roles
# Related Modules: app.api.workspaces, docs/Enterprise_notebooklm_openapi.yaml
# Important Notes:
#   - POST /workspaces is Platform Manage only (enterprise provisioning).
#     Creator is still auto-added as workspace admin (ownership + membership).
#   - Soft-delete (deleted_at) extends schema v2 — hard delete would cascade
#     wipe FK children (documents, chat_sessions, …).
# =============================================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import RoleName
from app.models.identity import Workspace
from app.repositories.roles import RoleRepository
from app.repositories.workspace_members import WorkspaceMemberRepository
from app.repositories.workspaces import WorkspaceRepository


class WorkspaceError(Exception):
    """Domain error mapped to HTTP by the presentation layer."""

    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class WorkspacePage:
    items: list[Workspace]
    page: int
    page_size: int
    total: int


class WorkspaceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._workspaces = WorkspaceRepository(session)
        self._members = WorkspaceMemberRepository(session)
        self._roles = RoleRepository(session)

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        page: int,
        page_size: int,
    ) -> WorkspacePage:
        items, total = await self._workspaces.list_for_member(
            user_id, page=page, page_size=page_size
        )
        return WorkspacePage(items=items, page=page, page_size=page_size, total=total)

    async def list_all(
        self,
        *,
        page: int,
        page_size: int,
    ) -> WorkspacePage:
        """Enterprise directory — Platform Manage sees every active workspace."""
        items, total = await self._workspaces.list_all_active(
            page=page, page_size=page_size
        )
        return WorkspacePage(items=items, page=page, page_size=page_size, total=total)

    async def create(
        self,
        *,
        owner_id: uuid.UUID,
        name: str,
        description: str | None,
    ) -> Workspace:
        """Create workspace and add creator as workspace admin in one transaction.

        Gate: Platform Manage at the router. Creator becomes owner_id +
        workspace_members.role=admin (Manage does not replace workspace admin).
        """
        admin_role = await self._roles.get_by_name(RoleName.admin)
        if admin_role is None:
            raise WorkspaceError(
                "roles_not_seeded",
                "System role 'admin' is missing; run DB migrations",
                status_code=500,
            )

        workspace = await self._workspaces.create(
            name=name,
            description=description,
            owner_id=owner_id,
        )
        await self._members.add_member(
            workspace_id=workspace.id,
            user_id=owner_id,
            role_id=admin_role.id,
        )
        return workspace

    async def get(self, workspace_id: uuid.UUID) -> Workspace:
        workspace = await self._workspaces.get_by_id(workspace_id)
        if workspace is None:
            raise WorkspaceError(
                "not_found",
                "Workspace not found",
                status_code=404,
            )
        return workspace

    async def update(
        self,
        workspace_id: uuid.UUID,
        *,
        name: str | None,
        description: str | None,
    ) -> Workspace:
        workspace = await self.get(workspace_id)
        if name is None and description is None:
            return workspace
        return await self._workspaces.update(
            workspace,
            name=name,
            description=description,
        )

    async def soft_delete(self, workspace_id: uuid.UUID) -> None:
        """Soft-delete workspace and all active members in one transaction.

        Members are soft-deleted so require_workspace_role / get_role_for_user
        immediately stop treating callers as members of a deleted workspace.
        """
        workspace = await self.get(workspace_id)
        await self._workspaces.soft_delete(workspace)
        await self._members.soft_delete_all_for_workspace(workspace_id)
