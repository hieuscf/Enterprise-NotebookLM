# =============================================================================
# File: security.py
# Module/Service: API Gateway / Auth Middleware
# Layer: Adapter
# Purpose: Password hashing and JWT create/verify helpers for FR12 auth.
# Responsibilities:
#   - Hash and verify passwords (argon2)
#   - Issue and decode access/refresh JWTs (HS256 by default)
# Dependencies:
#   - argon2-cffi, PyJWT, app.core.config.Settings
# Public Exports:
#   - hash_password, verify_password
#   - create_access_token, create_refresh_token, decode_token
#   - TokenType, JWT_WORKSPACE_EMBED_LIMIT
# Database/Table: N/A
# Related Modules: app.services.auth, app.dependencies.auth
# Important Notes:
#   - If a user belongs to > JWT_WORKSPACE_EMBED_LIMIT workspaces, access tokens
#     embed only sub/exp/iat (plus type). Workspace RBAC must query DB, not the
#     token claim list (see create_access_token).
# =============================================================================

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import Settings

# Max workspace memberships embedded in an access token. Above this, omit the
# claim so tokens stay small; require_workspace_role / auth flows must hit DB.
JWT_WORKSPACE_EMBED_LIMIT = 20

_password_hasher = PasswordHasher()


class TokenType(StrEnum):
    access = "access"
    refresh = "refresh"


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def _now() -> datetime:
    return datetime.now(UTC)


def create_access_token(
    *,
    user_id: uuid.UUID,
    email: str,
    workspaces: list[dict[str, str]],
    settings: Settings,
) -> tuple[str, int]:
    """Return (token, expires_in_seconds).

    Decision (FR12): embed ``workspaces`` only when len(workspaces) <=
    JWT_WORKSPACE_EMBED_LIMIT. Otherwise embed only ``sub`` / ``exp`` / ``iat``
    (plus ``type`` / ``email`` for debugging convenience on ``sub`` path) so
    large tenants do not inflate every request token; workspace authorization
    then always resolves via ``workspace_members`` in the DB.
    """
    expires_in = settings.access_token_expire_minutes * 60
    now = _now()
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": TokenType.access.value,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    # When membership count exceeds the embed limit, only keep sub/exp/iat/type
    # so RBAC cannot rely on token claims and must query workspace_members.
    if len(workspaces) <= JWT_WORKSPACE_EMBED_LIMIT:
        payload["email"] = email
        payload["workspaces"] = workspaces
    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return token, expires_in


def create_refresh_token(
    *,
    user_id: uuid.UUID,
    settings: Settings,
) -> tuple[str, str, int]:
    """Return (token, jti, expires_in_seconds)."""
    expires_in = settings.refresh_token_expire_days * 24 * 60 * 60
    now = _now()
    jti = str(uuid.uuid4())
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": TokenType.refresh.value,
        "jti": jti,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return token, jti, expires_in


def decode_token(token: str, settings: Settings) -> dict[str, Any]:
    """Decode and verify JWT signature + expiry. Raises jwt.PyJWTError on failure."""
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
