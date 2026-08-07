# =============================================================================
# File: test_extractions_api.py
# Module/Service: Extraction Service (FR7 Part 5)
# Layer: Presentation / Service
# Purpose: API + Celery orchestration tests for async Extractions.
# Responsibilities:
#   - POST 202 / RBAC / invalid type+format / cross-workspace
#   - GET list history + detail states; DELETE 204 + no recreate
#   - Celery process_extraction completion; entities enqueue without LLM
# Dependencies:
#   - pytest, httpx, ExtractionService fakes
# Public Exports:
#   - N/A
# Database/Table: N/A (in-memory fakes; no Postgres/Redis)
# Related Modules: app.api.extractions, app.workers.extractions
# Important Notes: Enqueue stubbed; LLM injected only in Celery unit path.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.adapters.llm_result import StructuredLlmResult
from app.api.extractions import get_extraction_service
from app.core.config import Settings
from app.core.rate_limit import InMemoryWorkspaceRateLimiter, get_workspace_rate_limiter
from app.db.session import get_db_session
from app.dependencies.auth import CurrentUser, get_current_user
from app.main import app
from app.models.artifacts import Extraction
from app.models.documents import Document, DocumentVersion
from app.models.enums import (
    DocumentVersionStatus,
    ExtractionOutputFormat,
    ExtractionStatus,
    ExtractionType,
    FileType,
    RoleName,
)
from app.repositories.extractions import EntityReuseRow
from app.repositories.retrieval import ChunkHydrationRow
from app.repositories.workspace_members import WorkspaceMemberRepository
from app.services.extraction.extraction_service import ExtractionService
from app.workers.extractions import run_extraction_generation

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeSession:
    async def commit(self) -> None:
        return None

    async def flush(self) -> None:
        return None


class FakeDocumentRepo:
    def __init__(self) -> None:
        self.documents: dict[uuid.UUID, Document] = {}
        self.versions: dict[uuid.UUID, DocumentVersion] = {}

    async def get_document(
        self, workspace_id: uuid.UUID, document_id: uuid.UUID
    ) -> Document | None:
        doc = self.documents.get(document_id)
        if doc is None or doc.workspace_id != workspace_id:
            return None
        return doc

    async def get_document_by_id(self, document_id: uuid.UUID) -> Document | None:
        return self.documents.get(document_id)

    async def get_version(
        self,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> DocumentVersion | None:
        doc = await self.get_document(workspace_id, document_id)
        if doc is None:
            return None
        ver = self.versions.get(version_id)
        if ver is None or ver.document_id != document_id:
            return None
        return ver


class FakeRetrievalRepo:
    def __init__(self) -> None:
        self.chunks_by_version: dict[uuid.UUID, list[ChunkHydrationRow]] = {}

    async def list_chunks_for_document(
        self,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        *,
        version_id: uuid.UUID | None = None,
    ) -> list[ChunkHydrationRow]:
        del workspace_id, document_id
        if version_id is None:
            return []
        return list(self.chunks_by_version.get(version_id, []))


class FakeExtractionRepo:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, Extraction] = {}
        self.entities: list[EntityReuseRow] = []

    async def create_processing(self, **kwargs: Any) -> Extraction:
        row = Extraction(
            id=uuid.uuid4(),
            document_id=kwargs["document_id"],
            created_by=kwargs["created_by"],
            source_version_id=kwargs["source_version_id"],
            extraction_type=kwargs["extraction_type"],
            output_format=kwargs["output_format"],
            status=ExtractionStatus.processing,
            result_json=None,
            model_used=None,
            prompt_tokens=0,
            completion_tokens=0,
            cost_usd=Decimal("0"),
            latency_ms=None,
            created_at=datetime.now(UTC),
        )
        self.rows[row.id] = row
        return row

    async def get(
        self, *, workspace_id: uuid.UUID, extraction_id: uuid.UUID
    ) -> Extraction | None:
        row = self.rows.get(extraction_id)
        if row is None:
            return None
        # Workspace check delegated via document map in fixture — here trust caller.
        del workspace_id
        return row

    async def get_by_id(self, extraction_id: uuid.UUID) -> Extraction | None:
        return self.rows.get(extraction_id)

    async def list_for_document(
        self, *, workspace_id: uuid.UUID, document_id: uuid.UUID
    ) -> list[Extraction]:
        del workspace_id
        items = [r for r in self.rows.values() if r.document_id == document_id]
        return sorted(items, key=lambda r: r.created_at, reverse=True)

    async def update_generation_result(
        self, *, extraction_id: uuid.UUID, **kwargs: Any
    ) -> bool:
        row = self.rows.get(extraction_id)
        if row is None or row.status != ExtractionStatus.processing:
            return False
        row.result_json = kwargs["result_json"]
        row.model_used = kwargs["model_used"]
        row.prompt_tokens = kwargs["prompt_tokens"]
        row.completion_tokens = kwargs["completion_tokens"]
        row.cost_usd = kwargs["cost_usd"]
        row.latency_ms = kwargs["latency_ms"]
        row.status = ExtractionStatus.completed
        return True

    async def mark_failed(self, *, extraction_id: uuid.UUID) -> bool:
        row = self.rows.get(extraction_id)
        if row is None or row.status != ExtractionStatus.processing:
            return False
        row.status = ExtractionStatus.failed
        row.result_json = None
        return True

    async def delete(self, extraction: Extraction) -> None:
        self.rows.pop(extraction.id, None)

    async def list_entities_for_version(
        self,
        *,
        workspace_id: uuid.UUID,
        source_version_id: uuid.UUID,
    ) -> list[EntityReuseRow]:
        del workspace_id, source_version_id
        return list(self.entities)


def _settings() -> Settings:
    return Settings(
        chat_llm_provider="anthropic",
        anthropic_api_key="test-key",
        chat_answer_light_model="claude-light-test",
        chat_answer_strong_model="claude-strong-test",
    )


@pytest.fixture
def workspace_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def docs_repo() -> FakeDocumentRepo:
    return FakeDocumentRepo()


@pytest.fixture
def extractions_repo() -> FakeExtractionRepo:
    return FakeExtractionRepo()


@pytest.fixture
def retrieval_repo() -> FakeRetrievalRepo:
    return FakeRetrievalRepo()


@pytest.fixture
def enqueued() -> list[uuid.UUID]:
    return []


def _seed_document(
    docs: FakeDocumentRepo,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    version_number: int = 1,
) -> tuple[Document, DocumentVersion]:
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    version = DocumentVersion(
        id=version_id,
        document_id=document_id,
        uploaded_by=user_id,
        version_number=version_number,
        storage_path=f"workspaces/{workspace_id}/documents/{document_id}/v{version_number}/a.pdf",
        file_size_bytes=100,
        checksum_sha256="c" * 64,
        status=DocumentVersionStatus.ready,
        is_current=True,
    )
    document = Document(
        id=document_id,
        workspace_id=workspace_id,
        current_version_id=version_id,
        title="Doc",
        file_type=FileType.pdf,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    docs.documents[document_id] = document
    docs.versions[version_id] = version
    return document, version


@pytest.fixture
async def client(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    docs_repo: FakeDocumentRepo,
    extractions_repo: FakeExtractionRepo,
    retrieval_repo: FakeRetrievalRepo,
    enqueued: list[uuid.UUID],
):
    from unittest.mock import AsyncMock

    allowed_ws = workspace_id

    async def _override_user() -> CurrentUser:
        return CurrentUser(id=user_id, email="u@example.com", full_name="U")

    async def _override_db() -> Any:
        yield FakeSession()

    def _override_service() -> ExtractionService:
        # Enforce workspace on get for detail/delete
        original_get = extractions_repo.get

        async def _scoped_get(
            *, workspace_id: uuid.UUID, extraction_id: uuid.UUID
        ) -> Extraction | None:
            row = await original_get(workspace_id=workspace_id, extraction_id=extraction_id)
            if row is None:
                return None
            doc = docs_repo.documents.get(row.document_id)
            if doc is None or doc.workspace_id != workspace_id:
                return None
            return row

        extractions_repo.get = _scoped_get  # type: ignore[method-assign]
        return ExtractionService(
            settings=_settings(),
            session=FakeSession(),  # type: ignore[arg-type]
            documents=docs_repo,  # type: ignore[arg-type]
            retrieval=retrieval_repo,  # type: ignore[arg-type]
            extractions=extractions_repo,  # type: ignore[arg-type]
            enqueue=True,
            enqueue_fn=lambda eid: enqueued.append(eid),
        )

    async def _role_side_effect(*, user_id: uuid.UUID, workspace_id: uuid.UUID) -> RoleName | None:
        del user_id
        if workspace_id != allowed_ws:
            return None
        return getattr(app.state, "test_role", RoleName.editor)

    get_workspace_rate_limiter.cache_clear()
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_db_session] = _override_db
    app.dependency_overrides[get_extraction_service] = _override_service
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


# ---------------------------------------------------------------------------
# POST
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [RoleName.admin, RoleName.editor])
async def test_post_extraction_accepted(
    client: AsyncClient,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    docs_repo: FakeDocumentRepo,
    extractions_repo: FakeExtractionRepo,
    enqueued: list[uuid.UUID],
    role: RoleName,
) -> None:
    _set_role(role)
    document, version = _seed_document(docs_repo, workspace_id=workspace_id, user_id=user_id)
    resp = await client.post(
        f"/workspaces/{workspace_id}/documents/{document.id}/extractions",
        json={"extraction_type": "table", "output_format": "json"},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "processing"
    assert body["result"] is None
    assert body["extraction_type"] == "table"
    assert body["output_format"] == "json"
    assert body["document_id"] == str(document.id)
    assert "id" in body and "created_at" in body
    assert len(extractions_repo.rows) == 1
    row = next(iter(extractions_repo.rows.values()))
    assert row.source_version_id == version.id
    assert enqueued == [row.id]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extraction_type",
    ["table", "figures", "entities", "timeline"],
)
async def test_post_all_extraction_types(
    client: AsyncClient,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    docs_repo: FakeDocumentRepo,
    extractions_repo: FakeExtractionRepo,
    enqueued: list[uuid.UUID],
    extraction_type: str,
) -> None:
    _set_role(RoleName.editor)
    document, version = _seed_document(docs_repo, workspace_id=workspace_id, user_id=user_id)
    # Clear shared fixtures between parametrized runs
    extractions_repo.rows.clear()
    enqueued.clear()

    resp = await client.post(
        f"/workspaces/{workspace_id}/documents/{document.id}/extractions",
        json={"extraction_type": extraction_type},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "processing"
    assert body["result"] is None
    assert body["extraction_type"] == extraction_type
    assert len(extractions_repo.rows) == 1
    row = next(iter(extractions_repo.rows.values()))
    assert row.source_version_id == version.id
    assert enqueued == [row.id]


@pytest.mark.asyncio
@pytest.mark.parametrize("output_format", ["json", "table"])
async def test_post_output_formats_accepted(
    client: AsyncClient,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    docs_repo: FakeDocumentRepo,
    extractions_repo: FakeExtractionRepo,
    enqueued: list[uuid.UUID],
    output_format: str,
) -> None:
    _set_role(RoleName.editor)
    document, _ = _seed_document(docs_repo, workspace_id=workspace_id, user_id=user_id)
    extractions_repo.rows.clear()
    enqueued.clear()

    resp = await client.post(
        f"/workspaces/{workspace_id}/documents/{document.id}/extractions",
        json={"extraction_type": "figures", "output_format": output_format},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["output_format"] == output_format
    assert body["status"] == "processing"
    assert len(enqueued) == 1


@pytest.mark.asyncio
async def test_post_invalid_extraction_type_422(
    client: AsyncClient,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    docs_repo: FakeDocumentRepo,
    extractions_repo: FakeExtractionRepo,
    enqueued: list[uuid.UUID],
) -> None:
    _set_role(RoleName.editor)
    document, _ = _seed_document(docs_repo, workspace_id=workspace_id, user_id=user_id)
    resp = await client.post(
        f"/workspaces/{workspace_id}/documents/{document.id}/extractions",
        json={"extraction_type": "epic"},
    )
    assert resp.status_code == 422
    assert extractions_repo.rows == {}
    assert enqueued == []


@pytest.mark.asyncio
async def test_post_invalid_output_format_422(
    client: AsyncClient,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    docs_repo: FakeDocumentRepo,
    extractions_repo: FakeExtractionRepo,
    enqueued: list[uuid.UUID],
) -> None:
    _set_role(RoleName.editor)
    document, _ = _seed_document(docs_repo, workspace_id=workspace_id, user_id=user_id)
    resp = await client.post(
        f"/workspaces/{workspace_id}/documents/{document.id}/extractions",
        json={"extraction_type": "table", "output_format": "csv"},
    )
    assert resp.status_code == 422
    assert extractions_repo.rows == {}
    assert enqueued == []


@pytest.mark.asyncio
async def test_post_viewer_forbidden(
    client: AsyncClient,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    docs_repo: FakeDocumentRepo,
) -> None:
    _set_role(RoleName.viewer)
    document, _ = _seed_document(docs_repo, workspace_id=workspace_id, user_id=user_id)
    resp = await client.post(
        f"/workspaces/{workspace_id}/documents/{document.id}/extractions",
        json={"extraction_type": "table"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_post_cross_workspace_document_404(
    client: AsyncClient,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    docs_repo: FakeDocumentRepo,
) -> None:
    _set_role(RoleName.editor)
    other_ws = uuid.uuid4()
    document, _ = _seed_document(docs_repo, workspace_id=other_ws, user_id=user_id)
    resp = await client.post(
        f"/workspaces/{workspace_id}/documents/{document.id}/extractions",
        json={"extraction_type": "table"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET list / detail / DELETE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [RoleName.admin, RoleName.editor, RoleName.viewer])
async def test_get_list_all_roles(
    client: AsyncClient,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    docs_repo: FakeDocumentRepo,
    extractions_repo: FakeExtractionRepo,
    role: RoleName,
) -> None:
    _set_role(role)
    document, v1 = _seed_document(docs_repo, workspace_id=workspace_id, user_id=user_id)
    v2_id = uuid.uuid4()
    docs_repo.versions[v2_id] = DocumentVersion(
        id=v2_id,
        document_id=document.id,
        uploaded_by=user_id,
        version_number=2,
        storage_path="x",
        file_size_bytes=1,
        checksum_sha256="d" * 64,
        status=DocumentVersionStatus.ready,
        is_current=True,
    )
    older = Extraction(
        id=uuid.uuid4(),
        document_id=document.id,
        created_by=user_id,
        source_version_id=v1.id,
        extraction_type=ExtractionType.table,
        output_format=ExtractionOutputFormat.json,
        status=ExtractionStatus.completed,
        result_json={"headers": ["A"], "rows": []},
        created_at=datetime.now(UTC) - timedelta(hours=2),
        prompt_tokens=0,
        completion_tokens=0,
        cost_usd=Decimal("0"),
    )
    newer = Extraction(
        id=uuid.uuid4(),
        document_id=document.id,
        created_by=user_id,
        source_version_id=v2_id,
        extraction_type=ExtractionType.entities,
        output_format=ExtractionOutputFormat.json,
        status=ExtractionStatus.completed,
        result_json={"entities": []},
        created_at=datetime.now(UTC) - timedelta(hours=1),
        prompt_tokens=0,
        completion_tokens=0,
        cost_usd=Decimal("0"),
    )
    extractions_repo.rows[older.id] = older
    extractions_repo.rows[newer.id] = newer

    resp = await client.get(f"/workspaces/{workspace_id}/documents/{document.id}/extractions")
    assert resp.status_code == 200
    body = resp.json()
    assert [item["id"] for item in body] == [str(newer.id), str(older.id)]
    assert {item["extraction_type"] for item in body} == {"table", "entities"}
    assert {item["document_id"] for item in body} == {str(document.id)}


@pytest.mark.asyncio
async def test_get_detail_states(
    client: AsyncClient,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    docs_repo: FakeDocumentRepo,
    extractions_repo: FakeExtractionRepo,
) -> None:
    _set_role(RoleName.viewer)
    document, version = _seed_document(docs_repo, workspace_id=workspace_id, user_id=user_id)

    processing = Extraction(
        id=uuid.uuid4(),
        document_id=document.id,
        created_by=user_id,
        source_version_id=version.id,
        extraction_type=ExtractionType.table,
        output_format=ExtractionOutputFormat.json,
        status=ExtractionStatus.processing,
        result_json=None,
        created_at=datetime.now(UTC),
        prompt_tokens=0,
        completion_tokens=0,
        cost_usd=Decimal("0"),
    )
    completed = Extraction(
        id=uuid.uuid4(),
        document_id=document.id,
        created_by=user_id,
        source_version_id=version.id,
        extraction_type=ExtractionType.table,
        output_format=ExtractionOutputFormat.json,
        status=ExtractionStatus.completed,
        result_json={"headers": ["Year"], "rows": [{"Year": 2024}]},
        created_at=datetime.now(UTC),
        prompt_tokens=1,
        completion_tokens=1,
        cost_usd=Decimal("0.1"),
    )
    failed = Extraction(
        id=uuid.uuid4(),
        document_id=document.id,
        created_by=user_id,
        source_version_id=version.id,
        extraction_type=ExtractionType.table,
        output_format=ExtractionOutputFormat.json,
        status=ExtractionStatus.failed,
        result_json=None,
        created_at=datetime.now(UTC),
        prompt_tokens=0,
        completion_tokens=0,
        cost_usd=Decimal("0"),
    )
    for row in (processing, completed, failed):
        extractions_repo.rows[row.id] = row

    r1 = await client.get(f"/workspaces/{workspace_id}/extractions/{processing.id}")
    assert r1.status_code == 200
    assert r1.json()["result"] is None
    assert r1.json()["status"] == "processing"

    r2 = await client.get(f"/workspaces/{workspace_id}/extractions/{completed.id}")
    assert r2.status_code == 200
    assert r2.json()["result"] == {"headers": ["Year"], "rows": [{"Year": 2024}]}
    assert r2.json()["status"] == "completed"

    r3 = await client.get(f"/workspaces/{workspace_id}/extractions/{failed.id}")
    assert r3.status_code == 200
    assert r3.json()["status"] == "failed"
    assert r3.json()["result"] is None

    r4 = await client.get(f"/workspaces/{workspace_id}/extractions/{uuid.uuid4()}")
    assert r4.status_code == 404

    other_ws = uuid.uuid4()
    r5 = await client.get(f"/workspaces/{other_ws}/extractions/{completed.id}")
    # Non-member of other workspace → 403 (existing RBAC convention)
    assert r5.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [RoleName.admin, RoleName.editor])
async def test_delete_extraction(
    client: AsyncClient,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    docs_repo: FakeDocumentRepo,
    extractions_repo: FakeExtractionRepo,
    role: RoleName,
) -> None:
    _set_role(role)
    document, version = _seed_document(docs_repo, workspace_id=workspace_id, user_id=user_id)
    row = Extraction(
        id=uuid.uuid4(),
        document_id=document.id,
        created_by=user_id,
        source_version_id=version.id,
        extraction_type=ExtractionType.table,
        output_format=ExtractionOutputFormat.json,
        status=ExtractionStatus.processing,
        result_json=None,
        created_at=datetime.now(UTC),
        prompt_tokens=0,
        completion_tokens=0,
        cost_usd=Decimal("0"),
    )
    extractions_repo.rows[row.id] = row

    resp = await client.delete(f"/workspaces/{workspace_id}/extractions/{row.id}")
    assert resp.status_code == 204
    assert row.id not in extractions_repo.rows
    # Document + version untouched
    assert document.id in docs_repo.documents
    assert version.id in docs_repo.versions

    list_resp = await client.get(
        f"/workspaces/{workspace_id}/documents/{document.id}/extractions"
    )
    assert list_resp.status_code == 200
    assert list_resp.json() == []


@pytest.mark.asyncio
async def test_delete_viewer_forbidden(
    client: AsyncClient,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    docs_repo: FakeDocumentRepo,
    extractions_repo: FakeExtractionRepo,
) -> None:
    _set_role(RoleName.viewer)
    document, version = _seed_document(docs_repo, workspace_id=workspace_id, user_id=user_id)
    row_id = uuid.uuid4()
    extractions_repo.rows[row_id] = Extraction(
        id=row_id,
        document_id=document.id,
        created_by=user_id,
        source_version_id=version.id,
        extraction_type=ExtractionType.table,
        output_format=ExtractionOutputFormat.json,
        status=ExtractionStatus.completed,
        result_json={"headers": ["X"], "rows": []},
        created_at=datetime.now(UTC),
        prompt_tokens=0,
        completion_tokens=0,
        cost_usd=Decimal("0"),
    )
    resp = await client.delete(f"/workspaces/{workspace_id}/extractions/{row_id}")
    assert resp.status_code == 403
    assert row_id in extractions_repo.rows


@pytest.mark.asyncio
async def test_delete_processing_then_celery_does_not_recreate() -> None:
    extractions = FakeExtractionRepo()
    missing = uuid.uuid4()
    svc = ExtractionService(
        settings=_settings(),
        session=FakeSession(),  # type: ignore[arg-type]
        documents=FakeDocumentRepo(),  # type: ignore[arg-type]
        retrieval=FakeRetrievalRepo(),  # type: ignore[arg-type]
        extractions=extractions,  # type: ignore[arg-type]
        enqueue=False,
    )
    assert await svc.process_extraction(missing) is None
    assert extractions.rows == {}


# ---------------------------------------------------------------------------
# Celery worker body
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_celery_run_extraction_generation_completed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()
    docs = FakeDocumentRepo()
    document, version = _seed_document(docs, workspace_id=workspace_id, user_id=user_id)
    retrieval = FakeRetrievalRepo()
    retrieval.chunks_by_version[version.id] = [
        ChunkHydrationRow(
            chunk_id=uuid.uuid4(),
            document_id=document.id,
            document_version_id=version.id,
            workspace_id=workspace_id,
            content="Year Revenue\n2024 1000",
            title="Doc",
            chunk_index=0,
        )
    ]
    extractions = FakeExtractionRepo()
    row = await extractions.create_processing(
        document_id=document.id,
        created_by=user_id,
        source_version_id=version.id,
        extraction_type=ExtractionType.table,
        output_format=ExtractionOutputFormat.json,
    )

    class _CM:
        def __init__(self, session: FakeSession) -> None:
            self._session = session

        async def __aenter__(self) -> FakeSession:
            return self._session

        async def __aexit__(self, *args: Any) -> None:
            del args

    session = FakeSession()

    def _factory() -> _CM:
        return _CM(session)

    async def _llm(**kwargs: Any) -> StructuredLlmResult:
        return StructuredLlmResult(
            data={
                "headers": ["Year", "Revenue"],
                "rows": [{"Year": 2024, "Revenue": 1000}],
            },
            model=kwargs["model"],
            input_tokens=9,
            output_tokens=4,
            estimated_cost_usd=0.002,
        )

    def _build_service(**kwargs: Any) -> ExtractionService:
        return ExtractionService(
            settings=_settings(),
            session=session,  # type: ignore[arg-type]
            documents=docs,  # type: ignore[arg-type]
            retrieval=retrieval,  # type: ignore[arg-type]
            extractions=extractions,  # type: ignore[arg-type]
            llm_call=_llm,
            enqueue=False,
        )

    monkeypatch.setattr("app.workers.extractions.async_session_factory", _factory)
    monkeypatch.setattr("app.workers.extractions.ExtractionService", _build_service)
    monkeypatch.setattr("app.workers.extractions.DocumentRepository", lambda s: docs)
    monkeypatch.setattr("app.workers.extractions.RetrievalRepository", lambda s: retrieval)
    monkeypatch.setattr("app.workers.extractions.ExtractionRepository", lambda s: extractions)

    result = await run_extraction_generation(row.id)
    assert result["status"] == "completed"
    assert extractions.rows[row.id].result_json == {
        "headers": ["Year", "Revenue"],
        "rows": [{"Year": 2024, "Revenue": 1000}],
    }
    # table prefers strong model
    assert extractions.rows[row.id].model_used == "claude-strong-test"
    assert extractions.rows[row.id].prompt_tokens == 9
    assert extractions.rows[row.id].completion_tokens == 4
    assert extractions.rows[row.id].cost_usd == Decimal("0.002")
    assert extractions.rows[row.id].source_version_id == version.id


# ---------------------------------------------------------------------------
# Entities: HTTP enqueue only; reuse path has zero LLM
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_entities_enqueues_without_llm(
    client: AsyncClient,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    docs_repo: FakeDocumentRepo,
    extractions_repo: FakeExtractionRepo,
    retrieval_repo: FakeRetrievalRepo,
    enqueued: list[uuid.UUID],
) -> None:
    _set_role(RoleName.editor)
    document, version = _seed_document(docs_repo, workspace_id=workspace_id, user_id=user_id)

    resp = await client.post(
        f"/workspaces/{workspace_id}/documents/{document.id}/extractions",
        json={"extraction_type": "entities"},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "processing"
    assert body["result"] is None
    assert body["extraction_type"] == "entities"
    assert len(enqueued) == 1
    row_id = uuid.UUID(body["id"])
    assert row_id in extractions_repo.rows

    # HTTP path must not generate — only enqueue. Process separately via reuse.
    entity_id = uuid.uuid4()
    extractions_repo.entities = [
        EntityReuseRow(
            id=entity_id,
            name="Acme Corp",
            type="ORG",
            description="Customer",
        )
    ]
    llm_calls = {"n": 0}

    async def _llm(**kwargs: Any) -> StructuredLlmResult:
        llm_calls["n"] += 1
        del kwargs
        raise AssertionError("entities REUSE path must not call LLM")

    svc = ExtractionService(
        settings=_settings(),
        session=FakeSession(),  # type: ignore[arg-type]
        documents=docs_repo,  # type: ignore[arg-type]
        retrieval=retrieval_repo,  # type: ignore[arg-type]
        extractions=extractions_repo,  # type: ignore[arg-type]
        llm_call=_llm,
        enqueue=False,
    )
    final = await svc.process_extraction(row_id)
    assert final is not None
    assert final.status == ExtractionStatus.completed
    assert svc.llm_call_count == 0
    assert llm_calls["n"] == 0
    assert final.result_json is not None
    assert final.result_json["entities"][0]["name"] == "Acme Corp"
    assert final.source_version_id == version.id
