# =============================================================================
# File: test_admin_health_api.py
# Module/Service: Observability / System Health (FR13)
# Layer: Presentation
# Purpose: HTTP tests for GET /admin/health.
# Responsibilities:
#   - 200 with SystemHealth shape for Manage; 403 for non-manage
# Dependencies:
#   - pytest, httpx, app.main
# Public Exports:
#   - N/A
# Database/Table: N/A (service override)
# Related Modules: app.api.admin_health, SystemHealthService
# Important Notes: No live infrastructure — dependency overrides only.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.admin_health import get_system_health_service
from app.core.rate_limit import InMemoryWorkspaceRateLimiter, get_workspace_rate_limiter
from app.db.session import get_db_session
from app.dependencies.auth import CurrentUser, get_current_user
from app.main import app
from app.models.enums import PlatformRole, RoleName
from app.repositories.workspace_members import WorkspaceMemberRepository
from app.schemas.admin import HealthServiceItem, SystemHealthResponse


class FakeSession:
    async def flush(self) -> None:
        return None


@pytest.mark.asyncio
async def test_admin_health_ok_for_manage() -> None:
    user_id = uuid.uuid4()
    checked = datetime.now(UTC)

    class FakeService:
        async def get_health(self) -> SystemHealthResponse:
            return SystemHealthResponse(
                status="healthy",
                checked_at=checked,
                message="All monitored dependencies are responding normally.",
                services=[
                    HealthServiceItem(
                        id="postgresql",
                        name="PostgreSQL",
                        category="core",
                        status="healthy",
                        provider="postgresql",
                        message="Database connection operational",
                        checked_at=checked,
                        response_time_ms=12,
                        critical=True,
                    ),
                    HealthServiceItem(
                        id="llm_provider",
                        name="LLM Provider",
                        category="ai_retrieval",
                        status="healthy",
                        provider="anthropic",
                        message="LLM credentials configured (connectivity not probed)",
                        checked_at=checked,
                        response_time_ms=1,
                        critical=True,
                    ),
                ],
            )

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
    app.dependency_overrides[get_system_health_service] = lambda: FakeService()
    app.dependency_overrides[get_workspace_rate_limiter] = (
        lambda: InMemoryWorkspaceRateLimiter()
    )

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/admin/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert body["message"]
        assert len(body["services"]) == 2
        assert body["services"][0]["id"] == "postgresql"
        assert "password" not in resp.text.lower()
        assert "secret" not in resp.text.lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_health_forbidden_for_viewer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
            resp = await client.get("/admin/health")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_compute_overall_status_rules() -> None:
    from app.services.health.checkers import ProbeResult
    from app.services.health.service import compute_overall_status

    now = datetime.now(UTC)

    def svc(
        *,
        status: str,
        critical: bool = False,
        sid: str = "x",
    ) -> ProbeResult:
        return ProbeResult(
            id=sid,
            name=sid,
            category="core",
            status=status,  # type: ignore[arg-type]
            provider=None,
            message=None,
            checked_at=now,
            response_time_ms=1,
            critical=critical,
        )

    assert compute_overall_status([]) == "unknown"
    assert (
        compute_overall_status(
            [svc(status="healthy", critical=True), svc(status="healthy")]
        )
        == "healthy"
    )
    assert (
        compute_overall_status(
            [svc(status="healthy", critical=True), svc(status="degraded")]
        )
        == "degraded"
    )
    assert (
        compute_overall_status(
            [
                svc(status="unhealthy", critical=True, sid="pg"),
                svc(status="healthy", sid="redis"),
            ]
        )
        == "unhealthy"
    )
    assert (
        compute_overall_status(
            [
                svc(status="unhealthy", critical=False, sid="neo"),
                svc(status="healthy", critical=True, sid="pg"),
            ]
        )
        == "degraded"
    )
