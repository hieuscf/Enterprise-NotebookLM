# =============================================================================
# File: test_admin_users.py
# Module/Service: Auth Service / Admin User Management (FR12)
# Layer: Presentation
# Purpose: Unit tests for GET/POST/DELETE /admin/users.
# Responsibilities:
#   - Cover create success/duplicate/forbidden; delete self/last-admin/success
# Dependencies:
#   - pytest, httpx, app.main, app.services.admin_users
# Public Exports:
#   - N/A
# Database/Table: N/A (in-memory fakes; no Postgres in CI)
# Related Modules: app.api.admin_users
# Important Notes: Uses dependency_overrides — no live DB required.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import hash_password, verify_password
from app.dependencies.auth import CurrentUser, get_current_user
from app.dependencies.rbac import require_platform_manage
from app.main import app
from app.models.enums import PlatformRole, RoleName, UserStatus
from app.api.admin_users import get_admin_user_service
from app.services.admin_users import AdminUserError, AdminUserService, normalize_email


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeUser:
    def __init__(
        self,
        *,
        email: str,
        password: str = "secret",
        full_name: str = "Test User",
        status: UserStatus = UserStatus.active,
        user_id: uuid.UUID | None = None,
    ) -> None:
        self.id = user_id or uuid.uuid4()
        self.email = email
        self.password_hash = hash_password(password)
        self.full_name = full_name
        self.status = status


class FakeUserRepository:
    def __init__(self, users: list[FakeUser] | None = None) -> None:
        self._users = list(users or [])
        self.deleted_ids: list[uuid.UUID] = []

    def _index(self) -> None:
        pass

    async def get_by_email(self, email: str) -> FakeUser | None:
        for u in self._users:
            if u.email == email:
                return u
        return None

    async def get_by_email_ci(self, email: str) -> FakeUser | None:
        target = email.lower()
        for u in self._users:
            if u.email.lower() == target:
                return u
        return None

    async def get_by_id(self, user_id: uuid.UUID) -> FakeUser | None:
        for u in self._users:
            if u.id == user_id:
                return u
        return None

    async def create(
        self,
        *,
        email: str,
        password_hash: str,
        full_name: str,
        status: UserStatus = UserStatus.active,
    ) -> FakeUser:
        user = FakeUser(email=email, full_name=full_name, user_id=uuid.uuid4())
        user.password_hash = password_hash
        user.status = status
        self._users.append(user)
        return user

    async def delete(self, user: FakeUser) -> None:
        self.deleted_ids.append(user.id)
        self._users = [u for u in self._users if u.id != user.id]

    async def list_users_without_active_membership(self) -> list[FakeUser]:
        return []

    async def list_all_active(self) -> list[FakeUser]:
        return list(self._users)

    async def list_restricting_dependency_tables(self, user_id: uuid.UUID) -> list[str]:
        return []


class FakeMemberRepository:
    def __init__(
        self,
        *,
        admin_workspaces: dict[uuid.UUID, list[uuid.UUID]] | None = None,
        active_workspaces: dict[uuid.UUID, list[uuid.UUID]] | None = None,
        roles: dict[tuple[uuid.UUID, uuid.UUID], RoleName] | None = None,
        admin_counts: dict[uuid.UUID, int] | None = None,
    ) -> None:
        self._admin_workspaces = admin_workspaces or {}
        self._active_workspaces = active_workspaces or {}
        self._roles = roles or {}
        self._admin_counts = admin_counts or {}

    async def list_admin_workspace_ids(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        return list(self._admin_workspaces.get(user_id, []))

    async def list_active_workspace_ids(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        return list(self._active_workspaces.get(user_id, []))

    async def get_role_for_user(
        self, *, user_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> RoleName | None:
        return self._roles.get((user_id, workspace_id))

    async def count_active_admins(self, workspace_id: uuid.UUID) -> int:
        return self._admin_counts.get(workspace_id, 0)

    async def list_members_for_workspaces(self, workspace_ids: list[uuid.UUID]) -> list[Any]:
        return []

    async def list_all_active_memberships(self) -> list[Any]:
        return []


class FakeWorkspaceRepository:
    def __init__(self, owned_counts: dict[uuid.UUID, int] | None = None) -> None:
        self._owned_counts = owned_counts or {}

    async def count_owned_by_user(self, user_id: uuid.UUID) -> int:
        return self._owned_counts.get(user_id, 0)


def _service(
    *,
    users: FakeUserRepository,
    members: FakeMemberRepository,
    workspaces: FakeWorkspaceRepository | None = None,
) -> AdminUserService:
    svc = AdminUserService.__new__(AdminUserService)
    svc._session = None  # type: ignore[assignment]
    svc._users = users  # type: ignore[assignment]
    svc._members = members  # type: ignore[assignment]
    svc._workspaces = workspaces or FakeWorkspaceRepository()  # type: ignore[assignment]
    return svc


# ---------------------------------------------------------------------------
# Service unit tests
# ---------------------------------------------------------------------------


def test_normalize_email() -> None:
    assert normalize_email("  Admin@Example.COM ") == "admin@example.com"


@pytest.mark.asyncio
async def test_create_user_hashes_password() -> None:
    actor = uuid.uuid4()
    ws = uuid.uuid4()
    users = FakeUserRepository()
    members = FakeMemberRepository(admin_workspaces={actor: [ws]})
    svc = _service(users=users, members=members)

    created = await svc.create_user(
        actor_id=actor,
        email="New.User@Example.com",
        password="plain-secret",
        full_name="  New User  ",
    )
    assert created.email == "new.user@example.com"
    assert created.full_name == "New User"
    assert created.password_hash != "plain-secret"
    assert verify_password("plain-secret", created.password_hash)


@pytest.mark.asyncio
async def test_create_user_duplicate_email() -> None:
    actor = uuid.uuid4()
    ws = uuid.uuid4()
    existing = FakeUser(email="taken@example.com")
    users = FakeUserRepository([existing])
    members = FakeMemberRepository(admin_workspaces={actor: [ws]})
    svc = _service(users=users, members=members)

    with pytest.raises(AdminUserError) as exc:
        await svc.create_user(
            actor_id=actor,
            email="TAKEN@example.com",
            password="x",
            full_name="Dup",
        )
    assert exc.value.status_code == 409
    assert exc.value.code == "email_exists"


@pytest.mark.asyncio
async def test_delete_self_blocked() -> None:
    actor = uuid.uuid4()
    ws = uuid.uuid4()
    users = FakeUserRepository([FakeUser(email="me@example.com", user_id=actor)])
    members = FakeMemberRepository(admin_workspaces={actor: [ws]})
    svc = _service(users=users, members=members)

    with pytest.raises(AdminUserError) as exc:
        await svc.delete_user_permanently(actor_id=actor, user_id=actor)
    assert exc.value.code == "self_delete"
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_delete_last_admin_blocked() -> None:
    actor = uuid.uuid4()
    target = uuid.uuid4()
    ws = uuid.uuid4()
    users = FakeUserRepository([FakeUser(email="t@example.com", user_id=target)])
    members = FakeMemberRepository(
        admin_workspaces={actor: [ws]},
        active_workspaces={target: [ws]},
        roles={(target, ws): RoleName.admin},
        admin_counts={ws: 1},
    )
    svc = _service(users=users, members=members)

    with pytest.raises(AdminUserError) as exc:
        await svc.delete_user_permanently(actor_id=actor, user_id=target)
    assert exc.value.code == "last_admin"
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_delete_success() -> None:
    actor = uuid.uuid4()
    target = uuid.uuid4()
    ws = uuid.uuid4()
    users = FakeUserRepository([FakeUser(email="t@example.com", user_id=target)])
    members = FakeMemberRepository(
        admin_workspaces={actor: [ws]},
        active_workspaces={target: [ws]},
        roles={(target, ws): RoleName.editor},
        admin_counts={ws: 2},
    )
    svc = _service(users=users, members=members)

    await svc.delete_user_permanently(actor_id=actor, user_id=target)
    assert target in users.deleted_ids


# ---------------------------------------------------------------------------
# API tests (dependency overrides)
# ---------------------------------------------------------------------------


@pytest.fixture
def actor() -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        email="manage@example.com",
        full_name="Manage",
        platform_role=PlatformRole.manage,
    )


@pytest.mark.asyncio
async def test_api_create_and_delete(actor: CurrentUser) -> None:
    users = FakeUserRepository()
    members = FakeMemberRepository()
    svc = _service(users=users, members=members)

    async def _manage() -> CurrentUser:
        return actor

    app.dependency_overrides[get_current_user] = _manage
    app.dependency_overrides[require_platform_manage] = _manage
    app.dependency_overrides[get_admin_user_service] = lambda: svc

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/admin/users",
            json={
                "email": "newbie@example.com",
                "password": "pass1",
                "full_name": "Newbie",
            },
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["email"] == "newbie@example.com"
        assert body["full_name"] == "Newbie"
        assert "password" not in body
        assert "password_hash" not in body
        user_id = body["id"]

        target_uuid = uuid.UUID(user_id)
        members._active_workspaces[target_uuid] = []

        deleted = await client.delete(f"/admin/users/{user_id}")
        assert deleted.status_code == 204

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_forbidden_without_manage() -> None:
    actor = CurrentUser(
        id=uuid.uuid4(),
        email="ws-admin@example.com",
        full_name="WS Admin",
        platform_role=None,
    )

    async def _user() -> CurrentUser:
        return actor

    app.dependency_overrides[get_current_user] = _user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/admin/users")
        assert res.status_code == 403

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_duplicate_email_409(actor: CurrentUser) -> None:
    users = FakeUserRepository([FakeUser(email="dup@example.com")])
    members = FakeMemberRepository()
    svc = _service(users=users, members=members)

    async def _manage() -> CurrentUser:
        return actor

    app.dependency_overrides[require_platform_manage] = _manage
    app.dependency_overrides[get_admin_user_service] = lambda: svc

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/admin/users",
            json={
                "email": "dup@example.com",
                "password": "pass1",
                "full_name": "Dup",
            },
        )
        assert res.status_code == 409
        detail = res.json()["detail"]
        assert detail["code"] == "email_exists"

    app.dependency_overrides.clear()
