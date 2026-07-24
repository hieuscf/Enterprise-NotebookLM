# =============================================================================
# File: workspaces.py
# Module/Service: Workspace Service (RBAC demo)
# Layer: Presentation
# Purpose: Minimal workspace routes to prove require_workspace_role (FR12 Step 2).
# Responsibilities:
#   - GET /workspaces/{workspaceId} — any member (viewer+)
#   - DELETE /workspaces/{workspaceId} — admin only (RBAC gate; no real delete yet)
# Dependencies:
#   - app.dependencies.rbac, app.repositories.workspaces, app.schemas.workspaces
# Public Exports:
#   - router
# Database/Table: workspaces, workspace_members
# Related Modules: docs/Enterprise_notebooklm_openapi.yaml (/workspaces/{workspaceId})
# Important Notes:
#   - Full Workspace CRUD / member management is phase 1.3 — DELETE is RBAC-only
#     stub (204 when allowed) so middleware can be tested without mutating data.
# =============================================================================

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.dependencies.rbac import (
    WorkspaceAccess,
    require_workspace_admin,
    require_workspace_member,
)
from app.repositories.workspaces import WorkspaceRepository
from app.schemas.common import ErrorResponse
from app.schemas.workspaces import WorkspaceResponse

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


@router.get(
    "/{workspaceId}",
    response_model=WorkspaceResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    },
)
async def get_workspace(
    workspaceId: uuid.UUID,
    access: WorkspaceAccess = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db_session),
) -> WorkspaceResponse:
    """Chi tiết Workspace — allowed for admin | editor | viewer members."""
    del workspaceId  # validated via Path inside require_workspace_member
    workspace = await WorkspaceRepository(session).get_by_id(access.workspace_id)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorResponse(
                code="not_found",
                message="Workspace not found",
            ).model_dump(),
        )
    return WorkspaceResponse(
        id=workspace.id,
        name=workspace.name,
        description=workspace.description,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )


@router.delete(
    "/{workspaceId}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    },
)
async def delete_workspace(
    workspaceId: uuid.UUID,
    access: WorkspaceAccess = Depends(require_workspace_admin),
) -> None:
    """Xoá Workspace (Admin) — RBAC demo only.

    Phase 1.3 will implement cascade delete. Here we only prove that
    require_workspace_admin returns 403 for non-admins and 204 for admins.
    """
    del workspaceId, access
    return None
