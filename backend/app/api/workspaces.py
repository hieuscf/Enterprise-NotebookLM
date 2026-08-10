# =============================================================================
# File: workspaces.py
# Module/Service: Workspace Service
# Layer: Presentation
# Purpose: FastAPI routes for Workspace + member management (FR1 / UC10).
# Responsibilities:
#   - GET/POST /workspaces — list (member or Manage-all) + create (Manage)
#   - GET/PATCH/DELETE /workspaces/{workspaceId} — Workspace RBAC + soft-delete
#   - GET/POST /workspaces/{id}/members; PATCH/DELETE .../members/{userId}
# Dependencies:
#   - get_current_user, require_platform_manage, require_workspace_*_rl
#   - app.services.workspaces, app.services.members
# Public Exports:
#   - router
# Database/Table: workspaces, workspace_members, roles, users
# Related Modules: docs/Enterprise_notebooklm_openapi.yaml (/workspaces*)
# Important Notes:
#   - Soft-delete extends schema v2; GET list filters deleted_at IS NULL.
#   - POST create: Platform Manage only; creator auto workspace-admin.
#   - Member mutate: Workspace Admin of that workspace only (not Manage-as-role).
#   - 409 member_exists + last-admin 400 are documented extensions beyond OpenAPI.
# =============================================================================

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.dependencies.auth import CurrentUser, get_current_user
from app.dependencies.rate_limit import (
    require_workspace_admin_or_manage_rl,
    require_workspace_admin_rl,
    require_workspace_member_rl,
)
from app.dependencies.rbac import WorkspaceAccess, require_platform_manage
from app.domain.permissions import is_manage
from app.models.enums import RoleName
from app.models.identity import Workspace
from app.repositories.workspace_members import MemberDetailRow
from app.schemas.common import ErrorResponse
from app.schemas.members import (
    AddMemberRequest,
    UpdateMemberRoleRequest,
    WorkspaceMemberResponse,
)
from app.schemas.workspaces import (
    WorkspaceCreateRequest,
    WorkspaceListResponse,
    WorkspaceResponse,
    WorkspaceUpdateRequest,
)
from app.services.members import MemberError, WorkspaceMemberService
from app.services.workspaces import WorkspaceError, WorkspaceService

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


def get_workspace_service(
    session: AsyncSession = Depends(get_db_session),
) -> WorkspaceService:
    return WorkspaceService(session)


def get_member_service(
    session: AsyncSession = Depends(get_db_session),
) -> WorkspaceMemberService:
    return WorkspaceMemberService(session)


def _to_response(workspace: Workspace) -> WorkspaceResponse:
    return WorkspaceResponse(
        id=workspace.id,
        name=workspace.name,
        description=workspace.description,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )


def _member_response(row: MemberDetailRow) -> WorkspaceMemberResponse:
    return WorkspaceMemberResponse(
        user_id=row.user_id,
        email=row.email,
        role=row.role.value,  # type: ignore[arg-type]
        joined_at=row.joined_at,
    )


def _workspace_http_error(exc: WorkspaceError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail=ErrorResponse(code=exc.code, message=exc.message).model_dump(),
    )


def _member_http_error(exc: MemberError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail=ErrorResponse(code=exc.code, message=exc.message).model_dump(),
    )


@router.get(
    "",
    response_model=WorkspaceListResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    },
)
async def list_workspaces(
    page: int = Query(1, ge=1, description="Page number (OpenAPI PageParam)"),
    page_size: int = Query(
        20, ge=1, le=100, description="Page size (OpenAPI PageSizeParam, max 100)"
    ),
    current_user: CurrentUser = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceListResponse:
    """List workspaces: membership for ordinary users; all active for Manage."""
    if is_manage(current_user):
        result = await service.list_all(page=page, page_size=page_size)
    else:
        result = await service.list_for_user(
            current_user.id, page=page, page_size=page_size
        )
    return WorkspaceListResponse(
        items=[_to_response(w) for w in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@router.post(
    "",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    },
)
async def create_workspace(
    body: WorkspaceCreateRequest,
    current_user: CurrentUser = Depends(require_platform_manage),
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceResponse:
    """Tạo Workspace mới (Platform Manage). Creator becomes workspace admin."""
    try:
        workspace = await service.create(
            owner_id=current_user.id,
            name=body.name,
            description=body.description,
        )
    except WorkspaceError as exc:
        raise _workspace_http_error(exc) from exc
    return _to_response(workspace)


@router.get(
    "/{workspaceId}",
    response_model=WorkspaceResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def get_workspace(
    workspaceId: uuid.UUID,
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceResponse:
    """Chi tiết Workspace — allowed for admin | editor | viewer members."""
    del workspaceId  # validated via Path inside require_workspace_member
    try:
        workspace = await service.get(access.workspace_id)
    except WorkspaceError as exc:
        raise _workspace_http_error(exc) from exc
    return _to_response(workspace)


@router.patch(
    "/{workspaceId}",
    response_model=WorkspaceResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def update_workspace(
    workspaceId: uuid.UUID,
    body: WorkspaceUpdateRequest,
    access: WorkspaceAccess = Depends(require_workspace_admin_or_manage_rl),
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceResponse:
    """Cập nhật Workspace — Workspace Admin of this workspace, or Platform Manage."""
    del workspaceId
    try:
        workspace = await service.update(
            access.workspace_id,
            name=body.name,
            description=body.description,
        )
    except WorkspaceError as exc:
        raise _workspace_http_error(exc) from exc
    return _to_response(workspace)


@router.delete(
    "/{workspaceId}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def delete_workspace(
    workspaceId: uuid.UUID,
    access: WorkspaceAccess = Depends(require_workspace_admin_or_manage_rl),
    service: WorkspaceService = Depends(get_workspace_service),
) -> None:
    """Xoá Workspace (Workspace Admin or Manage) — soft-delete via deleted_at."""
    del workspaceId
    try:
        await service.soft_delete(access.workspace_id)
    except WorkspaceError as exc:
        raise _workspace_http_error(exc) from exc


# ---------------------------------------------------------------------------
# Members (UC10)
# ---------------------------------------------------------------------------


@router.get(
    "/{workspaceId}/members",
    response_model=list[WorkspaceMemberResponse],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def list_members(
    workspaceId: uuid.UUID,
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    service: WorkspaceMemberService = Depends(get_member_service),
) -> list[WorkspaceMemberResponse]:
    """Danh sách thành viên — mọi role (admin/editor/viewer) đều xem được."""
    del workspaceId
    try:
        rows = await service.list_members(access.workspace_id)
    except MemberError as exc:
        raise _member_http_error(exc) from exc
    return [_member_response(r) for r in rows]


@router.post(
    "/{workspaceId}/members",
    response_model=WorkspaceMemberResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def add_member(
    workspaceId: uuid.UUID,
    body: AddMemberRequest,
    access: WorkspaceAccess = Depends(require_workspace_admin_rl),
    service: WorkspaceMemberService = Depends(get_member_service),
) -> WorkspaceMemberResponse:
    """Thêm thành viên — admin only. 409 nếu user đã là member active."""
    del workspaceId
    try:
        row = await service.add_member(
            workspace_id=access.workspace_id,
            user_id=body.user_id,
            role=RoleName(body.role),
        )
    except MemberError as exc:
        raise _member_http_error(exc) from exc
    return _member_response(row)


@router.patch(
    "/{workspaceId}/members/{userId}",
    response_model=WorkspaceMemberResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def update_member_role(
    workspaceId: uuid.UUID,
    userId: uuid.UUID,
    body: UpdateMemberRoleRequest,
    access: WorkspaceAccess = Depends(require_workspace_admin_rl),
    service: WorkspaceMemberService = Depends(get_member_service),
) -> WorkspaceMemberResponse:
    """Đổi role thành viên — admin only; chặn hạ admin cuối cùng."""
    del workspaceId
    try:
        row = await service.update_role(
            workspace_id=access.workspace_id,
            user_id=userId,
            role=RoleName(body.role),
            actor_user_id=access.user_id,
        )
    except MemberError as exc:
        raise _member_http_error(exc) from exc
    return _member_response(row)


@router.delete(
    "/{workspaceId}/members/{userId}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    },
)
async def remove_member(
    workspaceId: uuid.UUID,
    userId: uuid.UUID,
    access: WorkspaceAccess = Depends(require_workspace_admin_rl),
    service: WorkspaceMemberService = Depends(get_member_service),
) -> None:
    """Xoá thành viên (soft-delete) — admin only; chặn xoá admin cuối cùng."""
    del workspaceId
    try:
        await service.remove_member(
            workspace_id=access.workspace_id,
            user_id=userId,
        )
    except MemberError as exc:
        raise _member_http_error(exc) from exc
