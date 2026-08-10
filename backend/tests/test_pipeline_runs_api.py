# =============================================================================
# File: test_pipeline_runs_api.py
# Module/Service: Observability / Pipeline Runs (FR13)
# Layer: Presentation
# Purpose: HTTP + repo tests for GET /admin/.../pipeline-runs.
# Responsibilities:
#   - Workspace JOIN scope (no cross-tenant leakage); status filter; RBAC admin-only
# Dependencies:
#   - pytest, httpx, sqlalchemy, app.main
# Public Exports:
#   - N/A
# Database/Table: N/A (fake session / service override)
# Related Modules: app.api.admin, PipelineRepository, PipelineRunsService
# Important Notes: SQL compile asserts document_versions → documents JOIN path.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects import postgresql

from app.api.admin import get_pipeline_runs_service
from app.core.rate_limit import InMemoryWorkspaceRateLimiter, get_workspace_rate_limiter
from app.db.session import get_db_session
from app.dependencies.auth import CurrentUser, get_current_user
from app.main import app
from app.models.enums import PipelineStatus, PipelineStage, RoleName
from app.models.pipeline import PipelineRun, PipelineStageLog
from app.repositories.pipeline import PipelineRepository
from app.repositories.workspace_members import WorkspaceMemberRepository
from app.schemas.documents import PipelineRunResponse, PipelineStageLogResponse
from app.services.pipeline_runs import PipelineRunsService


class FakeSession:
    async def flush(self) -> None:
        return None


class _EmptyScalarsResult:
    def all(self) -> list[Any]:
        return []


class CapturingSession:
    """Captures SQLAlchemy statements executed via ``scalars``."""

    def __init__(self) -> None:
        self.statements: list[Any] = []

    async def scalars(self, stmt: Any) -> _EmptyScalarsResult:
        self.statements.append(stmt)
        return _EmptyScalarsResult()


def _sample_run(*, status: str = "failed") -> PipelineRunResponse:
    return PipelineRunResponse(
        id=uuid.uuid4(),
        document_version_id=uuid.uuid4(),
        status=status,  # type: ignore[arg-type]
        retry_count=1,
        error_message="stage failed",
        stages=[
            PipelineStageLogResponse(
                id=uuid.uuid4(),
                stage="document_understanding",
                status="completed",
                duration_ms=120,
                metadata={"pages": 3},
                error_message=None,
            )
        ],
        started_at=datetime(2026, 8, 9, 10, 0, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 8, 9, 10, 1, 0, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_list_for_workspace_sql_joins_documents_for_scope() -> None:
    """pipeline_runs has no workspace_id — must JOIN document_versions → documents."""
    workspace_id = uuid.uuid4()
    other_workspace_id = uuid.uuid4()
    session = CapturingSession()
    repo = PipelineRepository(session)  # type: ignore[arg-type]

    rows = await repo.list_for_workspace(
        workspace_id=workspace_id,
        status=PipelineStatus.failed,
        page=1,
        page_size=20,
    )
    assert rows == []
    assert len(session.statements) == 1

    compiled = session.statements[0].compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    )
    sql = str(compiled).lower()
    assert "join document_versions" in sql or "join document_versions " in sql
    assert "join documents" in sql or " documents " in sql
    assert "documents.workspace_id" in sql
    assert str(workspace_id) in str(compiled)
    assert str(other_workspace_id) not in str(compiled)
    assert "pipeline_runs.status" in sql
    assert "'failed'" in sql


@pytest.mark.asyncio
async def test_pipeline_runs_service_excludes_other_workspace_runs() -> None:
    """Service only returns runs the repo scoped to the requested workspace."""
    ws_a = uuid.uuid4()
    ws_b = uuid.uuid4()
    run_a = PipelineRun(
        id=uuid.uuid4(),
        document_version_id=uuid.uuid4(),
        status=PipelineStatus.completed,
        retry_count=0,
        error_message=None,
        started_at=datetime(2026, 8, 9, 9, 0, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 8, 9, 9, 5, 0, tzinfo=timezone.utc),
    )
    run_a.stages = [  # type: ignore[attr-defined]
        PipelineStageLog(
            id=uuid.uuid4(),
            pipeline_run_id=run_a.id,
            stage=PipelineStage.indexing,
            status=PipelineStatus.completed,
            duration_ms=50,
            metadata_={"ok": True},
            error_message=None,
        )
    ]
    run_b = PipelineRun(
        id=uuid.uuid4(),
        document_version_id=uuid.uuid4(),
        status=PipelineStatus.completed,
        retry_count=0,
        error_message=None,
        started_at=datetime(2026, 8, 9, 8, 0, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 8, 9, 8, 5, 0, tzinfo=timezone.utc),
    )
    run_b.stages = []  # type: ignore[attr-defined]

    class FakeRepo:
        async def list_for_workspace(self, **kwargs: Any) -> list[PipelineRun]:
            # Mimic JOIN filter: only rows belonging to the requested workspace.
            owned = {ws_a: [run_a], ws_b: [run_b]}
            return list(owned.get(kwargs["workspace_id"], []))

    service = PipelineRunsService(FakeRepo())  # type: ignore[arg-type]
    result = await service.list_runs(workspace_id=ws_a)
    assert len(result) == 1
    assert result[0].id == run_a.id
    assert result[0].stages[0].stage == "indexing"
    assert all(r.id != run_b.id for r in result)


@pytest.mark.asyncio
async def test_pipeline_runs_filters_by_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()
    expected = _sample_run(status="failed")

    class FakeService:
        async def list_runs(self, **kwargs: Any) -> list[PipelineRunResponse]:
            assert kwargs["workspace_id"] == workspace_id
            assert kwargs["status"] == PipelineStatus.failed
            assert kwargs["page"] == 1
            assert kwargs["page_size"] == 20
            return [expected]

    async def _user() -> CurrentUser:
        from app.models.enums import PlatformRole

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
    app.dependency_overrides[get_pipeline_runs_service] = lambda: FakeService()
    app.dependency_overrides[get_workspace_rate_limiter] = (
        lambda: InMemoryWorkspaceRateLimiter()
    )

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                f"/admin/workspaces/{workspace_id}/pipeline-runs",
                params={"status": "failed", "page": 1, "page_size": 20},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) == 1
        assert body[0]["status"] == "failed"
        assert body[0]["id"] == str(expected.id)
        assert body[0]["document_version_id"] == str(expected.document_version_id)
        assert isinstance(body[0]["stages"], list)
        assert body[0]["stages"][0]["stage"] == "document_understanding"
        assert body[0]["stages"][0]["metadata"] == {"pages": 3}
        assert "workspace_id" not in body[0]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [RoleName.editor, RoleName.viewer])
async def test_pipeline_runs_forbidden_for_non_admin(
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
            resp = await client.get(f"/admin/workspaces/{workspace_id}/pipeline-runs")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()
