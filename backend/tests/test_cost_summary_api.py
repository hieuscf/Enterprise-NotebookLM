# =============================================================================
# File: test_cost_summary_api.py
# Module/Service: Observability / Cost Summary (FR13 + FR14)
# Layer: Presentation
# Purpose: HTTP tests for GET /admin/.../cost-summary (+ by_agent_type).
# Responsibilities:
#   - 200 with legacy fields + by_agent_type; 403 non-admin
# Dependencies:
#   - pytest, httpx, app.main
# Public Exports:
#   - N/A
# Database/Table: N/A (service override)
# Related Modules: app.api.admin, CostSummaryService
# Important Notes: No live Postgres — dependency overrides only.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.admin import get_cost_summary_service
from app.core.rate_limit import InMemoryWorkspaceRateLimiter, get_workspace_rate_limiter
from app.db.session import get_db_session
from app.dependencies.auth import CurrentUser, get_current_user
from app.main import app
from app.models.enums import RoleName
from app.repositories.workspace_members import WorkspaceMemberRepository
from app.schemas.admin import (
    AgentTypeCostSummary,
    CostByModelItem,
    CostByRouteTypeItem,
    CostSummaryResponse,
)


class FakeSession:
    async def flush(self) -> None:
        return None


@pytest.mark.asyncio
async def test_cost_summary_includes_by_agent_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()

    class FakeService:
        async def get_summary(self, **kwargs: Any) -> CostSummaryResponse:
            assert kwargs["workspace_id"] == workspace_id
            assert kwargs["date_from"] == date(2026, 1, 1)
            assert kwargs["date_to"] == date(2026, 8, 1)
            return CostSummaryResponse(
                total_cost_usd=1.25,
                total_llm_calls=10,
                by_model=[
                    CostByModelItem(model_used="claude-sonnet", calls=8, cost_usd=1.2)
                ],
                by_route_type=[
                    CostByRouteTypeItem(route_type="complex", count=7),
                ],
                by_agent_type={
                    "rewrite": AgentTypeCostSummary(
                        total_cost_usd=0.032,
                        total_latency_ms=1543,
                        count=52,
                        average_latency_ms=29.67,
                    ),
                    "graph": AgentTypeCostSummary(
                        total_cost_usd=0.0,
                        total_latency_ms=893,
                        count=34,
                        average_latency_ms=26.26,
                    ),
                    "sql": AgentTypeCostSummary(
                        total_cost_usd=0.0,
                        total_latency_ms=281,
                        count=17,
                        average_latency_ms=16.53,
                    ),
                },
            )

    async def _user() -> CurrentUser:
        return CurrentUser(id=user_id, email="admin@ex.com", full_name="Admin")

    async def _db():
        yield FakeSession()

    async def _role(self: Any, *, user_id: uuid.UUID, workspace_id: uuid.UUID) -> RoleName | None:
        return RoleName.admin

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[get_cost_summary_service] = lambda: FakeService()
    app.dependency_overrides[get_workspace_rate_limiter] = (
        lambda: InMemoryWorkspaceRateLimiter()
    )
    monkeypatch.setattr(WorkspaceMemberRepository, "get_role_for_user", _role)

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                f"/admin/workspaces/{workspace_id}/cost-summary",
                params={"from": "2026-01-01", "to": "2026-08-01"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_cost_usd"] == 1.25
        assert body["total_llm_calls"] == 10
        assert body["by_model"][0]["model_used"] == "claude-sonnet"
        assert body["by_route_type"][0]["route_type"] == "complex"
        assert body["by_agent_type"]["rewrite"]["count"] == 52
        assert body["by_agent_type"]["graph"]["total_latency_ms"] == 893
        assert body["by_agent_type"]["sql"]["total_cost_usd"] == 0.0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_cost_summary_forbidden_for_viewer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()

    async def _user() -> CurrentUser:
        return CurrentUser(id=user_id, email="v@ex.com", full_name="Viewer")

    async def _db():
        yield FakeSession()

    async def _role(self: Any, *, user_id: uuid.UUID, workspace_id: uuid.UUID) -> RoleName | None:
        return RoleName.viewer

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[get_workspace_rate_limiter] = (
        lambda: InMemoryWorkspaceRateLimiter()
    )
    monkeypatch.setattr(WorkspaceMemberRepository, "get_role_for_user", _role)

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/admin/workspaces/{workspace_id}/cost-summary")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()
