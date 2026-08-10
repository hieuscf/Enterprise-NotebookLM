# =============================================================================
# File: test_platform_rbac.py
# Module/Service: Auth Service / Platform + Workspace RBAC (FR12)
# Layer: Presentation
# Purpose: Integration-style tests for Manage vs Workspace Admin/Editor/Viewer.
# Responsibilities:
#   - /admin/* requires platform_role=manage
#   - Workspace Admin cannot access /admin
#   - Cross-workspace member isolation
#   - Domain helpers is_manage / is_workspace_admin
# Dependencies:
#   - pytest, httpx, app.main, app.domain.permissions
# Public Exports:
#   - N/A
# Database/Table: N/A (dependency overrides; no Postgres in CI)
# Related Modules: app.dependencies.rbac, app.api.admin*, app.api.workspaces
# Important Notes: Does not promote workspace admin to manage.
# =============================================================================

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.rate_limit import InMemoryWorkspaceRateLimiter, get_workspace_rate_limiter
from app.db.session import get_db_session
from app.dependencies.auth import CurrentUser, get_current_user
from app.domain.permissions import has_workspace_role, is_manage, is_workspace_admin
from app.main import app
from app.models.enums import PlatformRole, RoleName
from app.repositories.workspace_members import WorkspaceMemberRepository


@pytest.fixture
def manage_user() -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        email="manage@example.com",
        full_name="Manage",
        platform_role=PlatformRole.manage,
    )


@pytest.fixture
def workspace_admin() -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        email="ws-admin@example.com",
        full_name="WS Admin",
        platform_role=None,
    )


async def _fake_db_session():
    yield AsyncMock()


def test_domain_helpers() -> None:
    manage = CurrentUser(
        id=uuid.uuid4(),
        email="m@ex.com",
        full_name="M",
        platform_role=PlatformRole.manage,
    )
    ordinary = CurrentUser(
        id=uuid.uuid4(),
        email="o@ex.com",
        full_name="O",
        platform_role=None,
    )
    assert is_manage(manage) is True
    assert is_manage(ordinary) is False
    assert is_workspace_admin(RoleName.admin) is True
    assert is_workspace_admin(RoleName.editor) is False
    assert has_workspace_role(RoleName.viewer, "viewer", "editor") is True
    assert has_workspace_role(RoleName.viewer, "admin") is False


@pytest.mark.asyncio
async def test_admin_users_forbidden_for_workspace_admin(
    workspace_admin: CurrentUser,
) -> None:
    async def _user() -> CurrentUser:
        return workspace_admin

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db_session] = _fake_db_session

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/admin/users")
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "forbidden"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_observability_forbidden_for_workspace_admin(
    workspace_admin: CurrentUser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid.uuid4()

    async def _user() -> CurrentUser:
        return workspace_admin

    async def _role(self: Any, *, user_id: uuid.UUID, workspace_id: uuid.UUID) -> RoleName:
        return RoleName.admin

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db_session] = _fake_db_session
    monkeypatch.setattr(WorkspaceMemberRepository, "get_role_for_user", _role)

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/admin/workspaces/{workspace_id}/query-logs")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_observability_allowed_for_manage(
    manage_user: CurrentUser,
) -> None:
    workspace_id = uuid.uuid4()

    class FakeService:
        async def list_logs(self, **kwargs: Any) -> list[Any]:
            assert kwargs["workspace_id"] == workspace_id
            return []

    async def _user() -> CurrentUser:
        return manage_user

    from app.api.admin import get_query_logs_service

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db_session] = _fake_db_session
    app.dependency_overrides[get_query_logs_service] = lambda: FakeService()

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/admin/workspaces/{workspace_id}/query-logs")
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_workspace_requires_manage(
    workspace_admin: CurrentUser,
) -> None:
    async def _user() -> CurrentUser:
        return workspace_admin

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db_session] = _fake_db_session

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/workspaces", json={"name": "New WS"})
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_cross_workspace_member_patch_isolation(
    workspace_admin: CurrentUser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Workspace Admin of Finance cannot manage HR members (viewer there → 403)."""
    from starlette.requests import Request

    from app.dependencies.rbac import require_workspace_admin

    finance = uuid.uuid4()
    hr = uuid.uuid4()
    target = uuid.uuid4()

    async def _user() -> CurrentUser:
        return workspace_admin

    async def _role(self: Any, *, user_id: uuid.UUID, workspace_id: uuid.UUID) -> RoleName | None:
        if workspace_id == finance:
            return RoleName.admin
        if workspace_id == hr:
            return RoleName.viewer
        return None

    monkeypatch.setattr(WorkspaceMemberRepository, "get_role_for_user", _role)

    async def _db():
        return AsyncMock()

    session = AsyncMock()

    # Direct dependency checks — no full member service stack.
    hr_req = Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "PATCH",
            "path": f"/workspaces/{hr}/members/{target}",
            "raw_path": f"/workspaces/{hr}/members/{target}".encode(),
            "root_path": "",
            "scheme": "http",
            "server": ("test", 80),
            "client": ("test", 123),
            "headers": [],
            "query_string": b"",
            "state": {},
        }
    )
    with pytest.raises(Exception) as hr_exc:
        await require_workspace_admin(
            request=hr_req,
            workspaceId=hr,
            current_user=workspace_admin,
            session=session,
        )
    assert getattr(hr_exc.value, "status_code", None) == 403

    finance_req = Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "PATCH",
            "path": f"/workspaces/{finance}/members/{target}",
            "raw_path": f"/workspaces/{finance}/members/{target}".encode(),
            "root_path": "",
            "scheme": "http",
            "server": ("test", 80),
            "client": ("test", 123),
            "headers": [],
            "query_string": b"",
            "state": {},
        }
    )
    access = await require_workspace_admin(
        request=finance_req,
        workspaceId=finance,
        current_user=workspace_admin,
        session=session,
    )
    assert access.role == RoleName.admin
    assert access.workspace_id == finance

    # Also confirm HTTP path rejects HR.
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db_session] = _fake_db_session
    app.dependency_overrides[get_workspace_rate_limiter] = (
        lambda: InMemoryWorkspaceRateLimiter()
    )
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            hr_resp = await client.patch(
                f"/workspaces/{hr}/members/{target}",
                json={"role": "editor"},
            )
        assert hr_resp.status_code == 403
    finally:
        app.dependency_overrides.clear()
