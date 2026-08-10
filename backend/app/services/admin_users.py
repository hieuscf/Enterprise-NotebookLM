# =============================================================================
# File: admin_users.py
# Module/Service: Auth Service / Admin User Management (FR12)
# Layer: Service
# Purpose: Business logic for Platform Manage user create / list / permanent
#          delete (hard-delete users row — not soft-disable).
# Responsibilities:
#   - Create user with argon2 password hash; enforce unique normalized email
#   - List all enterprise users + memberships (Platform Manage directory)
#   - Permanently delete user with self-delete, last-admin, ownership, and
#     RESTRICT-FK guards; CASCADE relations handled by the database
# Dependencies:
#   - UserRepository, WorkspaceMemberRepository, WorkspaceRepository,
#     app.core.security.hash_password
# Public Exports:
#   - AdminUserService, AdminUserError
# Database/Table: users, workspace_members, workspaces, document_versions,
#   summaries, extractions, comparisons, reports
# Related Modules: app.api.admin_users, docs/Enterprise_notebooklm_openapi.yaml
# Important Notes:
#   - Authorization gate is require_platform_manage at the router (not here).
#   - Permanent delete is hard DELETE; status=disabled is NOT used.
#   - Audit events USER_CREATED / USER_DELETED: TODO when audit infra exists.
# =============================================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.enums import RoleName, UserStatus
from app.models.identity import User
from app.repositories.users import UserRepository
from app.repositories.workspace_members import WorkspaceMemberRepository
from app.repositories.workspaces import WorkspaceRepository


class AdminUserError(Exception):
    """Domain error mapped to HTTP by the presentation layer."""

    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class AdminMembershipView:
    workspace_id: uuid.UUID
    workspace_name: str
    role: RoleName
    joined_at: object


@dataclass(frozen=True, slots=True)
class AdminUserView:
    user_id: uuid.UUID
    email: str
    full_name: str
    memberships: list[AdminMembershipView]


def normalize_email(email: str) -> str:
    """Strip + lowercase — create-path convention (login still exact-match)."""
    return email.strip().lower()


class AdminUserService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._members = WorkspaceMemberRepository(session)
        self._workspaces = WorkspaceRepository(session)

    async def create_user(
        self,
        *,
        actor_id: uuid.UUID,
        email: str,
        password: str,
        full_name: str,
    ) -> User:
        del actor_id  # Authorization enforced by require_platform_manage.

        normalized = normalize_email(email)
        if not normalized:
            raise AdminUserError(
                "validation_error",
                "Email is required",
                status_code=422,
            )

        name = full_name.strip()
        if not name:
            raise AdminUserError(
                "validation_error",
                "Full name is required",
                status_code=422,
            )

        if await self._users.get_by_email_ci(normalized) is not None:
            raise AdminUserError(
                "email_exists",
                "An account with this email already exists.",
                status_code=409,
            )

        # Never log `password`. Hash server-side only (argon2).
        user = await self._users.create(
            email=normalized,
            password_hash=hash_password(password),
            full_name=name,
            status=UserStatus.active,
        )
        # TODO(audit): emit USER_CREATED when audit infrastructure exists.
        return user

    async def list_users(self, *, actor_id: uuid.UUID) -> list[AdminUserView]:
        del actor_id  # Authorization enforced by require_platform_manage.

        rows = await self._members.list_all_active_memberships()
        all_users = await self._users.list_all_active()

        by_user: dict[uuid.UUID, AdminUserView] = {}
        for row in rows:
            membership = AdminMembershipView(
                workspace_id=row.workspace_id,
                workspace_name=row.workspace_name,
                role=row.role,
                joined_at=row.joined_at,
            )
            existing = by_user.get(row.user_id)
            if existing is None:
                by_user[row.user_id] = AdminUserView(
                    user_id=row.user_id,
                    email=row.email,
                    full_name=row.full_name,
                    memberships=[membership],
                )
            else:
                existing.memberships.append(membership)

        for user in all_users:
            if user.id not in by_user:
                by_user[user.id] = AdminUserView(
                    user_id=user.id,
                    email=user.email,
                    full_name=user.full_name,
                    memberships=[],
                )

        return sorted(by_user.values(), key=lambda u: u.email.lower())

    async def delete_user_permanently(
        self,
        *,
        actor_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        if actor_id == user_id:
            raise AdminUserError(
                "self_delete",
                "You cannot delete your own account.",
                status_code=400,
            )

        user = await self._users.get_by_id(user_id)
        if user is None:
            raise AdminUserError("not_found", "User not found", status_code=404)

        target_workspace_ids = await self._members.list_active_workspace_ids(user_id)

        # Reuse workspace last-admin rule: hard-delete cascades memberships.
        for workspace_id in target_workspace_ids:
            role = await self._members.get_role_for_user(
                user_id=user_id, workspace_id=workspace_id
            )
            if role == RoleName.admin:
                admin_count = await self._members.count_active_admins(workspace_id)
                if admin_count <= 1:
                    raise AdminUserError(
                        "last_admin",
                        "This account cannot be deleted because it is the last "
                        "administrator of a workspace.",
                        status_code=409,
                    )

        # workspaces.owner_id is ON DELETE RESTRICT (incl. soft-deleted rows).
        if await self._workspaces.count_owned_by_user(user_id) > 0:
            raise AdminUserError(
                "owns_workspace",
                "This account cannot be deleted because it owns one or more workspaces.",
                status_code=409,
            )

        blockers = await self._users.list_restricting_dependency_tables(user_id)
        if blockers:
            raise AdminUserError(
                "has_dependent_content",
                "This account cannot be deleted because it has associated content "
                "that still references it.",
                status_code=409,
            )

        await self._users.delete(user)
        # TODO(audit): emit USER_DELETED when audit infrastructure exists.
