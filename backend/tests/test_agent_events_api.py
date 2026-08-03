# =============================================================================
# File: test_agent_events_api.py
# Module/Service: Chat Service / Agent Events API (FR14)
# Layer: Presentation
# Purpose: HTTP tests for GET .../agent-events (schema, empty, RBAC).
# Responsibilities:
#   - 200 with events (no payloads); 200 []; 403 outsider
# Dependencies:
#   - pytest, httpx, app.main, AgentEventsService fakes
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: app.api.chat
# Important Notes: No live Postgres — dependency overrides only.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.chat import get_agent_events_service
from app.core.rate_limit import InMemoryWorkspaceRateLimiter, get_workspace_rate_limiter
from app.db.session import get_db_session
from app.dependencies.auth import CurrentUser, get_current_user
from app.main import app
from app.models.enums import RoleName
from app.repositories.workspace_members import WorkspaceMemberRepository
from app.schemas.chat import AgentEventResponse
from app.services.chat.agent_events_service import (
    AgentEventsService,
    AgentEventsServiceError,
)


class FakeSession:
    async def flush(self) -> None:
        return None


@pytest.mark.asyncio
async def test_case6_get_agent_events_with_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()
    message_id = uuid.uuid4()
    event_id = uuid.uuid4()

    class FakeService:
        async def list_for_message(self, **kwargs: Any) -> list[AgentEventResponse]:
            assert kwargs["workspace_id"] == workspace_id
            assert kwargs["message_id"] == message_id
            return [
                AgentEventResponse(
                    id=event_id,
                    agent_type="rewrite",
                    trigger_reason="ambiguous_query",
                    confidence_score=0.42,
                    triggered_second_retrieval=True,
                    model_used="claude-3-5-haiku-latest",
                    cost_usd=0.0001,
                    latency_ms=120,
                    created_at=datetime.now(UTC),
                )
            ]

    async def _user() -> CurrentUser:
        return CurrentUser(id=user_id, email="a@ex.com", full_name="A")

    async def _db():
        yield FakeSession()

    async def _role(self: Any, *, user_id: uuid.UUID, workspace_id: uuid.UUID) -> RoleName | None:
        return RoleName.viewer

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[get_agent_events_service] = lambda: FakeService()
    app.dependency_overrides[get_workspace_rate_limiter] = (
        lambda: InMemoryWorkspaceRateLimiter()
    )
    monkeypatch.setattr(WorkspaceMemberRepository, "get_role_for_user", _role)

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                f"/workspaces/{workspace_id}/chat/messages/{message_id}/agent-events"
            )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["agent_type"] == "rewrite"
        assert body[0]["confidence_score"] == 0.42
        assert "input_payload" not in body[0]
        assert "output_payload" not in body[0]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_case7_get_agent_events_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()
    message_id = uuid.uuid4()

    class FakeService:
        async def list_for_message(self, **kwargs: Any) -> list[AgentEventResponse]:
            return []

    async def _user() -> CurrentUser:
        return CurrentUser(id=user_id, email="a@ex.com", full_name="A")

    async def _db():
        yield FakeSession()

    async def _role(self: Any, *, user_id: uuid.UUID, workspace_id: uuid.UUID) -> RoleName | None:
        return RoleName.editor

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[get_agent_events_service] = lambda: FakeService()
    app.dependency_overrides[get_workspace_rate_limiter] = (
        lambda: InMemoryWorkspaceRateLimiter()
    )
    monkeypatch.setattr(WorkspaceMemberRepository, "get_role_for_user", _role)

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                f"/workspaces/{workspace_id}/chat/messages/{message_id}/agent-events"
            )
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_case8_get_agent_events_rbac_outsider_403(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid.uuid4()
    outsider_id = uuid.uuid4()
    message_id = uuid.uuid4()

    async def _user() -> CurrentUser:
        return CurrentUser(id=outsider_id, email="out@ex.com", full_name="Out")

    async def _db():
        yield FakeSession()

    async def _role(self: Any, *, user_id: uuid.UUID, workspace_id: uuid.UUID) -> RoleName | None:
        return None  # not a member

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[get_agent_events_service] = lambda: AgentEventsService(
        repo=None  # type: ignore[arg-type]
    )
    app.dependency_overrides[get_workspace_rate_limiter] = (
        lambda: InMemoryWorkspaceRateLimiter()
    )
    monkeypatch.setattr(WorkspaceMemberRepository, "get_role_for_user", _role)

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                f"/workspaces/{workspace_id}/chat/messages/{message_id}/agent-events"
            )
        assert resp.status_code == 403
        detail = resp.json()["detail"]
        assert detail["code"] == "forbidden"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_agent_events_service_message_missing_404() -> None:
    class FakeRepo:
        async def list_by_message(self, **kwargs: Any) -> None:
            return None

    svc = AgentEventsService(FakeRepo())  # type: ignore[arg-type]
    with pytest.raises(AgentEventsServiceError) as exc:
        await svc.list_for_message(workspace_id=uuid.uuid4(), message_id=uuid.uuid4())
    assert exc.value.status_code == 404
