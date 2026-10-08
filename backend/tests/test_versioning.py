# =============================================================================
# File: test_versioning.py
# Module/Service: Document Ingestion Service
# Layer: Service
# Purpose: Tests for version classification, edit history, and rollback.
# Responsibilities:
#   - Tag and metadata validation
#   - Classification writes an event only when values change
#   - Rollback refuses the current version and non-ready versions
#   - Viewer cannot rollback or retag
# Dependencies:
#   - pytest, httpx, in-memory fakes
# Public Exports:
#   - N/A
# Database/Table: N/A (fakes)
# Related Modules: app.services.versioning, app.services.documents, app.api.documents
# Important Notes: Does not require Postgres. Upload event recording is covered
#   by the shared FakeDocRepo used in test_documents.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.documents import get_document_service, get_versioning_service
from app.core.rate_limit import InMemoryWorkspaceRateLimiter, get_workspace_rate_limiter
from app.db.session import get_db_session
from app.dependencies.auth import CurrentUser, get_current_user
from app.main import app
from app.models.documents import Document, DocumentVersion
from app.models.enums import AiAnalysisStatus, DocumentVersionStatus, FileType, RoleName
from app.repositories.workspace_members import WorkspaceMemberRepository
from app.services.documents import DocumentIngestionError, DocumentIngestionService
from app.services.versioning import UNSET, VersioningService, normalize_metadata, normalize_tags


def test_normalize_tags_dedupes_and_casefolds() -> None:
    assert normalize_tags(["  Hợp đồng ", "hợp đồng", "Nội-bộ"]) == ["hợp đồng", "nội-bộ"]


def test_normalize_tags_rejects_symbols() -> None:
    with pytest.raises(DocumentIngestionError) as exc:
        normalize_tags(["ok", "bad/tag"])
    assert exc.value.code == "invalid_tag"


def test_normalize_metadata_trims_and_rejects_long_values() -> None:
    assert normalize_metadata({"  Phòng ban ": " Pháp chế "}) == {"Phòng ban": "Pháp chế"}
    with pytest.raises(DocumentIngestionError) as exc:
        normalize_metadata({"note": "x" * 501})
    assert exc.value.code == "invalid_metadata"


class _FakeDocs:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.documents: dict[uuid.UUID, Document] = {}
        self.versions: dict[uuid.UUID, DocumentVersion] = {}

    def add_document(self, workspace_id: uuid.UUID) -> Document:
        now = datetime.now(UTC)
        doc = Document(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            title="Hợp đồng",
            file_type=FileType.pdf,
            current_version_id=None,
            created_at=now,
            updated_at=now,
        )
        self.documents[doc.id] = doc
        return doc

    def add_version(
        self,
        document: Document,
        *,
        number: int,
        current: bool,
        status: DocumentVersionStatus = DocumentVersionStatus.ready,
    ) -> DocumentVersion:
        version = DocumentVersion(
            id=uuid.uuid4(),
            document_id=document.id,
            uploaded_by=uuid.uuid4(),
            version_number=number,
            storage_path=f"v{number}",
            file_size_bytes=10,
            checksum_sha256="abc",
            status=status,
            ai_analysis_status=AiAnalysisStatus.not_analyzed,
            is_current=current,
            tags=[],
            classification_metadata={},
            change_note=None,
            created_at=datetime.now(UTC),
        )
        self.versions[version.id] = version
        if current:
            document.current_version_id = version.id
        return version

    async def get_version(self, workspace_id, document_id, version_id):
        version = self.versions.get(version_id)
        document = self.documents.get(document_id)
        if (
            version is None
            or document is None
            or version.document_id != document_id
            or document.workspace_id != workspace_id
        ):
            return None
        return version

    async def get_document(self, workspace_id, document_id):
        document = self.documents.get(document_id)
        if document is None or document.workspace_id != workspace_id:
            return None
        return document

    async def add_version_event(self, **kwargs):
        self.events.append(kwargs)

    async def apply_version_labels(
        self,
        version,
        *,
        tags=None,
        classification_metadata=None,
        change_note=None,
        update_note=False,
    ):
        if tags is not None:
            version.tags = tags
        if classification_metadata is not None:
            version.classification_metadata = classification_metadata
        if update_note:
            version.change_note = change_note
        return version

    async def set_current_version(self, document, version):
        for item in self.versions.values():
            if item.document_id == document.id:
                item.is_current = False
        version.is_current = True
        document.current_version_id = version.id
        return document


def _versioning(fake: _FakeDocs) -> VersioningService:
    service = VersioningService(AsyncMock())
    service._docs = fake  # type: ignore[assignment]
    return service


def _ingestion(fake: _FakeDocs) -> DocumentIngestionService:
    service = DocumentIngestionService(AsyncMock(), AsyncMock(), enqueue=False)
    service._docs = fake  # type: ignore[assignment]
    return service


@pytest.mark.asyncio
async def test_update_classification_records_only_real_changes() -> None:
    fake = _FakeDocs()
    workspace_id = uuid.uuid4()
    document = fake.add_document(workspace_id)
    version = fake.add_version(document, number=2, current=True)
    actor = uuid.uuid4()
    service = _versioning(fake)

    updated = await service.update_classification(
        workspace_id=workspace_id,
        document_id=document.id,
        version_id=version.id,
        actor_id=actor,
        tags=["Hợp đồng", "hợp đồng"],
        classification_metadata={"Phòng ban": "Pháp chế"},
        change_note="  Sửa điều 3  ",
    )

    assert updated.tags == ["hợp đồng"]
    assert updated.classification_metadata == {"Phòng ban": "Pháp chế"}
    assert updated.change_note == "Sửa điều 3"
    assert [event["event_type"] for event in fake.events] == [
        "tags_updated",
        "metadata_updated",
        "metadata_updated",
    ]

    await service.update_classification(
        workspace_id=workspace_id,
        document_id=document.id,
        version_id=version.id,
        actor_id=actor,
        tags=["hợp đồng"],
        classification_metadata={"Phòng ban": "Pháp chế"},
        change_note="Sửa điều 3",
    )
    assert len(fake.events) == 3


@pytest.mark.asyncio
async def test_rollback_switches_current_and_records_event() -> None:
    fake = _FakeDocs()
    workspace_id = uuid.uuid4()
    document = fake.add_document(workspace_id)
    older = fake.add_version(document, number=1, current=False)
    current = fake.add_version(document, number=2, current=True)
    actor = uuid.uuid4()
    service = _ingestion(fake)

    updated = await service.rollback_version(
        workspace_id=workspace_id,
        document_id=document.id,
        version_id=older.id,
        actor_id=actor,
    )

    assert updated.current_version_id == older.id
    assert current.is_current is False
    assert older.is_current is True
    assert fake.events[-1]["event_type"] == "rolled_back"
    assert fake.events[-1]["actor_id"] == actor


@pytest.mark.asyncio
async def test_rollback_rejects_current_and_unready_versions() -> None:
    fake = _FakeDocs()
    workspace_id = uuid.uuid4()
    document = fake.add_document(workspace_id)
    current = fake.add_version(document, number=1, current=True)
    failed = fake.add_version(
        document,
        number=2,
        current=False,
        status=DocumentVersionStatus.failed,
    )
    service = _ingestion(fake)
    actor = uuid.uuid4()

    with pytest.raises(DocumentIngestionError) as current_exc:
        await service.rollback_version(
            workspace_id=workspace_id,
            document_id=document.id,
            version_id=current.id,
            actor_id=actor,
        )
    assert current_exc.value.code == "already_current"

    with pytest.raises(DocumentIngestionError) as failed_exc:
        await service.rollback_version(
            workspace_id=workspace_id,
            document_id=document.id,
            version_id=failed.id,
            actor_id=actor,
        )
    assert failed_exc.value.code == "version_not_ready"
    assert fake.events == []


@pytest.mark.asyncio
async def test_omitted_note_is_left_unchanged() -> None:
    fake = _FakeDocs()
    workspace_id = uuid.uuid4()
    document = fake.add_document(workspace_id)
    version = fake.add_version(document, number=1, current=True)
    version.change_note = "Giữ nguyên"
    service = _versioning(fake)

    updated = await service.update_classification(
        workspace_id=workspace_id,
        document_id=document.id,
        version_id=version.id,
        actor_id=uuid.uuid4(),
        tags=["nội bộ"],
        classification_metadata=None,
        change_note=UNSET,
    )
    assert updated.change_note == "Giữ nguyên"
    assert updated.tags == ["nội bộ"]
    assert len(fake.events) == 1


@pytest.fixture
def workspace_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
async def client():
    user = CurrentUser(id=uuid.uuid4(), email="editor@example.com", full_name="Editor")

    async def _user() -> CurrentUser:
        return user

    async def _db():
        yield AsyncMock()

    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[get_workspace_rate_limiter] = lambda: InMemoryWorkspaceRateLimiter()
    app.dependency_overrides[get_current_user] = _user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_viewer_cannot_rollback_or_retag(client, workspace_id: uuid.UUID) -> None:
    with patch.object(
        WorkspaceMemberRepository,
        "get_role_for_user",
        new=AsyncMock(return_value=RoleName.viewer),
    ):
        rollback = await client.post(
            f"/workspaces/{workspace_id}/documents/{uuid.uuid4()}/versions/{uuid.uuid4()}/rollback"
        )
        retag = await client.patch(
            f"/workspaces/{workspace_id}/documents/{uuid.uuid4()}/versions/{uuid.uuid4()}",
            json={"tags": ["nội bộ"]},
        )
    assert rollback.status_code == 403
    assert retag.status_code == 403


@pytest.mark.asyncio
async def test_editor_rollback_route_calls_service(client, workspace_id: uuid.UUID) -> None:
    service = AsyncMock()
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    service.rollback_version = AsyncMock(
        return_value=Document(
            id=document_id,
            workspace_id=workspace_id,
            title="Hợp đồng",
            file_type=FileType.pdf,
            current_version_id=version_id,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    app.dependency_overrides[get_document_service] = lambda: service
    with patch.object(
        WorkspaceMemberRepository,
        "get_role_for_user",
        new=AsyncMock(return_value=RoleName.editor),
    ):
        response = await client.post(
            f"/workspaces/{workspace_id}/documents/{document_id}/versions/{version_id}/rollback"
        )
    assert response.status_code == 200
    assert response.json()["current_version_id"] == str(version_id)
    service.rollback_version.assert_awaited()


@pytest.mark.asyncio
async def test_member_can_list_version_catalog(client, workspace_id: uuid.UUID) -> None:
    catalog = AsyncMock()
    catalog.list_catalog = AsyncMock(
        return_value=type(
            "Page",
            (),
            {"items": [], "page": 1, "page_size": 20, "total": 0, "available_tags": ["nội bộ"]},
        )()
    )
    app.dependency_overrides[get_versioning_service] = lambda: catalog
    with patch.object(
        WorkspaceMemberRepository,
        "get_role_for_user",
        new=AsyncMock(return_value=RoleName.viewer),
    ):
        response = await client.get(f"/workspaces/{workspace_id}/versions")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["available_tags"] == ["nội bộ"]
