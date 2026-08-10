# =============================================================================
# File: admin_users.py
# Module/Service: Auth Service / Admin User Management (FR12)
# Layer: Presentation
# Purpose: Platform Manage endpoints for enterprise user account create / list /
#          permanent delete.
# Responsibilities:
#   - GET  /admin/users
#   - POST /admin/users
#   - DELETE /admin/users/{userId}
# Dependencies:
#   - require_platform_manage, AdminUserService, get_db_session
# Public Exports:
#   - router
# Database/Table: users, workspace_members, roles, workspaces
# Related Modules: docs/Enterprise_notebooklm_openapi.yaml §Admin/Users
# Important Notes:
#   - Hard-delete only (not status=disabled). Self-delete blocked.
#   - Authorization: platform_role == manage only (not workspace admin).
# =============================================================================

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.dependencies.auth import CurrentUser
from app.dependencies.rbac import require_platform_manage
from app.schemas.admin_users import (
    AdminUserListItem,
    AdminUserListResponse,
    AdminUserMembership,
    AdminUserResponse,
    CreateAdminUserRequest,
)
from app.schemas.common import ErrorResponse
from app.services.admin_users import AdminUserError, AdminUserService

router = APIRouter(prefix="/admin/users", tags=["Admin/Users"])


def get_admin_user_service(
    session: AsyncSession = Depends(get_db_session),
) -> AdminUserService:
    return AdminUserService(session)


def _http_error(exc: AdminUserError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail=ErrorResponse(code=exc.code, message=exc.message).model_dump(),
    )


@router.get(
    "",
    response_model=AdminUserListResponse,
    summary="List all enterprise users (Manage)",
    operation_id="listAdminUsers",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    },
)
async def list_admin_users(
    current_user: CurrentUser = Depends(require_platform_manage),
    service: AdminUserService = Depends(get_admin_user_service),
) -> AdminUserListResponse:
    try:
        views = await service.list_users(actor_id=current_user.id)
    except AdminUserError as exc:
        raise _http_error(exc) from exc

    return AdminUserListResponse(
        items=[
            AdminUserListItem(
                user_id=v.user_id,
                email=v.email,
                full_name=v.full_name,
                memberships=[
                    AdminUserMembership(
                        workspace_id=m.workspace_id,
                        workspace_name=m.workspace_name,
                        role=m.role.value,  # type: ignore[arg-type]
                        joined_at=m.joined_at,  # type: ignore[arg-type]
                    )
                    for m in v.memberships
                ],
            )
            for v in views
        ]
    )


@router.post(
    "",
    response_model=AdminUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new enterprise user account (Manage)",
    operation_id="createAdminUser",
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
)
async def create_admin_user(
    body: CreateAdminUserRequest,
    current_user: CurrentUser = Depends(require_platform_manage),
    service: AdminUserService = Depends(get_admin_user_service),
) -> AdminUserResponse:
    try:
        user = await service.create_user(
            actor_id=current_user.id,
            email=str(body.email),
            password=body.password,
            full_name=body.full_name,
        )
    except AdminUserError as exc:
        raise _http_error(exc) from exc

    return AdminUserResponse(id=user.id, email=user.email, full_name=user.full_name)


@router.delete(
    "/{userId}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Permanently delete a user account (Manage)",
    operation_id="deleteAdminUser",
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
)
async def delete_admin_user(
    userId: uuid.UUID,
    current_user: CurrentUser = Depends(require_platform_manage),
    service: AdminUserService = Depends(get_admin_user_service),
) -> None:
    try:
        await service.delete_user_permanently(
            actor_id=current_user.id,
            user_id=userId,
        )
    except AdminUserError as exc:
        raise _http_error(exc) from exc
