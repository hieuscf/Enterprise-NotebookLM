# =============================================================================
# File: test_auth.py
# Module/Service: Auth Service
# Layer: Presentation
# Purpose: Unit tests for /auth/login, /auth/refresh, /auth/me (FR12 Step 1).
# Responsibilities:
#   - Cover login success/failure, refresh valid/expired, /me with/without token
# Dependencies:
#   - pytest, httpx, app.main, app.services.auth, app.core.security
# Public Exports:
#   - N/A
# Database/Table: N/A (in-memory fakes; no Postgres in CI)
# Related Modules: app.api.auth, app.dependencies.auth
# Important Notes: Uses dependency_overrides — no live DB/Redis required.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.core.refresh_token_store import InMemoryRefreshTokenStore
from app.core.security import (
    JWT_WORKSPACE_EMBED_LIMIT,
    TokenType,
    create_access_token,
    hash_password,
    verify_password,
)
from app.dependencies.auth import CurrentUser, get_auth_service, get_current_user
from app.main import app
from app.models.enums import RoleName, UserStatus
from app.repositories.workspace_members import MembershipRow
from app.schemas.users import UserResponse, WorkspaceMembership
from app.services.auth import AuthError, AuthService

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeUser:
    def __init__(
        self,
        *,
        email: str,
        password: str,
        full_name: str = "Test User",
        status: UserStatus = UserStatus.active,
        user_id: uuid.UUID | None = None,
        platform_role: object | None = None,
    ) -> None:
        self.id = user_id or uuid.uuid4()
        self.email = email
        self.password_hash = hash_password(password)
        self.full_name = full_name
        self.status = status
        self.platform_role = platform_role


class FakeUserRepository:
    def __init__(self, users: list[FakeUser]) -> None:
        self._by_email = {u.email: u for u in users}
        self._by_id = {u.id: u for u in users}

    async def get_by_email(self, email: str) -> FakeUser | None:
        return self._by_email.get(email)

    async def get_by_id(self, user_id: uuid.UUID) -> FakeUser | None:
        return self._by_id.get(user_id)


class FakeMemberRepository:
    def __init__(self, memberships: dict[uuid.UUID, list[MembershipRow]] | None = None) -> None:
        self._memberships = memberships or {}

    async def list_for_user(self, user_id: uuid.UUID) -> list[MembershipRow]:
        return list(self._memberships.get(user_id, []))


def _settings(**overrides: Any) -> Settings:
    base = dict(
        app_env="test",
        jwt_secret_key="test-secret-key-not-for-production",
        jwt_algorithm="HS256",
        access_token_expire_minutes=30,
        refresh_token_expire_days=7,
    )
    base.update(overrides)
    return Settings(**base)


def _auth_service(
    user: FakeUser,
    *,
    store: InMemoryRefreshTokenStore | None = None,
    memberships: list[MembershipRow] | None = None,
    settings: Settings | None = None,
) -> AuthService:
    return AuthService(
        users=FakeUserRepository([user]),  # type: ignore[arg-type]
        members=FakeMemberRepository({user.id: memberships or []}),  # type: ignore[arg-type]
        refresh_tokens=store or InMemoryRefreshTokenStore(),
        settings=settings or _settings(),
    )


# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("correct-horse")
    assert verify_password("correct-horse", hashed)
    assert not verify_password("wrong", hashed)


def test_access_token_omits_workspaces_when_over_limit() -> None:
    settings = _settings()
    user_id = uuid.uuid4()
    many = [
        {"workspace_id": str(uuid.uuid4()), "role": "viewer"}
        for _ in range(JWT_WORKSPACE_EMBED_LIMIT + 1)
    ]
    token, _ = create_access_token(
        user_id=user_id,
        email="a@example.com",
        workspaces=many,
        settings=settings,
    )
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    assert payload["sub"] == str(user_id)
    assert "workspaces" not in payload
    assert "email" not in payload


# ---------------------------------------------------------------------------
# AuthService unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_success_returns_auth_token() -> None:
    user = FakeUser(email="ok@example.com", password="secret123")
    ws = uuid.uuid4()
    service = _auth_service(
        user,
        memberships=[MembershipRow(workspace_id=ws, role=RoleName.editor)],
    )
    token = await service.login("ok@example.com", "secret123")
    assert token.token_type == "bearer"
    assert token.expires_in == 30 * 60
    assert token.access_token
    assert token.refresh_token
    payload = jwt.decode(
        token.access_token,
        service._settings.jwt_secret_key,
        algorithms=[service._settings.jwt_algorithm],
    )
    assert payload["sub"] == str(user.id)
    assert payload["workspaces"] == [{"workspace_id": str(ws), "role": "editor"}]


@pytest.mark.asyncio
async def test_login_wrong_password_raises() -> None:
    user = FakeUser(email="ok@example.com", password="secret123")
    service = _auth_service(user)
    with pytest.raises(AuthError):
        await service.login("ok@example.com", "nope")


@pytest.mark.asyncio
async def test_login_unknown_email_raises() -> None:
    user = FakeUser(email="ok@example.com", password="secret123")
    service = _auth_service(user)
    with pytest.raises(AuthError):
        await service.login("missing@example.com", "secret123")


@pytest.mark.asyncio
async def test_refresh_valid_rotates_tokens() -> None:
    user = FakeUser(email="ok@example.com", password="secret123")
    store = InMemoryRefreshTokenStore()
    service = _auth_service(user, store=store)
    original = await service.login("ok@example.com", "secret123")
    refreshed = await service.refresh(original.refresh_token)
    assert refreshed.refresh_token != original.refresh_token
    assert refreshed.access_token  # newly issued (may match if same-second iat/exp)
    # Old refresh jti no longer accepted (rotated)
    with pytest.raises(AuthError):
        await service.refresh(original.refresh_token)


@pytest.mark.asyncio
async def test_refresh_expired_raises() -> None:
    user = FakeUser(email="ok@example.com", password="secret123")
    settings = _settings()
    store = InMemoryRefreshTokenStore()
    service = _auth_service(user, store=store, settings=settings)

    now = datetime.now(UTC)
    jti = str(uuid.uuid4())
    expired = jwt.encode(
        {
            "sub": str(user.id),
            "type": TokenType.refresh.value,
            "jti": jti,
            "iat": now - timedelta(days=10),
            "exp": now - timedelta(seconds=1),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    store.save(user.id, jti, ttl_seconds=60)
    with pytest.raises(AuthError):
        await service.refresh(expired)


@pytest.mark.asyncio
async def test_get_me_loads_workspaces_from_memberships() -> None:
    user = FakeUser(email="ok@example.com", password="secret123", full_name="Ada")
    ws = uuid.uuid4()
    service = _auth_service(
        user,
        memberships=[MembershipRow(workspace_id=ws, role=RoleName.admin)],
    )
    me = await service.get_me(user.id)
    assert me == UserResponse(
        id=user.id,
        email="ok@example.com",
        full_name="Ada",
        platform_role=None,
        workspaces=[WorkspaceMembership(workspace_id=ws, role="admin")],
    )


# ---------------------------------------------------------------------------
# API endpoint tests (dependency overrides)
# ---------------------------------------------------------------------------


@pytest.fixture
def api_user() -> FakeUser:
    return FakeUser(email="api@example.com", password="api-secret")


@pytest.fixture
async def api_client(api_user: FakeUser, refresh_store: InMemoryRefreshTokenStore):
    ws = uuid.uuid4()
    settings = _settings()
    service = _auth_service(
        api_user,
        store=refresh_store,
        memberships=[MembershipRow(workspace_id=ws, role=RoleName.viewer)],
        settings=settings,
    )

    async def _override_auth_service() -> AuthService:
        return service

    async def _override_current_user() -> CurrentUser:
        return CurrentUser(
            id=api_user.id,
            email=api_user.email,
            full_name=api_user.full_name,
        )

    app.dependency_overrides[get_auth_service] = _override_auth_service
    # get_current_user overridden only where needed per-test
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, service, api_user, settings, ws, _override_current_user
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_login_success(api_client) -> None:
    client, _service, user, _settings, _ws, _ = api_client
    response = await client.post(
        "/auth/login",
        json={"email": user.email, "password": "api-secret"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert "access_token" in body and "refresh_token" in body
    assert body["expires_in"] == 30 * 60


@pytest.mark.asyncio
async def test_api_login_wrong_password(api_client) -> None:
    client, _service, user, _settings, _ws, _ = api_client
    response = await client.post(
        "/auth/login",
        json={"email": user.email, "password": "wrong"},
    )
    assert response.status_code == 401
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_api_refresh_valid(api_client) -> None:
    client, service, user, _settings, _ws, _ = api_client
    login = await service.login(user.email, "api-secret")
    response = await client.post(
        "/auth/refresh",
        json={"refresh_token": login.refresh_token},
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


@pytest.mark.asyncio
async def test_api_refresh_expired(api_client) -> None:
    client, _service, user, settings, _ws, _ = api_client
    now = datetime.now(UTC)
    expired = jwt.encode(
        {
            "sub": str(user.id),
            "type": TokenType.refresh.value,
            "jti": str(uuid.uuid4()),
            "iat": now - timedelta(days=2),
            "exp": now - timedelta(hours=1),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    response = await client.post("/auth/refresh", json={"refresh_token": expired})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_api_me_with_token(api_client) -> None:
    client, _service, user, _settings, ws, override_current_user = api_client
    app.dependency_overrides[get_current_user] = override_current_user
    response = await client.get(
        "/auth/me",
        headers={"Authorization": "Bearer unused-because-overridden"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == user.email
    assert body["full_name"] == user.full_name
    assert body["platform_role"] is None
    assert body["workspaces"] == [{"workspace_id": str(ws), "role": "viewer"}]


@pytest.mark.asyncio
async def test_api_me_without_token() -> None:
    app.dependency_overrides.clear()
    # Ensure get_current_user runs for real (no Bearer → 401); auth service unused
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/auth/me")
    assert response.status_code == 401
