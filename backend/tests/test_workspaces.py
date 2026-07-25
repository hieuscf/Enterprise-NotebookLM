# =============================================================================
# File: test_workspaces.py
# Module/Service: Workspace Service
# Layer: Presentation
# Purpose: Unit/API tests for Workspace CRUD (FR1 Step 1.3).
# Responsibilities:
#   - Creator auto-admin on POST; outsider GET → 403
#   - PATCH/DELETE require admin; soft-delete hides from list
# Dependencies:
#   - pytest, httpx, app.main, app.services.workspaces
# Public Exports:
#   - N/A
# Database/Table: N/A (fakes + dependency overrides; no Postgres in CI)
# Related Modules: app.api.workspaces, app.services.workspaces
# Important Notes: Soft-delete + auto-admin decisions documented in service.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.rate_limit import InMemoryWorkspaceRateLimiter, get_workspace_rate_limiter
from app.db.session import get_db_session
from app.dependencies.auth import CurrentUser, get_current_user
from app.main import app
from app.models.enums import RoleName
from app.models.identity import Role, Workspace
from app.repositories.roles import RoleRepository
from app.repositories.workspace_members import WorkspaceMemberRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.workspaces import WorkspaceError, WorkspaceService

# ---------------------------------------------------------------------------
# Fixtures / fakes
# ---------------------------------------------------------------------------


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def other_user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def workspace_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def current_user(user_id: uuid.UUID) -> CurrentUser:
    return CurrentUser(id=user_id, email="owner@example.com", full_name="Owner")


@pytest.fixture
def outsider(other_user_id: uuid.UUID) -> CurrentUser:
    return CurrentUser(id=other_user_id, email="out@example.com", full_name="Outsider")


def _override_user(user: CurrentUser):
    async def _dep() -> CurrentUser:
        return user

    return _dep


async def _fake_db_session():
    yield AsyncMock()


def _make_workspace(
    *,
    workspace_id: uuid.UUID | None = None,
    owner_id: uuid.UUID | None = None,
    name: str = "Demo WS",
    description: str | None = "desc",
    deleted_at: datetime | None = None,
) -> Workspace:
    now = datetime.now(UTC)
    ws = Workspace(
        id=workspace_id or uuid.uuid4(),
        name=name,
        description=description,
        owner_id=owner_id or uuid.uuid4(),
        created_at=now,
        updated_at=now,
        deleted_at=deleted_at,
    )
    return ws


@pytest.fixture
async def client():
    app.dependency_overrides[get_db_session] = _fake_db_session
    app.dependency_overrides[get_workspace_rate_limiter] = lambda: InMemoryWorkspaceRateLimiter()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Service unit tests (in-memory fake repos)
# ---------------------------------------------------------------------------


class FakeWorkspaceRepo:
    def __init__(self) -> None:
        self.by_id: dict[uuid.UUID, Workspace] = {}
        self.memberships: dict[uuid.UUID, set[uuid.UUID]] = {}  # user -> workspace ids

    async def get_by_id(
        self, workspace_id: uuid.UUID, *, include_deleted: bool = False
    ) -> Workspace | None:
        ws = self.by_id.get(workspace_id)
        if ws is None:
            return None
        if not include_deleted and ws.deleted_at is not None:
            return None
        return ws

    async def list_for_member(
        self, user_id: uuid.UUID, *, page: int, page_size: int
    ) -> tuple[list[Workspace], int]:
        ids = self.memberships.get(user_id, set())
        items = [self.by_id[i] for i in ids if i in self.by_id and self.by_id[i].deleted_at is None]
        items.sort(key=lambda w: w.created_at, reverse=True)
        total = len(items)
        start = (page - 1) * page_size
        return items[start : start + page_size], total

    async def create(self, *, name: str, description: str | None, owner_id: uuid.UUID) -> Workspace:
        ws = _make_workspace(owner_id=owner_id, name=name, description=description)
        self.by_id[ws.id] = ws
        return ws

    async def update(
        self,
        workspace: Workspace,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> Workspace:
        if name is not None:
            workspace.name = name
        if description is not None:
            workspace.description = description
        return workspace

    async def soft_delete(self, workspace: Workspace) -> None:
        workspace.deleted_at = datetime.now(UTC)


class FakeMemberRepo:
    def __init__(self, workspaces: FakeWorkspaceRepo) -> None:
        self._ws = workspaces
        self.added: list[dict[str, Any]] = []
        self.soft_deleted_workspaces: list[uuid.UUID] = []

    async def add_member(
        self, *, workspace_id: uuid.UUID, user_id: uuid.UUID, role_id: uuid.UUID
    ) -> MagicMock:
        self.added.append({"workspace_id": workspace_id, "user_id": user_id, "role_id": role_id})
        self._ws.memberships.setdefault(user_id, set()).add(workspace_id)
        return MagicMock()

    async def soft_delete_all_for_workspace(self, workspace_id: uuid.UUID) -> int:
        self.soft_deleted_workspaces.append(workspace_id)
        # Drop memberships pointing at this workspace so list_for_member stays consistent.
        for _uid, ids in list(self._ws.memberships.items()):
            ids.discard(workspace_id)
        return 1


class FakeRoleRepo:
    def __init__(self) -> None:
        self.admin = Role(id=uuid.uuid4(), name=RoleName.admin, permissions={})

    async def get_by_name(self, name: RoleName) -> Role | None:
        if name == RoleName.admin:
            return self.admin
        return None


def _service_with_fakes() -> (
    tuple[WorkspaceService, FakeWorkspaceRepo, FakeMemberRepo, FakeRoleRepo]
):
    ws_repo = FakeWorkspaceRepo()
    member_repo = FakeMemberRepo(ws_repo)
    role_repo = FakeRoleRepo()
    service = WorkspaceService(AsyncMock())
    service._workspaces = ws_repo  # type: ignore[method-assign]
    service._members = member_repo  # type: ignore[method-assign]
    service._roles = role_repo  # type: ignore[method-assign]
    return service, ws_repo, member_repo, role_repo


@pytest.mark.asyncio
async def test_create_adds_creator_as_admin(user_id: uuid.UUID) -> None:
    service, _, members, roles = _service_with_fakes()

    ws = await service.create(owner_id=user_id, name="Eng", description="dept")

    assert ws.name == "Eng"
    assert len(members.added) == 1
    assert members.added[0]["user_id"] == user_id
    assert members.added[0]["workspace_id"] == ws.id
    assert members.added[0]["role_id"] == roles.admin.id


@pytest.mark.asyncio
async def test_list_excludes_soft_deleted(user_id: uuid.UUID) -> None:
    service, ws_repo, members, _ = _service_with_fakes()
    active = await service.create(owner_id=user_id, name="Keep", description=None)
    gone = await service.create(owner_id=user_id, name="Gone", description=None)
    await service.soft_delete(gone.id)

    page = await service.list_for_user(user_id, page=1, page_size=20)

    assert page.total == 1
    assert page.items[0].id == active.id
    assert ws_repo.by_id[gone.id].deleted_at is not None
    assert len(members.added) == 2


@pytest.mark.asyncio
async def test_get_soft_deleted_raises_not_found(user_id: uuid.UUID) -> None:
    service, _, _, _ = _service_with_fakes()
    ws = await service.create(owner_id=user_id, name="X", description=None)
    await service.soft_delete(ws.id)

    with pytest.raises(WorkspaceError) as exc_info:
        await service.get(ws.id)
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_workspace_201(
    client: AsyncClient,
    current_user: CurrentUser,
    user_id: uuid.UUID,
) -> None:
    app.dependency_overrides[get_current_user] = _override_user(current_user)
    created = _make_workspace(owner_id=user_id, name="New WS")

    from unittest.mock import patch

    with (
        patch.object(
            RoleRepository,
            "get_by_name",
            new=AsyncMock(return_value=Role(id=uuid.uuid4(), name=RoleName.admin, permissions={})),
        ),
        patch.object(
            WorkspaceRepository,
            "create",
            new=AsyncMock(return_value=created),
        ),
        patch.object(
            WorkspaceMemberRepository,
            "add_member",
            new=AsyncMock(),
        ),
    ):
        response = await client.post(
            "/workspaces",
            json={"name": "New WS", "description": "desc"},
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == str(created.id)
    assert body["name"] == "New WS"


@pytest.mark.asyncio
async def test_get_workspace_outsider_403(
    client: AsyncClient,
    outsider: CurrentUser,
    workspace_id: uuid.UUID,
) -> None:
    app.dependency_overrides[get_current_user] = _override_user(outsider)

    from unittest.mock import patch

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
    assert response.json()["detail"]["code"] == "forbidden"


@pytest.mark.asyncio
async def test_patch_workspace_viewer_403(
    client: AsyncClient,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
) -> None:
    app.dependency_overrides[get_current_user] = _override_user(current_user)

    from unittest.mock import patch

    with patch.object(
        WorkspaceMemberRepository,
        "get_role_for_user",
        new=AsyncMock(return_value=RoleName.viewer),
    ):
        response = await client.patch(
            f"/workspaces/{workspace_id}",
            json={"name": "Hacked"},
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_patch_workspace_admin_200(
    client: AsyncClient,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    app.dependency_overrides[get_current_user] = _override_user(current_user)
    updated = _make_workspace(workspace_id=workspace_id, owner_id=user_id, name="Renamed")

    from unittest.mock import patch

    with (
        patch.object(
            WorkspaceMemberRepository,
            "get_role_for_user",
            new=AsyncMock(return_value=RoleName.admin),
        ),
        patch.object(
            WorkspaceRepository,
            "get_by_id",
            new=AsyncMock(return_value=updated),
        ),
        patch.object(
            WorkspaceRepository,
            "update",
            new=AsyncMock(return_value=updated),
        ),
    ):
        response = await client.patch(
            f"/workspaces/{workspace_id}",
            json={"name": "Renamed"},
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"


@pytest.mark.asyncio
async def test_delete_workspace_admin_soft_deletes(
    client: AsyncClient,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    app.dependency_overrides[get_current_user] = _override_user(current_user)
    ws = _make_workspace(workspace_id=workspace_id, owner_id=user_id)

    from unittest.mock import patch

    soft_delete = AsyncMock()
    soft_delete_members = AsyncMock(return_value=1)
    with (
        patch.object(
            WorkspaceMemberRepository,
            "get_role_for_user",
            new=AsyncMock(return_value=RoleName.admin),
        ),
        patch.object(
            WorkspaceRepository,
            "get_by_id",
            new=AsyncMock(return_value=ws),
        ),
        patch.object(
            WorkspaceRepository,
            "soft_delete",
            new=soft_delete,
        ),
        patch.object(
            WorkspaceMemberRepository,
            "soft_delete_all_for_workspace",
            new=soft_delete_members,
        ),
    ):
        response = await client.delete(
            f"/workspaces/{workspace_id}",
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 204
    soft_delete.assert_awaited_once()
    soft_delete_members.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_workspace_viewer_403(
    client: AsyncClient,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
) -> None:
    app.dependency_overrides[get_current_user] = _override_user(current_user)

    from unittest.mock import patch

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


@pytest.mark.asyncio
async def test_list_workspaces_paginated(
    client: AsyncClient,
    current_user: CurrentUser,
    user_id: uuid.UUID,
) -> None:
    app.dependency_overrides[get_current_user] = _override_user(current_user)
    items = [
        _make_workspace(owner_id=user_id, name="A"),
        _make_workspace(owner_id=user_id, name="B"),
    ]

    from unittest.mock import patch

    with patch.object(
        WorkspaceRepository,
        "list_for_member",
        new=AsyncMock(return_value=(items, 2)),
    ):
        response = await client.get(
            "/workspaces?page=1&page_size=20",
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert len(body["items"]) == 2
