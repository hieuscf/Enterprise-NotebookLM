# =============================================================================
# File: test_comparisons_api.py
# Module/Service: Comparison Service (FR8 Part 2)
# Layer: Presentation / Service
# Purpose: API integration tests for async Comparisons (happy path + RBAC).
# Responsibilities:
#   - POST 202 processing; GET detail; DELETE 204
#   - Viewer mutate → 403; cross-workspace document → 404
# Dependencies:
#   - pytest, httpx, ComparisonService fakes
# Public Exports:
#   - N/A
# Database/Table: N/A (in-memory fakes; no Postgres/Redis)
# Related Modules: app.api.comparisons, app.workers.comparisons
# Important Notes: Enqueue stubbed; no real LLM calls.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.comparisons import get_comparison_service
from app.core.config import Settings
from app.core.rate_limit import InMemoryWorkspaceRateLimiter, get_workspace_rate_limiter
from app.db.session import get_db_session
from app.dependencies.auth import CurrentUser, get_current_user
from app.main import app
from app.models.artifacts import Comparison, Summary
from app.models.documents import Document, DocumentVersion
from app.models.enums import (
    ComparisonStatus,
    DocumentVersionStatus,
    FileType,
    RoleName,
    SummaryStatus,
    SummaryType,
)
from app.repositories.comparisons import ComparisonWithDocuments
from app.repositories.retrieval import ChunkHydrationRow
from app.repositories.workspace_members import WorkspaceMemberRepository
from app.services.comparison.comparison_service import ComparisonService


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

    async def list_top_chunks_by_topic(
        self,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        *,
        version_id: uuid.UUID,
        focus: str | None = None,
        limit: int = 8,
    ) -> list[ChunkHydrationRow]:
        del workspace_id, document_id, focus
        return list(self.chunks_by_version.get(version_id, []))[:limit]


class FakeSummaryRepo:
    def __init__(self) -> None:
        self.by_version: dict[uuid.UUID, Summary] = {}

    async def get_latest_completed_for_version(
        self,
        *,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        source_version_id: uuid.UUID,
    ) -> Summary | None:
        del workspace_id, document_id
        return self.by_version.get(source_version_id)


class FakeComparisonRepo:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, ComparisonWithDocuments] = {}
        self._links: dict[uuid.UUID, list[uuid.UUID]] = {}

    async def create_processing(self, **kwargs: Any) -> ComparisonWithDocuments:
        row = Comparison(
            id=uuid.uuid4(),
            workspace_id=kwargs["workspace_id"],
            created_by=kwargs["created_by"],
            title=kwargs.get("title"),
            focus=kwargs.get("focus"),
            status=ComparisonStatus.processing,
            result=None,
            created_at=datetime.now(UTC),
        )
        doc_ids = list(kwargs["document_ids"])
        outcome = ComparisonWithDocuments(comparison=row, document_ids=doc_ids)
        self.rows[row.id] = outcome
        self._links[row.id] = doc_ids
        return outcome

    async def get_by_id(self, comparison_id: uuid.UUID) -> Comparison | None:
        item = self.rows.get(comparison_id)
        return item.comparison if item else None

    async def list_document_ids(self, comparison_id: uuid.UUID) -> list[uuid.UUID]:
        return list(self._links.get(comparison_id, []))

    async def list_for_workspace(
        self,
        *,
        workspace_id: uuid.UUID,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[ComparisonWithDocuments]:
        items = [
            r for r in self.rows.values() if r.comparison.workspace_id == workspace_id
        ]
        items.sort(key=lambda r: r.comparison.created_at, reverse=True)
        sliced = items[offset:]
        if limit is not None:
            sliced = sliced[:limit]
        return sliced

    async def get(
        self, *, workspace_id: uuid.UUID, comparison_id: uuid.UUID
    ) -> ComparisonWithDocuments | None:
        item = self.rows.get(comparison_id)
        if item is None or item.comparison.workspace_id != workspace_id:
            return None
        return item

    async def update_generation_result(self, **kwargs: Any) -> bool:
        item = self.rows.get(kwargs["comparison_id"])
        if item is None or item.comparison.status != ComparisonStatus.processing:
            return False
        item.comparison.result = kwargs["result"]
        item.comparison.status = ComparisonStatus.completed
        if kwargs.get("title") is not None:
            item.comparison.title = kwargs["title"]
        return True

    async def mark_failed(self, *, comparison_id: uuid.UUID) -> bool:
        item = self.rows.get(comparison_id)
        if item is None or item.comparison.status != ComparisonStatus.processing:
            return False
        item.comparison.status = ComparisonStatus.failed
        item.comparison.result = None
        return True

    async def delete(self, comparison: Comparison) -> None:
        self.rows.pop(comparison.id, None)
        self._links.pop(comparison.id, None)


def _settings() -> Settings:
    return Settings(
        chat_llm_provider="anthropic",
        anthropic_api_key="test-key",
        chat_answer_strong_model="claude-sonnet-test",
    )


def _seed_document(
    docs: FakeDocumentRepo,
    summaries: FakeSummaryRepo,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    title: str = "Doc",
) -> Document:
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    version = DocumentVersion(
        id=version_id,
        document_id=document_id,
        uploaded_by=user_id,
        version_number=1,
        storage_path=f"workspaces/{workspace_id}/documents/{document_id}/v1/a.pdf",
        file_size_bytes=100,
        checksum_sha256="c" * 64,
        status=DocumentVersionStatus.ready,
        is_current=True,
    )
    document = Document(
        id=document_id,
        workspace_id=workspace_id,
        current_version_id=version_id,
        title=title,
        file_type=FileType.pdf,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    docs.documents[document_id] = document
    docs.versions[version_id] = version
    summaries.by_version[version_id] = Summary(
        id=uuid.uuid4(),
        document_id=document_id,
        created_by=user_id,
        source_version_id=version_id,
        type=SummaryType.short,
        status=SummaryStatus.completed,
        content=f"Summary of {title}",
        sections=None,
        model_used="test",
        prompt_tokens=1,
        completion_tokens=1,
        cost_usd=0,
        latency_ms=1,
        created_at=datetime.now(UTC),
    )
    return document


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
def summaries_repo() -> FakeSummaryRepo:
    return FakeSummaryRepo()


@pytest.fixture
def comparisons_repo() -> FakeComparisonRepo:
    return FakeComparisonRepo()


@pytest.fixture
def enqueued() -> list[uuid.UUID]:
    return []


@pytest.fixture
async def client(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    docs_repo: FakeDocumentRepo,
    summaries_repo: FakeSummaryRepo,
    comparisons_repo: FakeComparisonRepo,
    enqueued: list[uuid.UUID],
):
    allowed_ws = workspace_id

    async def _override_user() -> CurrentUser:
        return CurrentUser(id=user_id, email="u@example.com", full_name="U")

    async def _override_db() -> Any:
        yield FakeSession()

    def _override_service() -> ComparisonService:
        return ComparisonService(
            settings=_settings(),
            session=FakeSession(),  # type: ignore[arg-type]
            documents=docs_repo,  # type: ignore[arg-type]
            retrieval=FakeRetrievalRepo(),  # type: ignore[arg-type]
            summaries=summaries_repo,  # type: ignore[arg-type]
            comparisons=comparisons_repo,  # type: ignore[arg-type]
            enqueue=True,
            enqueue_fn=lambda cid: enqueued.append(cid),
        )

    async def _role_side_effect(*, user_id: uuid.UUID, workspace_id: uuid.UUID) -> RoleName | None:
        del user_id
        if workspace_id != allowed_ws:
            return None
        return getattr(app.state, "test_role", RoleName.editor)

    get_workspace_rate_limiter.cache_clear()
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_db_session] = _override_db
    app.dependency_overrides[get_comparison_service] = _override_service
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


@pytest.mark.asyncio
async def test_post_comparison_accepted_happy_path(
    client: AsyncClient,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    docs_repo: FakeDocumentRepo,
    summaries_repo: FakeSummaryRepo,
    enqueued: list[uuid.UUID],
) -> None:
    _set_role(RoleName.editor)
    doc_a = _seed_document(
        docs_repo, summaries_repo, workspace_id=workspace_id, user_id=user_id, title="A"
    )
    doc_b = _seed_document(
        docs_repo, summaries_repo, workspace_id=workspace_id, user_id=user_id, title="B"
    )

    resp = await client.post(
        f"/workspaces/{workspace_id}/comparisons",
        json={"document_ids": [str(doc_a.id), str(doc_b.id)], "focus": "benefits"},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["workspace_id"] == str(workspace_id)
    assert set(body["document_ids"]) == {str(doc_a.id), str(doc_b.id)}
    assert body["status"] == "processing"
    assert body["result"] is None
    assert "id" in body and "created_at" in body
    assert enqueued == [uuid.UUID(body["id"])]

    detail = await client.get(f"/workspaces/{workspace_id}/comparisons/{body['id']}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "processing"

    listed = await client.get(f"/workspaces/{workspace_id}/comparisons?page=1&page_size=20")
    assert listed.status_code == 200
    assert any(item["id"] == body["id"] for item in listed.json())

    deleted = await client.delete(f"/workspaces/{workspace_id}/comparisons/{body['id']}")
    assert deleted.status_code == 204


@pytest.mark.asyncio
async def test_post_comparison_viewer_forbidden(
    client: AsyncClient,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    docs_repo: FakeDocumentRepo,
    summaries_repo: FakeSummaryRepo,
) -> None:
    _set_role(RoleName.viewer)
    doc_a = _seed_document(
        docs_repo, summaries_repo, workspace_id=workspace_id, user_id=user_id, title="A"
    )
    doc_b = _seed_document(
        docs_repo, summaries_repo, workspace_id=workspace_id, user_id=user_id, title="B"
    )
    resp = await client.post(
        f"/workspaces/{workspace_id}/comparisons",
        json={"document_ids": [str(doc_a.id), str(doc_b.id)]},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_post_cross_workspace_document_404(
    client: AsyncClient,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    docs_repo: FakeDocumentRepo,
    summaries_repo: FakeSummaryRepo,
) -> None:
    _set_role(RoleName.editor)
    other_ws = uuid.uuid4()
    doc_a = _seed_document(
        docs_repo, summaries_repo, workspace_id=workspace_id, user_id=user_id, title="A"
    )
    doc_other = _seed_document(
        docs_repo, summaries_repo, workspace_id=other_ws, user_id=user_id, title="Other"
    )
    resp = await client.post(
        f"/workspaces/{workspace_id}/comparisons",
        json={"document_ids": [str(doc_a.id), str(doc_other.id)]},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "not_found"
