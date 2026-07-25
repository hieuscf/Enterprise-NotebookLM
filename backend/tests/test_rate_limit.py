# =============================================================================
# File: test_rate_limit.py
# Module/Service: API Gateway / Auth Middleware
# Layer: Presentation
# Purpose: Tests for per-workspace API rate limiting (FR12 Step 3).
# Responsibilities:
#   - Under limit → allow; over limit → 429 + Retry-After; reset window
# Dependencies:
#   - pytest, httpx, app.core.rate_limit, app.dependencies.rate_limit
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: app.api.workspaces
# Important Notes: Uses InMemoryWorkspaceRateLimiter — no Redis required in CI.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings, get_settings
from app.core.rate_limit import InMemoryWorkspaceRateLimiter, get_workspace_rate_limiter
from app.db.session import get_db_session
from app.dependencies.auth import CurrentUser, get_current_user
from app.main import app
from app.models.enums import RoleName
from app.repositories.workspace_members import WorkspaceMemberRepository


@pytest.fixture
def workspace_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def current_user() -> CurrentUser:
    return CurrentUser(id=uuid.uuid4(), email="rl@example.com", full_name="RL User")


@pytest.fixture
def limiter() -> InMemoryWorkspaceRateLimiter:
    get_workspace_rate_limiter.cache_clear()
    return InMemoryWorkspaceRateLimiter()


@pytest.fixture
def low_limit_settings() -> Settings:
    get_settings.cache_clear()
    return Settings(
        app_env="test",
        jwt_secret_key="test-secret",
        rate_limit_requests_per_minute=3,
        rate_limit_window_seconds=60,
    )


async def _fake_db():
    yield AsyncMock()


@pytest.fixture
async def client(
    current_user: CurrentUser,
    limiter: InMemoryWorkspaceRateLimiter,
    low_limit_settings: Settings,
):
    async def _user() -> CurrentUser:
        return current_user

    def _settings() -> Settings:
        return low_limit_settings

    def _limiter() -> InMemoryWorkspaceRateLimiter:
        return limiter

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db_session] = _fake_db
    app.dependency_overrides[get_settings] = _settings
    app.dependency_overrides[get_workspace_rate_limiter] = _limiter

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, limiter
    app.dependency_overrides.clear()
    get_settings.cache_clear()
    get_workspace_rate_limiter.cache_clear()


@pytest.mark.asyncio
async def test_under_limit_allows_requests(
    client,
    workspace_id: uuid.UUID,
) -> None:
    ac, _limiter = client
    now = datetime.now(UTC)

    class FakeWorkspace:
        id = workspace_id
        name = "RL WS"
        description = None
        created_at = now
        updated_at = now

    with (
        patch.object(
            WorkspaceMemberRepository,
            "get_role_for_user",
            new=AsyncMock(return_value=RoleName.viewer),
        ),
        patch(
            "app.services.workspaces.WorkspaceRepository.get_by_id",
            new=AsyncMock(return_value=FakeWorkspace()),
        ),
    ):
        for _ in range(3):
            response = await ac.get(
                f"/workspaces/{workspace_id}",
                headers={"Authorization": "Bearer test"},
            )
            assert response.status_code == 200


@pytest.mark.asyncio
async def test_over_limit_returns_429_with_retry_after(
    client,
    workspace_id: uuid.UUID,
) -> None:
    ac, _limiter = client
    now = datetime.now(UTC)

    class FakeWorkspace:
        id = workspace_id
        name = "RL WS"
        description = None
        created_at = now
        updated_at = now

    with (
        patch.object(
            WorkspaceMemberRepository,
            "get_role_for_user",
            new=AsyncMock(return_value=RoleName.viewer),
        ),
        patch(
            "app.services.workspaces.WorkspaceRepository.get_by_id",
            new=AsyncMock(return_value=FakeWorkspace()),
        ),
    ):
        for _ in range(3):
            assert (
                await ac.get(
                    f"/workspaces/{workspace_id}",
                    headers={"Authorization": "Bearer test"},
                )
            ).status_code == 200

        response = await ac.get(
            f"/workspaces/{workspace_id}",
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 429
    assert "retry-after" in response.headers
    assert int(response.headers["retry-after"]) >= 1
    detail = response.json()["detail"]
    assert detail["code"] == "rate_limited"


@pytest.mark.asyncio
async def test_reset_window_allows_again(
    client,
    workspace_id: uuid.UUID,
) -> None:
    ac, limiter = client
    now = datetime.now(UTC)

    class FakeWorkspace:
        id = workspace_id
        name = "RL WS"
        description = None
        created_at = now
        updated_at = now

    with (
        patch.object(
            WorkspaceMemberRepository,
            "get_role_for_user",
            new=AsyncMock(return_value=RoleName.viewer),
        ),
        patch(
            "app.services.workspaces.WorkspaceRepository.get_by_id",
            new=AsyncMock(return_value=FakeWorkspace()),
        ),
    ):
        for _ in range(3):
            await ac.get(
                f"/workspaces/{workspace_id}",
                headers={"Authorization": "Bearer test"},
            )
        blocked = await ac.get(
            f"/workspaces/{workspace_id}",
            headers={"Authorization": "Bearer test"},
        )
        assert blocked.status_code == 429

        limiter.reset(workspace_id)

        ok = await ac.get(
            f"/workspaces/{workspace_id}",
            headers={"Authorization": "Bearer test"},
        )
        assert ok.status_code == 200


def test_in_memory_limiter_unit() -> None:
    limiter = InMemoryWorkspaceRateLimiter()
    ws = uuid.uuid4()
    for _ in range(2):
        assert limiter.hit(ws, limit=2, window_seconds=60).allowed
    denied = limiter.hit(ws, limit=2, window_seconds=60)
    assert not denied.allowed
    assert denied.retry_after >= 1
    limiter.reset(ws)
    assert limiter.hit(ws, limit=2, window_seconds=60).allowed
