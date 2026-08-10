# =============================================================================
# File: test_admin_documents.py
# Module/Service: Document Ingestion Service / Admin Console (FR2, FR12)
# Layer: Presentation
# Purpose: Unit tests for GET /admin/documents* (Manage-only).
# Responsibilities:
#   - Auth: Manage 200; Workspace Admin / editor / viewer / anon → 403/401
#   - List pagination/filter params accepted; detail/versions 404 path
# Dependencies:
#   - pytest, httpx, app.main
# Public Exports:
#   - N/A
# Database/Table: N/A (dependency overrides; no Postgres in CI)
# Related Modules: app.api.admin_documents
# Important Notes: Service fakes — no live DB required.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.admin_documents import get_admin_document_service
from app.dependencies.auth import CurrentUser, get_current_user
from app.main import app
from app.models.enums import DocumentVersionStatus, FileType, PlatformRole
from app.repositories.admin_documents import (
    AdminDocumentRow,
    AdminDocumentSummaryCounts,
)
from app.services.admin_documents import (
    AdminDocumentDetailResult,
    AdminDocumentError,
    AdminDocumentListResult,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeDocument:
    def __init__(
        self,
        *,
        title: str = "Annual Report",
        file_type: FileType = FileType.pdf,
        workspace_id: uuid.UUID | None = None,
        doc_id: uuid.UUID | None = None,
    ) -> None:
        self.id = doc_id or uuid.uuid4()
        self.workspace_id = workspace_id or uuid.uuid4()
        self.title = title
        self.file_type = file_type
        self.current_version_id = uuid.uuid4()
        now = datetime.now(UTC)
        self.created_at = now
        self.updated_at = now


class FakeVersion:
    def __init__(
        self,
        *,
        document_id: uuid.UUID,
        version_id: uuid.UUID | None = None,
        status: DocumentVersionStatus = DocumentVersionStatus.ready,
        version_number: int = 1,
    ) -> None:
        self.id = version_id or uuid.uuid4()
        self.document_id = document_id
        self.uploaded_by = uuid.uuid4()
        self.version_number = version_number
        self.storage_path = (
            f"workspaces/{uuid.uuid4()}/documents/{document_id}/v{version_number}/report.pdf"
        )
        self.file_size_bytes = 2_500_000
        self.checksum_sha256 = "a" * 64
        self.page_count = 12
        self.status = status
        self.is_current = True
        from app.models.enums import PreviewStatus

        self.preview_status = PreviewStatus.pending
        self.preview_type = None
        self.preview_generated_at = None
        self.created_at = datetime.now(UTC)


class FakeAdminDocumentService:
    def __init__(self) -> None:
        self.doc = FakeDocument()
        self.ver = FakeVersion(document_id=self.doc.id, version_id=self.doc.current_version_id)
        self.list_calls: list[dict[str, Any]] = []

    async def list_documents(self, **kwargs: Any) -> AdminDocumentListResult:
        self.list_calls.append(kwargs)
        row = AdminDocumentRow(
            document=self.doc,  # type: ignore[arg-type]
            workspace_name="Finance",
            current_version=self.ver,  # type: ignore[arg-type]
        )
        return AdminDocumentListResult(
            items=[row],
            page=kwargs.get("page", 1),
            page_size=kwargs.get("page_size", 20),
            total=1,
            summary=AdminDocumentSummaryCounts(
                total=1, processing=0, ready=1, failed=0
            ),
        )

    async def get_document(self, document_id: uuid.UUID) -> AdminDocumentDetailResult:
        if document_id != self.doc.id:
            raise AdminDocumentError("not_found", "Document not found.", status_code=404)
        row = AdminDocumentRow(
            document=self.doc,  # type: ignore[arg-type]
            workspace_name="Finance",
            current_version=self.ver,  # type: ignore[arg-type]
        )
        return AdminDocumentDetailResult(
            row=row,
            filename="report.pdf",
            latest_pipeline_run=None,
        )

    async def list_versions(self, document_id: uuid.UUID) -> list[Any]:
        if document_id != self.doc.id:
            raise AdminDocumentError("not_found", "Document not found.", status_code=404)
        return [self.ver]


@pytest.fixture
def manage_user() -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        email="manage@example.com",
        full_name="Manage",
        platform_role=PlatformRole.manage,
    )


@pytest.fixture
def workspace_admin() -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        email="ws-admin@example.com",
        full_name="WS Admin",
        platform_role=None,
    )


@pytest.fixture
def editor_user() -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        email="editor@example.com",
        full_name="Editor",
        platform_role=None,
    )


@pytest.fixture
def fake_service() -> FakeAdminDocumentService:
    return FakeAdminDocumentService()


def _override_manage(user: CurrentUser, service: FakeAdminDocumentService) -> None:
    async def _user() -> CurrentUser:
        return user

    def _svc() -> FakeAdminDocumentService:
        return service

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_admin_document_service] = _svc


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_forbidden_for_workspace_admin(
    workspace_admin: CurrentUser,
    fake_service: FakeAdminDocumentService,
) -> None:
    _override_manage(workspace_admin, fake_service)
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/admin/documents")
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "forbidden"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_forbidden_for_editor(
    editor_user: CurrentUser,
    fake_service: FakeAdminDocumentService,
) -> None:
    _override_manage(editor_user, fake_service)
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/admin/documents")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_unauthorized_without_user() -> None:
    app.dependency_overrides.clear()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/admin/documents")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_ok_for_manage(
    manage_user: CurrentUser,
    fake_service: FakeAdminDocumentService,
) -> None:
    _override_manage(manage_user, fake_service)
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/admin/documents",
                params={
                    "page": 1,
                    "page_size": 20,
                    "status": "ready",
                    "file_type": "pdf",
                    "search": "Annual",
                    "sort": "updated_at",
                    "order": "desc",
                },
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["summary"]["ready"] == 1
        assert body["items"][0]["workspace_name"] == "Finance"
        assert body["items"][0]["filename"] == "report.pdf"
        assert body["items"][0]["status"] == "ready"
        assert fake_service.list_calls
        call = fake_service.list_calls[0]
        assert call["status"] == DocumentVersionStatus.ready
        assert call["file_type"] == FileType.pdf
        assert call["search"] == "Annual"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_detail_ok_and_not_found(
    manage_user: CurrentUser,
    fake_service: FakeAdminDocumentService,
) -> None:
    _override_manage(manage_user, fake_service)
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            ok = await client.get(f"/admin/documents/{fake_service.doc.id}")
            missing = await client.get(f"/admin/documents/{uuid.uuid4()}")
        assert ok.status_code == 200
        assert ok.json()["title"] == "Annual Report"
        assert ok.json()["current_version"]["version_number"] == 1
        assert missing.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_versions_ok(
    manage_user: CurrentUser,
    fake_service: FakeAdminDocumentService,
) -> None:
    _override_manage(manage_user, fake_service)
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                f"/admin/documents/{fake_service.doc.id}/versions"
            )
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["status"] == "ready"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_detail_forbidden_for_workspace_admin(
    workspace_admin: CurrentUser,
    fake_service: FakeAdminDocumentService,
) -> None:
    _override_manage(workspace_admin, fake_service)
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/admin/documents/{fake_service.doc.id}")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_filename_from_storage_path() -> None:
    from app.repositories.admin_documents import filename_from_storage_path

    assert (
        filename_from_storage_path(
            "workspaces/ws/documents/doc/v1/Annual Report 2026.pdf"
        )
        == "Annual Report 2026.pdf"
    )
    assert filename_from_storage_path(None) is None
    assert filename_from_storage_path("") is None
