# =============================================================================
# File: rbac.py
# Module/Service: API Gateway / Auth Middleware
# Layer: Presentation
# Purpose: FastAPI dependency factory for workspace-scoped RBAC (FR12).
# Responsibilities:
#   - require_workspace_role(*allowed_roles) — gate routes with {workspaceId}
#   - Resolve role from workspace_members (DB), never trust JWT claims alone
#   - Attach current_role / workspace_id onto request.state for downstream use
# Dependencies:
#   - FastAPI Request/Path, app.dependencies.auth.get_current_user
#   - app.repositories.workspace_members
# Public Exports:
#   - WorkspaceAccess, require_workspace_role
#   - require_workspace_member, require_workspace_editor, require_workspace_admin
# Database/Table: workspace_members, roles
# Related Modules: System_Architecture (API Gateway / Auth Middleware), app.api.workspaces
# Important Notes:
#   - Not a member → 403 Forbidden; role not in allow-list → 403.
#   - Callers pass explicit allow-lists; use module-level helpers for hierarchy:
#     admin > editor > viewer (admin implies editor/write; all three for read).
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
from app.models.enums import RoleName
from app.repositories.workspace_members import WorkspaceMemberRepository
from app.schemas.common import ErrorResponse


@dataclass(frozen=True, slots=True)
class WorkspaceAccess:
    """Resolved membership after RBAC gate passes."""

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


def require_workspace_role(
    *allowed_roles: str,
) -> Callable[..., Coroutine[Any, Any, WorkspaceAccess]]:
    """Factory: allow only listed roles for the path workspaceId.

    Example (read — all members)::

        Depends(require_workspace_role("admin", "editor", "viewer"))

    Example (admin-only delete / member role change)::

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

        # Expose for handlers / later middleware (e.g. rate limit by workspace).
        request.state.workspace_id = workspaceId
        request.state.current_role = role.value

        return WorkspaceAccess(
            workspace_id=workspaceId,
            user_id=current_user.id,
            role=role,
        )

    return _checker


# Standard allow-lists for upcoming routers (1.3+). Prefer these over ad-hoc lists.
require_workspace_member = require_workspace_role("admin", "editor", "viewer")
require_workspace_editor = require_workspace_role("admin", "editor")
require_workspace_admin = require_workspace_role("admin")
