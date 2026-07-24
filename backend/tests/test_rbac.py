# =============================================================================
# File: test_rbac.py
# Module/Service: API Gateway / Auth Middleware
# Layer: Presentation
# Purpose: Unit/API tests for require_workspace_role (FR12 Step 2).
# Responsibilities:
#   - Non-member → 403; insufficient role → 403; sufficient role → 200/204
# Dependencies:
#   - pytest, httpx, app.main, app.dependencies.rbac
# Public Exports:
#   - N/A
# Database/Table: N/A (dependency overrides; no Postgres in CI)
# Related Modules: app.api.workspaces, app.dependencies.rbac
# Important Notes: Overrides get_current_user + membership lookup via fake repo.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from app.db.session import get_db_session
from app.dependencies.auth import CurrentUser, get_current_user
from app.dependencies.rbac import (
    WorkspaceAccess,
    require_workspace_admin,
    require_workspace_member,
)
from app.main import app
from app.models.enums import RoleName
from app.repositories.workspace_members import WorkspaceMemberRepository


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def workspace_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def current_user(user_id: uuid.UUID) -> CurrentUser:
    return CurrentUser(id=user_id, email="rbac@example.com", full_name="RBAC User")


def _override_user(user: CurrentUser):
    async def _dep() -> CurrentUser:
        return user

    return _dep


async def _fake_db_session():
    yield AsyncMock()


def _http_request(workspace_id: uuid.UUID, method: str = "GET") -> Request:
    path = f"/workspaces/{workspace_id}"
    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "scheme": "http",
        "server": ("test", 80),
        "client": ("test", 123),
        "headers": [],
        "query_string": b"",
        "state": {},
    }
    return Request(scope)


@pytest.fixture
async def client():
    app.dependency_overrides[get_db_session] = _fake_db_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_workspace_non_member_403(
    client: AsyncClient,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
) -> None:
    app.dependency_overrides[get_current_user] = _override_user(current_user)

    with patch.object(
        WorkspaceMemberRepository,
        "get_role_for_user",
        new=AsyncMock(return_value=None),
    ):
        response = await client.get(
            f"/workspaces/{workspace_id}",
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 403
    detail = response.json()["detail"]
    assert detail["code"] == "forbidden"
    assert "member" in detail["message"].lower()


@pytest.mark.asyncio
async def test_delete_workspace_viewer_forbidden(
    client: AsyncClient,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
) -> None:
    """Viewer is a member but not in admin allow-list → 403."""
    app.dependency_overrides[get_current_user] = _override_user(current_user)

    with patch.object(
        WorkspaceMemberRepository,
        "get_role_for_user",
        new=AsyncMock(return_value=RoleName.viewer),
    ):
        response = await client.delete(
            f"/workspaces/{workspace_id}",
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 403
    detail = response.json()["detail"]
    assert detail["code"] == "forbidden"
    assert "role" in detail["message"].lower()


@pytest.mark.asyncio
async def test_get_workspace_viewer_200(
    client: AsyncClient,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
) -> None:
    app.dependency_overrides[get_current_user] = _override_user(current_user)

    now = datetime.now(UTC)

    class FakeWorkspace:
        id = workspace_id
        name = "Demo WS"
        description = "rbac demo"
        created_at = now
        updated_at = now

    with (
        patch.object(
            WorkspaceMemberRepository,
            "get_role_for_user",
            new=AsyncMock(return_value=RoleName.viewer),
        ),
        patch(
            "app.api.workspaces.WorkspaceRepository.get_by_id",
            new=AsyncMock(return_value=FakeWorkspace()),
        ),
    ):
        response = await client.get(
            f"/workspaces/{workspace_id}",
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(workspace_id)
    assert body["name"] == "Demo WS"


@pytest.mark.asyncio
async def test_delete_workspace_admin_204(
    client: AsyncClient,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
) -> None:
    app.dependency_overrides[get_current_user] = _override_user(current_user)

    with patch.object(
        WorkspaceMemberRepository,
        "get_role_for_user",
        new=AsyncMock(return_value=RoleName.admin),
    ):
        response = await client.delete(
            f"/workspaces/{workspace_id}",
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 204


@pytest.mark.asyncio
async def test_require_workspace_role_sets_request_state(
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
) -> None:
    request = _http_request(workspace_id)

    with patch.object(
        WorkspaceMemberRepository,
        "get_role_for_user",
        new=AsyncMock(return_value=RoleName.editor),
    ):
        access = await require_workspace_member(
            request=request,
            workspaceId=workspace_id,
            current_user=current_user,
            session=AsyncMock(),
        )

    assert isinstance(access, WorkspaceAccess)
    assert access.role == RoleName.editor
    assert request.state.current_role == "editor"
    assert request.state.workspace_id == workspace_id


@pytest.mark.asyncio
async def test_editor_cannot_pass_admin_dependency(
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
) -> None:
    request = _http_request(workspace_id, method="DELETE")

    with patch.object(
        WorkspaceMemberRepository,
        "get_role_for_user",
        new=AsyncMock(return_value=RoleName.editor),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await require_workspace_admin(
                request=request,
                workspaceId=workspace_id,
                current_user=current_user,
                session=AsyncMock(),
            )

    assert exc_info.value.status_code == 403
