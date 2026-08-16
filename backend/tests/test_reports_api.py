# =============================================================================
# File: test_reports_api.py
# Module/Service: Report Service (FR9 Prompt 4/5)
# Layer: Presentation / Service
# Purpose: API + service tests for async Reports (CRUD, export, Celery enqueue).
# Responsibilities:
#   - POST 202 pending for each export_format; GET list/detail; DELETE 204
#   - Export 409 when not ready; 200 binary when ready
#   - process_report happy path per format with mocked renderers (no real render)
# Dependencies:
#   - pytest, httpx, ReportService fakes
# Public Exports:
#   - N/A
# Database/Table: N/A (in-memory fakes; no Postgres/MinIO/Redis)
# Related Modules: app.api.reports, app.workers.reports, app.services.report_service
# Important Notes: Renderers + MinIO stubbed; no real PDF/DOCX/MD generation.
# =============================================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.reports import get_report_service
from app.core.rate_limit import InMemoryWorkspaceRateLimiter, get_workspace_rate_limiter
from app.db.session import get_db_session
from app.dependencies.auth import CurrentUser, get_current_user
from app.main import app
from app.models.artifacts import Report, ReportItem
from app.models.enums import ReportFormat, ReportSourceType, ReportStatus, RoleName
from app.repositories.reports import ReportItemSpec, ReportWithItems
from app.repositories.workspace_members import WorkspaceMemberRepository
from app.services.report_aggregation import (
    AggregatedReportBlock,
    ReportAggregationError,
    ReportItemInput,
)
from app.services.report_service import ReportService
from app.services.renderers.docx_renderer import DocxRenderResult
from app.services.renderers.markdown_renderer import MarkdownRenderResult
from app.services.renderers.pdf_renderer import PdfRenderResult


class FakeSession:
    async def commit(self) -> None:
        return None

    async def flush(self) -> None:
        return None


@dataclass
class FakeStorage:
    objects: dict[str, bytes] = field(default_factory=dict)
    deleted: list[str] = field(default_factory=list)

    def upload_bytes(
        self,
        *,
        object_key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        del content_type
        self.objects[object_key] = data
        return object_key

    def download_bytes(self, object_key: str) -> bytes:
        if object_key not in self.objects:
            raise FileNotFoundError(object_key)
        return self.objects[object_key]

    def iter_object(self, object_key: str, chunk_size: int = 65536):
        data = self.download_bytes(object_key)
        if not data:
            return
            yield
        for index in range(0, len(data), chunk_size):
            yield data[index : index + chunk_size]

    def object_exists(self, object_key: str) -> bool:
        return object_key in self.objects

    def object_size(self, object_key: str) -> int | None:
        data = self.objects.get(object_key)
        return None if data is None else len(data)

    def delete_object(self, object_key: str) -> None:
        self.deleted.append(object_key)
        self.objects.pop(object_key, None)


class FakeReportRepo:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, ReportWithItems] = {}

    async def create_pending(self, **kwargs: Any) -> ReportWithItems:
        report_id = uuid.uuid4()
        report = Report(
            id=report_id,
            workspace_id=kwargs["workspace_id"],
            created_by=kwargs["created_by"],
            title=kwargs["title"],
            format=kwargs["format_"],
            status=ReportStatus.pending,
            file_path=None,
            created_at=datetime.now(UTC),
        )
        items = [
            ReportItem(
                id=uuid.uuid4(),
                report_id=report_id,
                source_type=spec.source_type,
                source_id=spec.source_id,
                order_index=spec.order_index,
            )
            for spec in kwargs["items"]
        ]
        wrapped = ReportWithItems(report=report, items=items)
        self.rows[report_id] = wrapped
        return wrapped

    async def get_by_id(self, report_id: uuid.UUID) -> Report | None:
        wrapped = self.rows.get(report_id)
        return wrapped.report if wrapped else None

    async def get(
        self, *, workspace_id: uuid.UUID, report_id: uuid.UUID
    ) -> ReportWithItems | None:
        wrapped = self.rows.get(report_id)
        if wrapped is None or wrapped.report.workspace_id != workspace_id:
            return None
        return wrapped

    async def get_row(
        self, *, workspace_id: uuid.UUID, report_id: uuid.UUID
    ) -> Report | None:
        wrapped = await self.get(workspace_id=workspace_id, report_id=report_id)
        return wrapped.report if wrapped else None

    async def list_for_workspace(
        self,
        *,
        workspace_id: uuid.UUID,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[ReportWithItems]:
        rows = [w for w in self.rows.values() if w.report.workspace_id == workspace_id]
        rows.sort(key=lambda w: w.report.created_at, reverse=True)
        sliced = rows[offset:]
        if limit is not None:
            sliced = sliced[:limit]
        return sliced

    async def list_items(self, report_id: uuid.UUID) -> list[ReportItem]:
        wrapped = self.rows.get(report_id)
        return list(wrapped.items) if wrapped else []

    async def mark_ready(self, *, report_id: uuid.UUID, file_path: str) -> bool:
        wrapped = self.rows.get(report_id)
        if wrapped is None or wrapped.report.status != ReportStatus.pending:
            return False
        wrapped.report.status = ReportStatus.ready
        wrapped.report.file_path = file_path
        return True

    async def mark_failed(self, *, report_id: uuid.UUID) -> bool:
        wrapped = self.rows.get(report_id)
        if wrapped is None or wrapped.report.status != ReportStatus.pending:
            return False
        wrapped.report.status = ReportStatus.failed
        wrapped.report.file_path = None
        return True

    async def delete(
        self, *, workspace_id: uuid.UUID, report_id: uuid.UUID
    ) -> Report | None:
        wrapped = await self.get(workspace_id=workspace_id, report_id=report_id)
        if wrapped is None:
            return None
        del self.rows[report_id]
        return wrapped.report


class FakeAggregation:
    def __init__(self) -> None:
        self.allowed: set[uuid.UUID] = set()
        self.blocks: list[AggregatedReportBlock] = [
            AggregatedReportBlock(
                order_index=0,
                source_type=ReportSourceType.summary,
                title="Summary block",
                content={"text": "Hello", "style": "short", "sections": None},
            )
        ]
        self.preview_payload: dict[str, Any] | None = None

    async def aggregate(
        self, *, workspace_id: uuid.UUID, items: list[ReportItemInput]
    ) -> list[AggregatedReportBlock]:
        del workspace_id
        for item in items:
            if item.source_id not in self.allowed:
                raise ReportAggregationError(
                    "source_not_found",
                    f"source {item.source_id} not found",
                    status_code=404,
                )
        return list(self.blocks)

    async def preview_comparison(
        self,
        *,
        workspace_id: uuid.UUID,
        comparison_id: uuid.UUID,
    ) -> dict[str, Any] | None:
        del workspace_id
        if self.preview_payload is None:
            return None
        return {**self.preview_payload, "comparison_id": str(comparison_id)}


def _mock_markdown_render(blocks: Any, **kwargs: Any) -> MarkdownRenderResult:
    del blocks
    output_dir: Path = kwargs["output_dir"]
    report_id: uuid.UUID = kwargs["report_id"]
    workspace_id: uuid.UUID = kwargs["workspace_id"]
    filename = f"mock_{report_id}.md"
    path = output_dir / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Mock\n\n## Summary block\n\nHello\n", encoding="utf-8")
    return MarkdownRenderResult(
        filename=filename,
        local_path=path,
        object_key=f"workspaces/{workspace_id}/reports/{report_id}/{filename}",
        markdown=path.read_text(encoding="utf-8"),
        section_count=1,
    )


def _mock_docx_render(blocks: Any, **kwargs: Any) -> DocxRenderResult:
    del blocks
    output_dir: Path = kwargs["output_dir"]
    report_id: uuid.UUID = kwargs["report_id"]
    workspace_id: uuid.UUID = kwargs["workspace_id"]
    filename = f"mock_{report_id}.docx"
    path = output_dir / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"PK\x03\x04-mock-docx")
    return DocxRenderResult(
        filename=filename,
        local_path=path,
        object_key=f"workspaces/{workspace_id}/reports/{report_id}/{filename}",
        section_count=1,
    )


def _mock_pdf_render(markdown: str, **kwargs: Any) -> PdfRenderResult:
    del markdown
    output_dir: Path = kwargs["output_dir"]
    report_id: uuid.UUID = kwargs["report_id"]
    workspace_id: uuid.UUID = kwargs["workspace_id"]
    filename = f"mock_{report_id}.pdf"
    path = output_dir / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4 mock")
    return PdfRenderResult(
        filename=filename,
        local_path=path,
        object_key=f"workspaces/{workspace_id}/reports/{report_id}/{filename}",
    )


@pytest.fixture
def workspace_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def source_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def reports_repo() -> FakeReportRepo:
    return FakeReportRepo()


@pytest.fixture
def aggregation() -> FakeAggregation:
    return FakeAggregation()


@pytest.fixture
def storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture
def enqueued() -> list[uuid.UUID]:
    return []


@pytest.fixture
def staging_dir(tmp_path: Path) -> Path:
    return tmp_path / "staging"


@pytest.fixture
async def client(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    reports_repo: FakeReportRepo,
    aggregation: FakeAggregation,
    storage: FakeStorage,
    enqueued: list[uuid.UUID],
    staging_dir: Path,
    source_id: uuid.UUID,
):
    aggregation.allowed.add(source_id)
    allowed_ws = workspace_id

    async def _override_user() -> CurrentUser:
        return CurrentUser(id=user_id, email="u@example.com", full_name="U")

    async def _override_db() -> Any:
        yield FakeSession()

    def _override_service() -> ReportService:
        return ReportService(
            session=FakeSession(),  # type: ignore[arg-type]
            reports=reports_repo,  # type: ignore[arg-type]
            aggregation=aggregation,  # type: ignore[arg-type]
            storage=storage,  # type: ignore[arg-type]
            enqueue=True,
            enqueue_fn=lambda rid: enqueued.append(rid),
            markdown_render_fn=_mock_markdown_render,
            docx_render_fn=_mock_docx_render,
            pdf_render_fn=_mock_pdf_render,
            staging_dir=staging_dir,
        )

    async def _role_side_effect(*, user_id: uuid.UUID, workspace_id: uuid.UUID) -> RoleName | None:
        del user_id
        if workspace_id != allowed_ws:
            return None
        return getattr(app.state, "test_role", RoleName.editor)

    get_workspace_rate_limiter.cache_clear()
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_db_session] = _override_db
    app.dependency_overrides[get_report_service] = _override_service
    app.dependency_overrides[get_workspace_rate_limiter] = lambda: InMemoryWorkspaceRateLimiter()

    with patch.object(
        WorkspaceMemberRepository,
        "get_role_for_user",
        new=AsyncMock(side_effect=_role_side_effect),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

    app.dependency_overrides.clear()
    get_workspace_rate_limiter.cache_clear()
    if hasattr(app.state, "test_role"):
        delattr(app.state, "test_role")


def _set_role(role: RoleName) -> None:
    app.state.test_role = role


def _create_body(source_id: uuid.UUID, export_format: str) -> dict[str, Any]:
    return {
        "title": f"Report {export_format}",
        "export_format": export_format,
        "items": [
            {
                "source_type": "summary",
                "source_id": str(source_id),
                "order_index": 0,
            }
        ],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("export_format", ["markdown", "docx", "pdf"])
async def test_post_report_accepted_per_format(
    client: AsyncClient,
    workspace_id: uuid.UUID,
    source_id: uuid.UUID,
    enqueued: list[uuid.UUID],
    export_format: str,
) -> None:
    _set_role(RoleName.editor)
    resp = await client.post(
        f"/workspaces/{workspace_id}/reports",
        json=_create_body(source_id, export_format),
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["workspace_id"] == str(workspace_id)
    assert body["title"] == f"Report {export_format}"
    assert body["export_format"] == export_format
    assert body["status"] == "pending"
    assert body["file_url"] is None
    assert "id" in body and "created_at" in body
    assert enqueued[-1] == uuid.UUID(body["id"])


@pytest.mark.asyncio
async def test_list_get_delete_and_export_lifecycle(
    client: AsyncClient,
    workspace_id: uuid.UUID,
    source_id: uuid.UUID,
    reports_repo: FakeReportRepo,
    aggregation: FakeAggregation,
    storage: FakeStorage,
    staging_dir: Path,
) -> None:
    _set_role(RoleName.editor)
    create = await client.post(
        f"/workspaces/{workspace_id}/reports",
        json=_create_body(source_id, "markdown"),
    )
    assert create.status_code == 202
    report_id = uuid.UUID(create.json()["id"])

    listed = await client.get(f"/workspaces/{workspace_id}/reports?page=1&page_size=20")
    assert listed.status_code == 200
    assert any(item["id"] == str(report_id) for item in listed.json())

    detail = await client.get(f"/workspaces/{workspace_id}/reports/{report_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "pending"
    assert detail.json()["items"][0]["source_id"] == str(source_id)
    assert detail.json()["preview"] is None

    not_ready = await client.get(f"/workspaces/{workspace_id}/reports/{report_id}/export")
    assert not_ready.status_code == 409
    assert not_ready.json()["detail"]["code"] == "not_ready"

    service = ReportService(
        session=FakeSession(),  # type: ignore[arg-type]
        reports=reports_repo,  # type: ignore[arg-type]
        aggregation=aggregation,  # type: ignore[arg-type]
        storage=storage,  # type: ignore[arg-type]
        enqueue=False,
        markdown_render_fn=_mock_markdown_render,
        docx_render_fn=_mock_docx_render,
        pdf_render_fn=_mock_pdf_render,
        staging_dir=staging_dir,
    )
    outcome = await service.process_report(report_id)
    assert outcome is not None
    assert outcome.status == ReportStatus.ready
    assert outcome.file_path is not None
    assert outcome.file_path in storage.objects

    ready_detail = await client.get(f"/workspaces/{workspace_id}/reports/{report_id}")
    assert ready_detail.status_code == 200
    assert ready_detail.json()["status"] == "ready"
    assert ready_detail.json()["file_url"] == (
        f"/workspaces/{workspace_id}/reports/{report_id}/export"
    )

    exported = await client.get(f"/workspaces/{workspace_id}/reports/{report_id}/export")
    assert exported.status_code == 200
    assert "text/markdown" in exported.headers["content-type"]
    assert exported.headers["cache-control"] == "private, no-store"
    assert exported.headers["x-content-type-options"] == "nosniff"
    assert "attachment" in exported.headers["content-disposition"]
    assert "filename=" in exported.headers["content-disposition"]
    assert ".." not in exported.headers["content-disposition"]
    assert exported.content.startswith(b"# Mock")

    deleted = await client.delete(f"/workspaces/{workspace_id}/reports/{report_id}")
    assert deleted.status_code == 204
    assert outcome.file_path in storage.deleted
    missing = await client.get(f"/workspaces/{workspace_id}/reports/{report_id}")
    assert missing.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("export_format", "suffix", "magic"),
    [
        (ReportFormat.markdown, ".md", b"# Mock"),
        (ReportFormat.docx, ".docx", b"PK\x03\x04"),
        (ReportFormat.pdf, ".pdf", b"%PDF"),
    ],
)
async def test_process_report_per_export_format(
    reports_repo: FakeReportRepo,
    aggregation: FakeAggregation,
    storage: FakeStorage,
    staging_dir: Path,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    source_id: uuid.UUID,
    export_format: ReportFormat,
    suffix: str,
    magic: bytes,
) -> None:
    aggregation.allowed.add(source_id)
    created = await reports_repo.create_pending(
        workspace_id=workspace_id,
        created_by=user_id,
        title=f"T {export_format.value}",
        format_=export_format,
        items=[
            ReportItemSpec(
                source_type=ReportSourceType.summary,
                source_id=source_id,
                order_index=0,
            )
        ],
    )
    service = ReportService(
        session=FakeSession(),  # type: ignore[arg-type]
        reports=reports_repo,  # type: ignore[arg-type]
        aggregation=aggregation,  # type: ignore[arg-type]
        storage=storage,  # type: ignore[arg-type]
        enqueue=False,
        markdown_render_fn=_mock_markdown_render,
        docx_render_fn=_mock_docx_render,
        pdf_render_fn=_mock_pdf_render,
        staging_dir=staging_dir,
    )
    outcome = await service.process_report(created.report.id)
    assert outcome is not None
    assert outcome.status == ReportStatus.ready
    assert outcome.file_path is not None
    assert outcome.file_path.endswith(suffix)
    assert storage.objects[outcome.file_path].startswith(magic)


@pytest.mark.asyncio
async def test_post_invalid_source_returns_404(
    client: AsyncClient,
    workspace_id: uuid.UUID,
) -> None:
    _set_role(RoleName.editor)
    resp = await client.post(
        f"/workspaces/{workspace_id}/reports",
        json=_create_body(uuid.uuid4(), "pdf"),
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "source_not_found"


@pytest.mark.asyncio
async def test_post_viewer_forbidden(
    client: AsyncClient,
    workspace_id: uuid.UUID,
    source_id: uuid.UUID,
) -> None:
    _set_role(RoleName.viewer)
    resp = await client.post(
        f"/workspaces/{workspace_id}/reports",
        json=_create_body(source_id, "markdown"),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_report_includes_comparison_preview(
    client: AsyncClient,
    workspace_id: uuid.UUID,
    source_id: uuid.UUID,
    aggregation: FakeAggregation,
) -> None:
    _set_role(RoleName.editor)
    aggregation.preview_payload = {
        "has_contract_report": True,
        "comparison_ready": True,
        "comparison_report": {
            "executive_summary": {
                "total_clauses": 12,
                "unchanged": 8,
                "modified": 4,
                "added": 2,
                "removed": 0,
            }
        },
    }
    create = await client.post(
        f"/workspaces/{workspace_id}/reports",
        json={
            "title": "Comparison preview",
            "export_format": "markdown",
            "items": [
                {
                    "source_type": "comparison",
                    "source_id": str(source_id),
                    "order_index": 0,
                }
            ],
        },
    )
    assert create.status_code == 202
    assert create.json()["preview"] is None
    report_id = create.json()["id"]

    listed = await client.get(f"/workspaces/{workspace_id}/reports")
    listed_row = next(item for item in listed.json() if item["id"] == report_id)
    assert listed_row["preview"] is None

    detail = await client.get(f"/workspaces/{workspace_id}/reports/{report_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["items"][0]["source_type"] == "comparison"
    assert body["preview"]["comparison_id"] == str(source_id)
    assert body["preview"]["comparison_report"]["executive_summary"]["total_clauses"] == 12


@pytest.mark.asyncio
async def test_get_report_unknown_or_foreign_workspace(
    client: AsyncClient,
    workspace_id: uuid.UUID,
) -> None:
    _set_role(RoleName.editor)
    missing = await client.get(f"/workspaces/{workspace_id}/reports/{uuid.uuid4()}")
    assert missing.status_code == 404
    foreign = await client.get(f"/workspaces/{uuid.uuid4()}/reports/{uuid.uuid4()}")
    assert foreign.status_code == 403


async def _ready_report(
    *,
    reports_repo: FakeReportRepo,
    aggregation: FakeAggregation,
    storage: FakeStorage,
    staging_dir: Path,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    source_id: uuid.UUID,
    export_format: ReportFormat = ReportFormat.markdown,
    title: str = "Report markdown",
) -> Report:
    aggregation.allowed.add(source_id)
    created = await reports_repo.create_pending(
        workspace_id=workspace_id,
        created_by=user_id,
        title=title,
        format_=export_format,
        items=[
            ReportItemSpec(
                source_type=ReportSourceType.summary,
                source_id=source_id,
                order_index=0,
            )
        ],
    )
    service = ReportService(
        session=FakeSession(),  # type: ignore[arg-type]
        reports=reports_repo,  # type: ignore[arg-type]
        aggregation=aggregation,  # type: ignore[arg-type]
        storage=storage,  # type: ignore[arg-type]
        enqueue=False,
        markdown_render_fn=_mock_markdown_render,
        docx_render_fn=_mock_docx_render,
        pdf_render_fn=_mock_pdf_render,
        staging_dir=staging_dir,
    )
    outcome = await service.process_report(created.report.id)
    assert outcome is not None
    assert outcome.status == ReportStatus.ready
    return outcome


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("export_format", "mime", "magic"),
    [
        (ReportFormat.markdown, "text/markdown", b"# Mock"),
        (
            ReportFormat.docx,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            b"PK\x03\x04",
        ),
        (ReportFormat.pdf, "application/pdf", b"%PDF"),
    ],
)
async def test_export_ready_report_mime_and_bytes(
    client: AsyncClient,
    reports_repo: FakeReportRepo,
    aggregation: FakeAggregation,
    storage: FakeStorage,
    staging_dir: Path,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    source_id: uuid.UUID,
    export_format: ReportFormat,
    mime: str,
    magic: bytes,
) -> None:
    _set_role(RoleName.editor)
    row = await _ready_report(
        reports_repo=reports_repo,
        aggregation=aggregation,
        storage=storage,
        staging_dir=staging_dir,
        workspace_id=workspace_id,
        user_id=user_id,
        source_id=source_id,
        export_format=export_format,
        title=f"Contract Comparison {export_format.value}",
    )
    resp = await client.get(f"/workspaces/{workspace_id}/reports/{row.id}/export")
    assert resp.status_code == 200
    assert mime in resp.headers["content-type"]
    assert resp.content.startswith(magic)
    disposition = resp.headers["content-disposition"]
    assert "attachment" in disposition
    assert disposition.lower().count("filename") >= 1
    if export_format is ReportFormat.markdown:
        assert ".md" in disposition
    elif export_format is ReportFormat.docx:
        assert ".docx" in disposition
    else:
        assert ".pdf" in disposition


@pytest.mark.asyncio
async def test_export_failed_report_is_controlled_error(
    client: AsyncClient,
    reports_repo: FakeReportRepo,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    source_id: uuid.UUID,
) -> None:
    _set_role(RoleName.editor)
    created = await reports_repo.create_pending(
        workspace_id=workspace_id,
        created_by=user_id,
        title="Failed report",
        format_=ReportFormat.pdf,
        items=[
            ReportItemSpec(
                source_type=ReportSourceType.summary,
                source_id=source_id,
                order_index=0,
            )
        ],
    )
    await reports_repo.mark_failed(report_id=created.report.id)
    resp = await client.get(
        f"/workspaces/{workspace_id}/reports/{created.report.id}/export"
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "generation_failed"
    assert "traceback" not in resp.json()["detail"]["message"].lower()


@pytest.mark.asyncio
async def test_export_missing_artifact_is_file_not_found(
    client: AsyncClient,
    reports_repo: FakeReportRepo,
    aggregation: FakeAggregation,
    storage: FakeStorage,
    staging_dir: Path,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    source_id: uuid.UUID,
) -> None:
    _set_role(RoleName.editor)
    row = await _ready_report(
        reports_repo=reports_repo,
        aggregation=aggregation,
        storage=storage,
        staging_dir=staging_dir,
        workspace_id=workspace_id,
        user_id=user_id,
        source_id=source_id,
    )
    assert row.file_path is not None
    storage.objects.pop(row.file_path)
    resp = await client.get(f"/workspaces/{workspace_id}/reports/{row.id}/export")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "file_not_found"


@pytest.mark.asyncio
async def test_export_rejects_injected_storage_url(
    client: AsyncClient,
    reports_repo: FakeReportRepo,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    source_id: uuid.UUID,
) -> None:
    _set_role(RoleName.editor)
    created = await reports_repo.create_pending(
        workspace_id=workspace_id,
        created_by=user_id,
        title="Injected",
        format_=ReportFormat.pdf,
        items=[
            ReportItemSpec(
                source_type=ReportSourceType.summary,
                source_id=source_id,
                order_index=0,
            )
        ],
    )
    created.report.status = ReportStatus.ready
    created.report.file_path = "s3://other-bucket/secret.pdf"
    resp = await client.get(
        f"/workspaces/{workspace_id}/reports/{created.report.id}/export"
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "file_not_found"


@pytest.mark.asyncio
async def test_export_sanitizes_path_traversal_title(
    client: AsyncClient,
    reports_repo: FakeReportRepo,
    aggregation: FakeAggregation,
    storage: FakeStorage,
    staging_dir: Path,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    source_id: uuid.UUID,
) -> None:
    _set_role(RoleName.editor)
    row = await _ready_report(
        reports_repo=reports_repo,
        aggregation=aggregation,
        storage=storage,
        staging_dir=staging_dir,
        workspace_id=workspace_id,
        user_id=user_id,
        source_id=source_id,
        title="../../secret",
    )
    resp = await client.get(f"/workspaces/{workspace_id}/reports/{row.id}/export")
    assert resp.status_code == 200
    disposition = resp.headers["content-disposition"]
    assert ".." not in disposition
    assert "/" not in disposition.split("filename=")[-1].replace("UTF-8''", "")


@pytest.mark.asyncio
async def test_export_foreign_workspace_is_forbidden(
    client: AsyncClient,
    reports_repo: FakeReportRepo,
    aggregation: FakeAggregation,
    storage: FakeStorage,
    staging_dir: Path,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    source_id: uuid.UUID,
) -> None:
    _set_role(RoleName.editor)
    row = await _ready_report(
        reports_repo=reports_repo,
        aggregation=aggregation,
        storage=storage,
        staging_dir=staging_dir,
        workspace_id=workspace_id,
        user_id=user_id,
        source_id=source_id,
    )
    resp = await client.get(f"/workspaces/{uuid.uuid4()}/reports/{row.id}/export")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_export_other_report_in_workspace_is_404(
    client: AsyncClient,
    workspace_id: uuid.UUID,
) -> None:
    _set_role(RoleName.editor)
    resp = await client.get(f"/workspaces/{workspace_id}/reports/{uuid.uuid4()}/export")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "not_found"


@pytest.mark.asyncio
async def test_export_viewer_can_download_ready_report(
    client: AsyncClient,
    reports_repo: FakeReportRepo,
    aggregation: FakeAggregation,
    storage: FakeStorage,
    staging_dir: Path,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    source_id: uuid.UUID,
) -> None:
    row = await _ready_report(
        reports_repo=reports_repo,
        aggregation=aggregation,
        storage=storage,
        staging_dir=staging_dir,
        workspace_id=workspace_id,
        user_id=user_id,
        source_id=source_id,
    )
    _set_role(RoleName.viewer)
    resp = await client.get(f"/workspaces/{workspace_id}/reports/{row.id}/export")
    assert resp.status_code == 200
    assert resp.content.startswith(b"# Mock")
