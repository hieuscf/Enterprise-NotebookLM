# =============================================================================
# File: test_query_logs_api.py
# Module/Service: Observability / Query Logs (FR13)
# Layer: Presentation
# Purpose: HTTP tests for GET /admin/.../query-logs.
# Responsibilities:
#   - 200 with route_type filter forwarded; 403 for non-admin (editor/viewer)
# Dependencies:
#   - pytest, httpx, app.main
# Public Exports:
#   - N/A
# Database/Table: N/A (service override)
# Related Modules: app.api.admin, QueryLogsService
# Important Notes: No live Postgres — dependency overrides only.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.admin import get_query_logs_service
from app.core.rate_limit import InMemoryWorkspaceRateLimiter, get_workspace_rate_limiter
from app.db.session import get_db_session
from app.dependencies.auth import CurrentUser, get_current_user
from app.main import app
from app.models.enums import PlatformRole, RoleName, RouteType
from app.repositories.workspace_members import WorkspaceMemberRepository
from app.schemas.admin import QueryLogResponse


class FakeSession:
    async def flush(self) -> None:
        return None


def _sample_log(*, route_type: str = "complex") -> QueryLogResponse:
    return QueryLogResponse(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        message_id=uuid.uuid4(),
        cache_id=None,
        query_text="What is the Q3 revenue?",
        route_type=route_type,  # type: ignore[arg-type]
        llm_calls_count=2,
        model_used="claude-sonnet",
        latency_ms=420,
        created_at=datetime(2026, 8, 9, 12, 0, 0, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_query_logs_filters_by_route_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()
    expected = _sample_log(route_type="factoid")

    class FakeService:
        async def list_logs(self, **kwargs: Any) -> list[QueryLogResponse]:
            assert kwargs["workspace_id"] == workspace_id
            assert kwargs["route_type"] == RouteType.factoid
            assert kwargs["page"] == 1
            assert kwargs["page_size"] == 20
            return [expected]

    async def _user() -> CurrentUser:
        return CurrentUser(
            id=user_id,
            email="manage@ex.com",
            full_name="Manage",
            platform_role=PlatformRole.manage,
        )

    async def _db():
        yield FakeSession()

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[get_query_logs_service] = lambda: FakeService()
    app.dependency_overrides[get_workspace_rate_limiter] = (
        lambda: InMemoryWorkspaceRateLimiter()
    )

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                f"/admin/workspaces/{workspace_id}/query-logs",
                params={"route_type": "factoid", "page": 1, "page_size": 20},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) == 1
        assert body[0]["route_type"] == "factoid"
        assert body[0]["query_text"] == expected.query_text
        assert body[0]["llm_calls_count"] == 2
        assert body[0]["id"] == str(expected.id)
        assert body[0]["user_id"] == str(expected.user_id)
        assert body[0]["message_id"] == str(expected.message_id)
        assert body[0]["cache_id"] is None
        assert body[0]["model_used"] == "claude-sonnet"
        assert body[0]["latency_ms"] == 420
        assert "created_at" in body[0]
        assert "workspace_id" not in body[0]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [RoleName.editor, RoleName.viewer])
async def test_query_logs_forbidden_for_non_admin(
    monkeypatch: pytest.MonkeyPatch,
    role: RoleName,
) -> None:
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()

    async def _user() -> CurrentUser:
        return CurrentUser(id=user_id, email="member@ex.com", full_name="Member")

    async def _db():
        yield FakeSession()

    async def _role(self: Any, *, user_id: uuid.UUID, workspace_id: uuid.UUID) -> RoleName | None:
        return role

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[get_workspace_rate_limiter] = (
        lambda: InMemoryWorkspaceRateLimiter()
    )
    monkeypatch.setattr(WorkspaceMemberRepository, "get_role_for_user", _role)

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/admin/workspaces/{workspace_id}/query-logs")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()
