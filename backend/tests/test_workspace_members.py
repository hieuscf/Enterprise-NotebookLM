# =============================================================================
# File: test_workspace_members.py
# Module/Service: Workspace Service
# Layer: Presentation
# Purpose: Unit/API tests for workspace member management (FR1 Step 1.3 / UC10).
# Responsibilities:
#   - Duplicate add → 409; role change OK; last-admin demote/remove → 400
#   - Non-admin add/remove → 403
# Dependencies:
#   - pytest, httpx, app.services.members
# Public Exports:
#   - N/A
# Database/Table: N/A (fakes + dependency overrides; no Postgres in CI)
# Related Modules: app.api.workspaces, app.services.members
# Important Notes: 409 + last-admin are intentional OpenAPI extensions.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.rate_limit import InMemoryWorkspaceRateLimiter, get_workspace_rate_limiter
from app.db.session import get_db_session
from app.dependencies.auth import CurrentUser, get_current_user
from app.main import app
from app.models.enums import RoleName
from app.models.identity import Role, User, Workspace, WorkspaceMember
from app.repositories.roles import RoleRepository
from app.repositories.users import UserRepository
from app.repositories.workspace_members import MemberDetailRow, WorkspaceMemberRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.members import MemberError, WorkspaceMemberService


@pytest.fixture
def workspace_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def admin_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def target_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def admin_user(admin_id: uuid.UUID) -> CurrentUser:
    return CurrentUser(id=admin_id, email="admin@example.com", full_name="Admin")


@pytest.fixture
def viewer_user() -> CurrentUser:
    return CurrentUser(id=uuid.uuid4(), email="viewer@example.com", full_name="Viewer")


def _override_user(user: CurrentUser):
    async def _dep() -> CurrentUser:
        return user

    return _dep


async def _fake_db_session():
    yield AsyncMock()


def _ws(workspace_id: uuid.UUID) -> Workspace:
    now = datetime.now(UTC)
    return Workspace(
        id=workspace_id,
        name="WS",
        description=None,
        owner_id=uuid.uuid4(),
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )


def _detail(
    *,
    user_id: uuid.UUID,
    email: str = "u@example.com",
    role: RoleName = RoleName.editor,
) -> MemberDetailRow:
    return MemberDetailRow(
        user_id=user_id,
        email=email,
        role=role,
        joined_at=datetime.now(UTC),
    )


@pytest.fixture
async def client():
    app.dependency_overrides[get_db_session] = _fake_db_session
    app.dependency_overrides[get_workspace_rate_limiter] = lambda: InMemoryWorkspaceRateLimiter()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Service unit tests with fakes
# ---------------------------------------------------------------------------


class FakeMembers:
    def __init__(self) -> None:
        self.active: dict[tuple[uuid.UUID, uuid.UUID], WorkspaceMember] = {}
        self.roles: dict[tuple[uuid.UUID, uuid.UUID], RoleName] = {}
        self.details: dict[uuid.UUID, list[MemberDetailRow]] = {}

    async def list_for_workspace(self, workspace_id: uuid.UUID) -> list[MemberDetailRow]:
        return list(self.details.get(workspace_id, []))

    async def get_active_member(
        self, *, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> WorkspaceMember | None:
        return self.active.get((workspace_id, user_id))

    async def get_any_member_row(
        self, *, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> WorkspaceMember | None:
        return self.active.get((workspace_id, user_id))

    async def add_member(
        self, *, workspace_id: uuid.UUID, user_id: uuid.UUID, role_id: uuid.UUID
    ) -> WorkspaceMember:
        m = WorkspaceMember(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            user_id=user_id,
            role_id=role_id,
            joined_at=datetime.now(UTC),
            deleted_at=None,
        )
        self.active[(workspace_id, user_id)] = m
        return m

    async def revive_member(
        self, member: WorkspaceMember, *, role_id: uuid.UUID
    ) -> WorkspaceMember:
        member.role_id = role_id
        member.deleted_at = None
        return member

    async def update_role(self, member: WorkspaceMember, *, role_id: uuid.UUID) -> WorkspaceMember:
        member.role_id = role_id
        return member

    async def soft_delete(self, member: WorkspaceMember) -> None:
        member.deleted_at = datetime.now(UTC)
        key = (member.workspace_id, member.user_id)
        self.active.pop(key, None)
        self.roles.pop(key, None)

    async def get_role_for_user(
        self, *, user_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> RoleName | None:
        return self.roles.get((workspace_id, user_id))

    async def count_active_admins(self, workspace_id: uuid.UUID) -> int:
        return sum(
            1
            for (ws, _), role in self.roles.items()
            if ws == workspace_id and role == RoleName.admin
        )


def _member_service(
    workspace_id: uuid.UUID,
    *,
    members: FakeMembers | None = None,
) -> tuple[WorkspaceMemberService, FakeMembers]:
    fake = members or FakeMembers()
    svc = WorkspaceMemberService(AsyncMock())
    svc._members = fake  # type: ignore[method-assign]
    svc._roles = MagicMock()
    svc._roles.get_by_name = AsyncMock(
        side_effect=lambda name: Role(id=uuid.uuid4(), name=name, permissions={})
    )
    svc._users = MagicMock()
    svc._workspaces = MagicMock()
    svc._workspaces.get_by_id = AsyncMock(return_value=_ws(workspace_id))
    return svc, fake


@pytest.mark.asyncio
async def test_add_duplicate_raises_409(workspace_id: uuid.UUID, target_id: uuid.UUID) -> None:
    svc, fake = _member_service(workspace_id)
    fake.active[(workspace_id, target_id)] = WorkspaceMember(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        user_id=target_id,
        role_id=uuid.uuid4(),
        joined_at=datetime.now(UTC),
        deleted_at=None,
    )
    svc._users.get_by_id = AsyncMock(
        return_value=User(
            id=target_id,
            email="t@example.com",
            password_hash="x",
            full_name="T",
        )
    )

    with pytest.raises(MemberError) as exc:
        await svc.add_member(workspace_id=workspace_id, user_id=target_id, role=RoleName.viewer)
    assert exc.value.status_code == 409
    assert exc.value.code == "member_exists"


@pytest.mark.asyncio
async def test_demote_last_admin_raises_400(workspace_id: uuid.UUID, admin_id: uuid.UUID) -> None:
    svc, fake = _member_service(workspace_id)
    fake.active[(workspace_id, admin_id)] = WorkspaceMember(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        user_id=admin_id,
        role_id=uuid.uuid4(),
        joined_at=datetime.now(UTC),
        deleted_at=None,
    )
    fake.roles[(workspace_id, admin_id)] = RoleName.admin

    with pytest.raises(MemberError) as exc:
        await svc.update_role(
            workspace_id=workspace_id,
            user_id=admin_id,
            role=RoleName.viewer,
            actor_user_id=admin_id,
        )
    assert exc.value.status_code == 400
    assert exc.value.code == "last_admin"


@pytest.mark.asyncio
async def test_remove_last_admin_raises_400(workspace_id: uuid.UUID, admin_id: uuid.UUID) -> None:
    svc, fake = _member_service(workspace_id)
    fake.active[(workspace_id, admin_id)] = WorkspaceMember(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        user_id=admin_id,
        role_id=uuid.uuid4(),
        joined_at=datetime.now(UTC),
        deleted_at=None,
    )
    fake.roles[(workspace_id, admin_id)] = RoleName.admin

    with pytest.raises(MemberError) as exc:
        await svc.remove_member(workspace_id=workspace_id, user_id=admin_id)
    assert exc.value.status_code == 400
    assert exc.value.code == "last_admin"


@pytest.mark.asyncio
async def test_update_role_succeeds_with_two_admins(
    workspace_id: uuid.UUID, admin_id: uuid.UUID, target_id: uuid.UUID
) -> None:
    svc, fake = _member_service(workspace_id)
    for uid in (admin_id, target_id):
        fake.active[(workspace_id, uid)] = WorkspaceMember(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            user_id=uid,
            role_id=uuid.uuid4(),
            joined_at=datetime.now(UTC),
            deleted_at=None,
        )
        fake.roles[(workspace_id, uid)] = RoleName.admin
    fake.details[workspace_id] = [
        _detail(user_id=admin_id, email="a@example.com", role=RoleName.admin),
        _detail(user_id=target_id, email="t@example.com", role=RoleName.editor),
    ]

    row = await svc.update_role(
        workspace_id=workspace_id,
        user_id=target_id,
        role=RoleName.editor,
        actor_user_id=admin_id,
    )
    assert row.user_id == target_id
    assert row.role == RoleName.editor


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_member_non_admin_403(
    client: AsyncClient,
    viewer_user: CurrentUser,
    workspace_id: uuid.UUID,
    target_id: uuid.UUID,
) -> None:
    app.dependency_overrides[get_current_user] = _override_user(viewer_user)

    with patch.object(
        WorkspaceMemberRepository,
        "get_role_for_user",
        new=AsyncMock(return_value=RoleName.viewer),
    ):
        response = await client.post(
            f"/workspaces/{workspace_id}/members",
            json={"user_id": str(target_id), "role": "editor"},
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_add_member_duplicate_409(
    client: AsyncClient,
    admin_user: CurrentUser,
    workspace_id: uuid.UUID,
    target_id: uuid.UUID,
) -> None:
    app.dependency_overrides[get_current_user] = _override_user(admin_user)

    with (
        patch.object(
            WorkspaceMemberRepository,
            "get_role_for_user",
            new=AsyncMock(return_value=RoleName.admin),
        ),
        patch.object(
            WorkspaceRepository,
            "get_by_id",
            new=AsyncMock(return_value=_ws(workspace_id)),
        ),
        patch.object(
            UserRepository,
            "get_by_id",
            new=AsyncMock(
                return_value=User(
                    id=target_id,
                    email="t@example.com",
                    password_hash="x",
                    full_name="T",
                )
            ),
        ),
        patch.object(
            RoleRepository,
            "get_by_name",
            new=AsyncMock(return_value=Role(id=uuid.uuid4(), name=RoleName.editor, permissions={})),
        ),
        patch.object(
            WorkspaceMemberRepository,
            "get_any_member_row",
            new=AsyncMock(
                return_value=WorkspaceMember(
                    id=uuid.uuid4(),
                    workspace_id=workspace_id,
                    user_id=target_id,
                    role_id=uuid.uuid4(),
                    joined_at=datetime.now(UTC),
                    deleted_at=None,
                )
            ),
        ),
    ):
        response = await client.post(
            f"/workspaces/{workspace_id}/members",
            json={"user_id": str(target_id), "role": "editor"},
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "member_exists"


@pytest.mark.asyncio
async def test_add_member_201(
    client: AsyncClient,
    admin_user: CurrentUser,
    workspace_id: uuid.UUID,
    target_id: uuid.UUID,
) -> None:
    app.dependency_overrides[get_current_user] = _override_user(admin_user)
    detail = _detail(user_id=target_id, email="t@example.com", role=RoleName.editor)

    with (
        patch.object(
            WorkspaceMemberRepository,
            "get_role_for_user",
            new=AsyncMock(return_value=RoleName.admin),
        ),
        patch.object(
            WorkspaceRepository,
            "get_by_id",
            new=AsyncMock(return_value=_ws(workspace_id)),
        ),
        patch.object(
            UserRepository,
            "get_by_id",
            new=AsyncMock(
                return_value=User(
                    id=target_id,
                    email="t@example.com",
                    password_hash="x",
                    full_name="T",
                )
            ),
        ),
        patch.object(
            RoleRepository,
            "get_by_name",
            new=AsyncMock(return_value=Role(id=uuid.uuid4(), name=RoleName.editor, permissions={})),
        ),
        patch.object(
            WorkspaceMemberRepository,
            "get_any_member_row",
            new=AsyncMock(return_value=None),
        ),
        patch.object(
            WorkspaceMemberRepository,
            "add_member",
            new=AsyncMock(),
        ),
        patch.object(
            WorkspaceMemberRepository,
            "list_for_workspace",
            new=AsyncMock(return_value=[detail]),
        ),
    ):
        response = await client.post(
            f"/workspaces/{workspace_id}/members",
            json={"user_id": str(target_id), "role": "editor"},
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["user_id"] == str(target_id)
    assert body["role"] == "editor"
    assert body["email"] == "t@example.com"


@pytest.mark.asyncio
async def test_remove_member_viewer_403(
    client: AsyncClient,
    viewer_user: CurrentUser,
    workspace_id: uuid.UUID,
    target_id: uuid.UUID,
) -> None:
    app.dependency_overrides[get_current_user] = _override_user(viewer_user)

    with patch.object(
        WorkspaceMemberRepository,
        "get_role_for_user",
        new=AsyncMock(return_value=RoleName.viewer),
    ):
        response = await client.delete(
            f"/workspaces/{workspace_id}/members/{target_id}",
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_remove_last_admin_400(
    client: AsyncClient,
    admin_user: CurrentUser,
    workspace_id: uuid.UUID,
    admin_id: uuid.UUID,
) -> None:
    app.dependency_overrides[get_current_user] = _override_user(admin_user)

    with (
        patch.object(
            WorkspaceMemberRepository,
            "get_role_for_user",
            new=AsyncMock(return_value=RoleName.admin),
        ),
        patch.object(
            WorkspaceRepository,
            "get_by_id",
            new=AsyncMock(return_value=_ws(workspace_id)),
        ),
        patch.object(
            WorkspaceMemberRepository,
            "get_active_member",
            new=AsyncMock(
                return_value=WorkspaceMember(
                    id=uuid.uuid4(),
                    workspace_id=workspace_id,
                    user_id=admin_id,
                    role_id=uuid.uuid4(),
                    joined_at=datetime.now(UTC),
                    deleted_at=None,
                )
            ),
        ),
        patch.object(
            WorkspaceMemberRepository,
            "count_active_admins",
            new=AsyncMock(return_value=1),
        ),
    ):
        # get_role_for_user is also used inside remove_member for target role;
        # first call is RBAC (admin), subsequent calls return admin for target.
        response = await client.delete(
            f"/workspaces/{workspace_id}/members/{admin_id}",
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "last_admin"
