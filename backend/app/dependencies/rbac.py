# =============================================================================
# File: rbac.py
# Module/Service: API Gateway / Auth Middleware
# Layer: Presentation
# Purpose: FastAPI dependencies for Platform Manage + Workspace RBAC (FR12).
# Responsibilities:
#   - require_platform_manage — gate /admin/* (platform_role == manage)
#   - require_workspace_role(*allowed_roles) — gate /workspaces/{workspaceId}/*
#   - require_workspace_admin_or_manage — workspace admin OR platform manage
# Dependencies:
#   - FastAPI Request/Path, app.dependencies.auth.get_current_user
#   - app.domain.permissions, app.repositories.workspace_members
# Public Exports:
#   - WorkspaceAccess, require_workspace_role, require_platform_manage
#   - require_workspace_member, require_workspace_editor, require_workspace_admin
#   - require_workspace_admin_or_manage
# Database/Table: users.platform_role, workspace_members, roles
# Related Modules: System_Architecture (API Gateway / Auth Middleware)
# Important Notes:
#   - manage ≠ workspace admin; scopes are independent.
#   - Workspace role never grants /admin access.
# =============================================================================

from __future__ import annotations

import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, HTTPException, Path, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.dependencies.auth import CurrentUser, get_current_user
from app.domain.permissions import is_manage
from app.models.enums import RoleName
from app.repositories.workspace_members import WorkspaceMemberRepository
from app.schemas.common import ErrorResponse


@dataclass(frozen=True, slots=True)
class WorkspaceAccess:
    """Resolved membership after workspace RBAC gate passes."""

    workspace_id: uuid.UUID
    user_id: uuid.UUID
    role: RoleName


def _forbidden(message: str) -> HTTPException:
    """OpenAPI Forbidden → Error {code, message} nested under FastAPI detail."""
    body = ErrorResponse(code="forbidden", message=message)
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=body.model_dump(),
    )


async def require_platform_manage(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Gate for /admin/* — Platform Manage only (not workspace admin / owner)."""
    if not is_manage(current_user):
        raise _forbidden("Platform manage role required")
    return current_user


def require_workspace_role(
    *allowed_roles: str,
) -> Callable[..., Coroutine[Any, Any, WorkspaceAccess]]:
    """Factory: allow only listed workspace roles for the path workspaceId.

    Example (read — all members)::

        Depends(require_workspace_role("admin", "editor", "viewer"))

    Example (workspace-admin-only member role change)::

        Depends(require_workspace_role("admin"))

    Example (upload / mutate content — editor+)::

        Depends(require_workspace_role("admin", "editor"))
    """
    if not allowed_roles:
        raise ValueError("require_workspace_role requires at least one role")

    allowed = frozenset(allowed_roles)
    unknown = allowed - {r.value for r in RoleName}
    if unknown:
        raise ValueError(f"Unknown roles for RBAC allow-list: {sorted(unknown)}")

    async def _checker(
        request: Request,
        workspaceId: uuid.UUID = Path(..., description="Workspace UUID"),
        current_user: CurrentUser = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session),
    ) -> WorkspaceAccess:
        # Source of truth: workspace_members join roles (JWT may omit workspaces).
        role = await WorkspaceMemberRepository(session).get_role_for_user(
            user_id=current_user.id,
            workspace_id=workspaceId,
        )
        if role is None:
            raise _forbidden("Not a member of this workspace")
        if role.value not in allowed:
            raise _forbidden("Insufficient role for this workspace action")

        request.state.workspace_id = workspaceId
        request.state.current_role = role.value

        return WorkspaceAccess(
            workspace_id=workspaceId,
            user_id=current_user.id,
            role=role,
        )

    return _checker


def require_workspace_admin_or_manage() -> Callable[
    ..., Coroutine[Any, Any, WorkspaceAccess]
]:
    """Workspace Admin of this workspace, OR Platform Manage (enterprise override).

    Used for workspace update/delete from Admin Console without implying that
    manage becomes a workspace membership role.
    """

    async def _checker(
        request: Request,
        workspaceId: uuid.UUID = Path(..., description="Workspace UUID"),
        current_user: CurrentUser = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session),
    ) -> WorkspaceAccess:
        if is_manage(current_user):
            request.state.workspace_id = workspaceId
            request.state.current_role = "manage"
            # Synthetic access: Manage is not a workspace RoleName.
            return WorkspaceAccess(
                workspace_id=workspaceId,
                user_id=current_user.id,
                role=RoleName.admin,
            )

        role = await WorkspaceMemberRepository(session).get_role_for_user(
            user_id=current_user.id,
            workspace_id=workspaceId,
        )
        if role is None:
            raise _forbidden("Not a member of this workspace")
        if role != RoleName.admin:
            raise _forbidden("Insufficient role for this workspace action")

        request.state.workspace_id = workspaceId
        request.state.current_role = role.value
        return WorkspaceAccess(
            workspace_id=workspaceId,
            user_id=current_user.id,
            role=role,
        )

    return _checker


# Standard allow-lists. Prefer these over ad-hoc lists.
# Hierarchy is workspace-scoped only: admin > editor > viewer.
require_workspace_member = require_workspace_role("admin", "editor", "viewer")
require_workspace_editor = require_workspace_role("admin", "editor")
require_workspace_admin = require_workspace_role("admin")
# Bound once for Depends(...) identity stability in tests/overrides.
require_workspace_admin_or_manage_dep = require_workspace_admin_or_manage()
