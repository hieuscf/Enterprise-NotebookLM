# =============================================================================
# File: test_documents.py
# Module/Service: Document Ingestion Service
# Layer: Presentation / Service
# Purpose: Unit tests for FR2 Step 1 — Upload & Versioning API.
# Responsibilities:
#   - Upload tạo đủ documents + document_versions + pipeline_runs
#   - Version 2 → version 1 is_current=false; set-current processing → 400
#   - Viewer upload → 403
# Dependencies:
#   - pytest, httpx, in-memory fake repos (no Postgres/MinIO in CI)
# Public Exports:
#   - N/A
# Database/Table: N/A (fakes)
# Related Modules: app.services.documents, app.api.documents
# Important Notes: Enqueue is stubbed; pipeline body is out of Step 1 scope.
# =============================================================================

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.adapters.minio_storage import get_minio_storage
from app.api.documents import get_document_service
from app.core.rate_limit import InMemoryWorkspaceRateLimiter, get_workspace_rate_limiter
from app.db.session import get_db_session
from app.dependencies.auth import CurrentUser, get_current_user
from app.main import app
from app.models.documents import Document, DocumentVersion
from app.models.enums import DocumentVersionStatus, FileType, PipelineStatus, RoleName
from app.models.pipeline import PipelineRun
from app.repositories.workspace_members import WorkspaceMemberRepository
from app.services.documents import (
    DocumentIngestionError,
    DocumentIngestionService,
    build_storage_path,
    detect_file_type,
    hash_upload_stream,
)

# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------


class FakeMinio:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def ensure_bucket(self) -> None:
        return None

    def upload_bytes(self, *, object_key: str, data: bytes, content_type: str = "") -> str:
        self.objects[object_key] = data
        return object_key

    def upload_stream(
        self,
        *,
        object_key: str,
        stream: Any,
        length: int,
        content_type: str = "",
    ) -> str:
        data = stream.read(length)
        self.objects[object_key] = data
        return object_key

    def download_bytes(self, object_key: str) -> bytes:
        return self.objects[object_key]

    def delete_object(self, object_key: str) -> None:
        self.objects.pop(object_key, None)


class FakeSession:
    def __init__(self) -> None:
        self.committed = False

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True


class FakeDocRepo:
    def __init__(self) -> None:
        self.documents: dict[uuid.UUID, Document] = {}
        self.versions: dict[uuid.UUID, DocumentVersion] = {}

    async def create_document(
        self,
        *,
        workspace_id: uuid.UUID,
        title: str,
        file_type: FileType,
    ) -> Document:
        now = datetime.now(UTC)
        doc = Document(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            title=title,
            file_type=file_type,
            current_version_id=None,
            created_at=now,
            updated_at=now,
        )
        self.documents[doc.id] = doc
        return doc

    async def get_document(
        self, workspace_id: uuid.UUID, document_id: uuid.UUID
    ) -> Document | None:
        doc = self.documents.get(document_id)
        if doc is None or doc.workspace_id != workspace_id:
            return None
        return doc

    async def list_versions(
        self, workspace_id: uuid.UUID, document_id: uuid.UUID
    ) -> list[DocumentVersion]:
        doc = self.documents.get(document_id)
        if doc is None or doc.workspace_id != workspace_id:
            return []
        rows = [v for v in self.versions.values() if v.document_id == document_id]
        return sorted(rows, key=lambda v: v.version_number, reverse=True)

    async def get_version(
        self,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> DocumentVersion | None:
        ver = self.versions.get(version_id)
        if ver is None or ver.document_id != document_id:
            return None
        doc = self.documents.get(document_id)
        if doc is None or doc.workspace_id != workspace_id:
            return None
        return ver

    async def next_version_number(self, document_id: uuid.UUID) -> int:
        nums = [v.version_number for v in self.versions.values() if v.document_id == document_id]
        return (max(nums) if nums else 0) + 1

    async def clear_current_flags(self, document_id: uuid.UUID) -> None:
        for ver in self.versions.values():
            if ver.document_id == document_id:
                ver.is_current = False

    async def create_version(
        self,
        *,
        document_id: uuid.UUID,
        uploaded_by: uuid.UUID,
        version_number: int,
        storage_path: str,
        file_size_bytes: int,
        checksum_sha256: str,
        is_current: bool,
        status: DocumentVersionStatus = DocumentVersionStatus.processing,
    ) -> DocumentVersion:
        ver = DocumentVersion(
            id=uuid.uuid4(),
            document_id=document_id,
            uploaded_by=uploaded_by,
            version_number=version_number,
            storage_path=storage_path,
            file_size_bytes=file_size_bytes,
            checksum_sha256=checksum_sha256,
            page_count=None,
            status=status,
            is_current=is_current,
            created_at=datetime.now(UTC),
        )
        self.versions[ver.id] = ver
        return ver

    async def set_current_version(self, document: Document, version: DocumentVersion) -> Document:
        await self.clear_current_flags(document.id)
        version.is_current = True
        document.current_version_id = version.id
        return document


class FakePipelineRepo:
    def __init__(self) -> None:
        self.runs: list[PipelineRun] = []

    async def create_run(self, document_version_id: uuid.UUID) -> PipelineRun:
        run = PipelineRun(
            id=uuid.uuid4(),
            document_version_id=document_version_id,
            status=PipelineStatus.pending,
            retry_count=0,
        )
        self.runs.append(run)
        return run


async def _chunks_from_bytes(data: bytes, chunk_size: int = 4):
    for i in range(0, len(data), chunk_size):
        yield data[i : i + chunk_size]


def _wire_service(
    session: FakeSession,
    storage: FakeMinio,
    docs: FakeDocRepo,
    pipeline: FakePipelineRepo,
    *,
    enqueue: bool = True,
) -> DocumentIngestionService:
    service = DocumentIngestionService(session, storage, enqueue=enqueue)  # type: ignore[arg-type]
    service._docs = docs  # type: ignore[method-assign]
    service._pipeline = pipeline  # type: ignore[method-assign]
    return service


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_detect_file_type_and_storage_path() -> None:
    assert detect_file_type("report.PDF") == FileType.pdf
    with pytest.raises(DocumentIngestionError) as exc:
        detect_file_type("virus.exe")
    assert exc.value.status_code == 400

    ws, doc = uuid.uuid4(), uuid.uuid4()
    path = build_storage_path(
        workspace_id=ws,
        document_id=doc,
        version_number=1,
        filename="a/b.txt",
    )
    assert path == f"workspaces/{ws}/documents/{doc}/v1/a_b.txt"


@pytest.mark.asyncio
async def test_hash_upload_stream_chunked() -> None:
    payload = b"hello-enterprise-notebooklm" * 20
    result = await hash_upload_stream(_chunks_from_bytes(payload, chunk_size=7))
    assert result.checksum_sha256 == hashlib.sha256(payload).hexdigest()
    assert result.file_size_bytes == len(payload)
    assert result.stream.read() == payload
    result.stream.close()


# ---------------------------------------------------------------------------
# Service unit tests (Step 1 acceptance)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_creates_document_version_and_pipeline_run(monkeypatch) -> None:
    session = FakeSession()
    storage = FakeMinio()
    docs = FakeDocRepo()
    pipeline = FakePipelineRepo()
    service = _wire_service(session, storage, docs, pipeline)

    enqueued: list[str] = []
    monkeypatch.setattr(
        "app.workers.pipeline.run_pipeline.delay",
        lambda run_id: enqueued.append(run_id),
    )

    ws = uuid.uuid4()
    user = uuid.uuid4()
    payload = b"%PDF-1.4 fake content for checksum"
    result = await service.upload_new(
        workspace_id=ws,
        uploaded_by=user,
        title="Q1 Report",
        filename="q1.pdf",
        file_chunks=_chunks_from_bytes(payload),
    )

    assert len(docs.documents) == 1
    assert len(docs.versions) == 1
    assert len(pipeline.runs) == 1
    assert session.committed is True

    doc = result.document
    ver = result.version
    run = result.pipeline_run
    assert doc.current_version_id == ver.id
    assert ver.version_number == 1
    assert ver.is_current is True
    assert ver.status == DocumentVersionStatus.processing
    assert ver.page_count is None
    assert ver.checksum_sha256 == hashlib.sha256(payload).hexdigest()
    assert ver.storage_path == (f"workspaces/{ws}/documents/{doc.id}/v1/q1.pdf")
    assert run.document_version_id == ver.id
    assert run.status == PipelineStatus.pending
    assert ver.storage_path in storage.objects
    assert enqueued == [str(run.id)]


@pytest.mark.asyncio
async def test_upload_version_2_clears_is_current_on_v1(monkeypatch) -> None:
    session = FakeSession()
    storage = FakeMinio()
    docs = FakeDocRepo()
    pipeline = FakePipelineRepo()
    service = _wire_service(session, storage, docs, pipeline)
    monkeypatch.setattr("app.workers.pipeline.run_pipeline.delay", lambda _rid: None)

    ws = uuid.uuid4()
    user = uuid.uuid4()
    first = await service.upload_new(
        workspace_id=ws,
        uploaded_by=user,
        title="Doc",
        filename="a.txt",
        file_chunks=_chunks_from_bytes(b"version-one"),
    )
    v1 = first.version
    assert v1.is_current is True

    second = await service.upload_new_version(
        workspace_id=ws,
        document_id=first.document.id,
        uploaded_by=user,
        filename="a.txt",
        file_chunks=_chunks_from_bytes(b"version-two"),
    )
    v2 = second.version
    # Re-read v1 from store (same object mutated by clear_current_flags)
    assert docs.versions[v1.id].is_current is False
    assert v2.is_current is True
    assert v2.version_number == 2
    assert first.document.current_version_id == v2.id
    assert len(pipeline.runs) == 2
    assert v2.storage_path.endswith("/v2/a.txt")


@pytest.mark.asyncio
async def test_set_current_processing_returns_400() -> None:
    session = FakeSession()
    storage = FakeMinio()
    docs = FakeDocRepo()
    pipeline = FakePipelineRepo()
    service = _wire_service(session, storage, docs, pipeline, enqueue=False)

    ws = uuid.uuid4()
    doc = await docs.create_document(workspace_id=ws, title="D", file_type=FileType.txt)
    ver = await docs.create_version(
        document_id=doc.id,
        uploaded_by=uuid.uuid4(),
        version_number=1,
        storage_path="workspaces/x/documents/y/v1/a.txt",
        file_size_bytes=3,
        checksum_sha256="abc",
        is_current=True,
        status=DocumentVersionStatus.processing,
    )
    doc.current_version_id = ver.id

    with pytest.raises(DocumentIngestionError) as exc:
        await service.set_current_version(
            workspace_id=ws,
            document_id=doc.id,
            version_id=ver.id,
        )
    assert exc.value.status_code == 400
    assert exc.value.code == "version_not_ready"


@pytest.mark.asyncio
async def test_set_current_ready_succeeds() -> None:
    session = FakeSession()
    storage = FakeMinio()
    docs = FakeDocRepo()
    pipeline = FakePipelineRepo()
    service = _wire_service(session, storage, docs, pipeline, enqueue=False)

    ws = uuid.uuid4()
    doc = await docs.create_document(workspace_id=ws, title="D", file_type=FileType.txt)
    v1 = await docs.create_version(
        document_id=doc.id,
        uploaded_by=uuid.uuid4(),
        version_number=1,
        storage_path="p1",
        file_size_bytes=1,
        checksum_sha256="a",
        is_current=True,
        status=DocumentVersionStatus.ready,
    )
    v2 = await docs.create_version(
        document_id=doc.id,
        uploaded_by=uuid.uuid4(),
        version_number=2,
        storage_path="p2",
        file_size_bytes=1,
        checksum_sha256="b",
        is_current=False,
        status=DocumentVersionStatus.ready,
    )
    doc.current_version_id = v1.id

    updated = await service.set_current_version(
        workspace_id=ws,
        document_id=doc.id,
        version_id=v2.id,
    )
    assert updated.current_version_id == v2.id
    assert docs.versions[v1.id].is_current is False
    assert docs.versions[v2.id].is_current is True


# ---------------------------------------------------------------------------
# API RBAC
# ---------------------------------------------------------------------------


def _override_user(user: CurrentUser):
    async def _dep() -> CurrentUser:
        return user

    return _dep


async def _fake_db_session():
    yield AsyncMock()


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def workspace_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def current_user(user_id: uuid.UUID) -> CurrentUser:
    return CurrentUser(id=user_id, email="editor@example.com", full_name="Editor")


@pytest.fixture
async def client(current_user: CurrentUser):
    app.dependency_overrides[get_db_session] = _fake_db_session
    app.dependency_overrides[get_workspace_rate_limiter] = lambda: InMemoryWorkspaceRateLimiter()
    app.dependency_overrides[get_current_user] = _override_user(current_user)
    app.dependency_overrides[get_minio_storage] = lambda: FakeMinio()  # type: ignore[return-value]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_viewer_upload_forbidden(client, workspace_id: uuid.UUID):
    with patch.object(
        WorkspaceMemberRepository,
        "get_role_for_user",
        new=AsyncMock(return_value=RoleName.viewer),
    ):
        resp = await client.post(
            f"/workspaces/{workspace_id}/documents",
            data={"title": "Hello"},
            files={"file": ("hello.txt", b"hello", "text/plain")},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_api_set_current_processing_returns_400(
    client, workspace_id: uuid.UUID, current_user: CurrentUser
):
    service = MagicMock()
    service.set_current_version = AsyncMock(
        side_effect=DocumentIngestionError(
            "version_not_ready",
            "Cannot set-current: version status is 'processing', "
            "only versions with status 'ready' can become current",
            status_code=400,
        )
    )
    app.dependency_overrides[get_document_service] = lambda: service

    with patch.object(
        WorkspaceMemberRepository,
        "get_role_for_user",
        new=AsyncMock(return_value=RoleName.editor),
    ):
        resp = await client.post(
            f"/workspaces/{workspace_id}/documents/{uuid.uuid4()}/versions/{uuid.uuid4()}/set-current"
        )

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "version_not_ready"
