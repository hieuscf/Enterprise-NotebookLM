# =============================================================================
# File: auth.py
# Module/Service: API Gateway / Auth Middleware
# Layer: Presentation
# Purpose: Reusable FastAPI dependencies for JWT auth (FR12).
# Responsibilities:
#   - Provide get_auth_service and get_current_user (Bearer JWT)
# Dependencies:
#   - FastAPI security, app.services.auth, app.repositories.*, app.core.*
# Public Exports:
#   - get_auth_service, get_current_user, CurrentUser, bearer_scheme
# Database/Table: users
# Related Modules: app.api.auth; app.dependencies.rbac (require_workspace_role)
# Important Notes: Missing/invalid/expired Bearer → 401 Unauthorized.
# =============================================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.refresh_token_store import RefreshTokenStore, get_refresh_token_store
from app.core.security import TokenType, decode_token
from app.db.session import get_db_session
from app.models.enums import UserStatus
from app.repositories.users import UserRepository
from app.repositories.workspace_members import WorkspaceMemberRepository
from app.services.auth import AuthService

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class CurrentUser:
    id: uuid.UUID
    email: str
    full_name: str


def get_auth_service(
    session: AsyncSession = Depends(get_db_session),
    refresh_tokens: RefreshTokenStore = Depends(get_refresh_token_store),
    settings: Settings = Depends(get_settings),
) -> AuthService:
    return AuthService(
        users=UserRepository(session),
        members=WorkspaceMemberRepository(session),
        refresh_tokens=refresh_tokens,
        settings=settings,
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(credentials.credentials, settings)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if payload.get("type") != TokenType.access.value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )

    sub = payload.get("sub")
    try:
        user_id = uuid.UUID(str(sub))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = await UserRepository(session).get_by_id(user_id)
    if user is None or user.status != UserStatus.active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return CurrentUser(id=user.id, email=user.email, full_name=user.full_name)
