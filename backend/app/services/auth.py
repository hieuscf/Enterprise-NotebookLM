# =============================================================================
# File: auth.py
# Module/Service: Auth Service
# Layer: Service
# Purpose: Login, refresh, and current-user business logic (FR12).
# Responsibilities:
#   - Authenticate email/password and issue AuthToken
#   - Rotate refresh tokens (single active jti)
#   - Build UserResponse with live workspace memberships from DB
# Dependencies:
#   - app.repositories.users, workspace_members
#   - app.core.security, app.core.refresh_token_store, app.core.config
# Public Exports:
#   - AuthService, AuthError
# Database/Table: users, workspace_members, roles
# Related Modules: app.api.auth, app.dependencies.auth
# Important Notes: /auth/me always queries DB for roles (never JWT-only).
# =============================================================================

from __future__ import annotations

import uuid

import jwt

from app.core.config import Settings
from app.core.refresh_token_store import RefreshTokenStore
from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.models.enums import UserStatus
from app.repositories.users import UserRepository
from app.repositories.workspace_members import WorkspaceMemberRepository
from app.schemas.auth import AuthToken
from app.schemas.users import UserResponse, WorkspaceMembership


class AuthError(Exception):
    """Raised for authentication failures that map to HTTP 401."""

    def __init__(self, detail: str = "Unauthorized") -> None:
        self.detail = detail
        super().__init__(detail)


class AuthService:
    def __init__(
        self,
        *,
        users: UserRepository,
        members: WorkspaceMemberRepository,
        refresh_tokens: RefreshTokenStore,
        settings: Settings,
    ) -> None:
        self._users = users
        self._members = members
        self._refresh_tokens = refresh_tokens
        self._settings = settings

    async def _workspace_claims(self, user_id: uuid.UUID) -> list[dict[str, str]]:
        rows = await self._members.list_for_user(user_id)
        return [{"workspace_id": str(row.workspace_id), "role": row.role.value} for row in rows]

    async def _issue_tokens(self, user_id: uuid.UUID, email: str) -> AuthToken:
        workspaces = await self._workspace_claims(user_id)
        access_token, expires_in = create_access_token(
            user_id=user_id,
            email=email,
            workspaces=workspaces,
            settings=self._settings,
        )
        refresh_token, jti, refresh_ttl = create_refresh_token(
            user_id=user_id,
            settings=self._settings,
        )
        self._refresh_tokens.save(user_id, jti, refresh_ttl)
        return AuthToken(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=expires_in,
        )

    async def login(self, email: str, password: str) -> AuthToken:
        user = await self._users.get_by_email(email)
        # Same message for missing user / bad password / disabled — avoid enumeration.
        if user is None or user.status != UserStatus.active:
            raise AuthError("Invalid email or password")
        if not verify_password(password, user.password_hash):
            raise AuthError("Invalid email or password")
        return await self._issue_tokens(user.id, user.email)

    async def refresh(self, refresh_token: str) -> AuthToken:
        try:
            payload = decode_token(refresh_token, self._settings)
        except jwt.PyJWTError as exc:
            raise AuthError("Invalid or expired refresh token") from exc

        if payload.get("type") != TokenType.refresh.value:
            raise AuthError("Invalid or expired refresh token")

        sub = payload.get("sub")
        jti = payload.get("jti")
        if not sub or not jti:
            raise AuthError("Invalid or expired refresh token")

        try:
            user_id = uuid.UUID(str(sub))
        except ValueError as exc:
            raise AuthError("Invalid or expired refresh token") from exc

        if not self._refresh_tokens.matches(user_id, str(jti)):
            raise AuthError("Invalid or expired refresh token")

        user = await self._users.get_by_id(user_id)
        if user is None or user.status != UserStatus.active:
            raise AuthError("Invalid or expired refresh token")

        # Rotate: replace active jti so the previous refresh token cannot be reused.
        return await self._issue_tokens(user.id, user.email)

    async def get_me(self, user_id: uuid.UUID) -> UserResponse:
        user = await self._users.get_by_id(user_id)
        if user is None or user.status != UserStatus.active:
            raise AuthError("Unauthorized")

        # Always join workspace_members at call time so role changes apply immediately.
        rows = await self._members.list_for_user(user_id)
        platform = user.platform_role.value if user.platform_role is not None else None
        return UserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            platform_role=platform,  # type: ignore[arg-type]
            workspaces=[
                WorkspaceMembership(workspace_id=row.workspace_id, role=row.role.value)
                for row in rows
            ],
        )
