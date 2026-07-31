# =============================================================================
# File: test_search_api.py
# Module/Service: Search Service
# Layer: Presentation / Service
# Purpose: Unit tests for Search API + history (FR3 / UC3 Part 2).
# Responsibilities:
#   - POST /search calls HybridRetrievalService and writes search_history
#   - Filters, history isolation, retrieval failure → no history write
# Dependencies:
#   - pytest, httpx ASGITransport, fakes (no live Qdrant/ES/Neo4j/Postgres)
# Public Exports:
#   - N/A
# Database/Table: N/A (fakes)
# Related Modules: app.api.search, app.services.search
# Important Notes: Hybrid retrieval is mocked — never re-tested here.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.search import get_search_service
from app.core.rate_limit import InMemoryWorkspaceRateLimiter, get_workspace_rate_limiter
from app.db.session import get_db_session
from app.dependencies.auth import CurrentUser, get_current_user
from app.main import app
from app.models.enums import FileType, RoleName
from app.models.query import SearchHistory
from app.repositories.retrieval import MetadataDocumentRow
from app.repositories.workspace_members import WorkspaceMemberRepository
from app.schemas.search import SearchRequest
from app.services.retrieval.exceptions import RetrievalUnavailableError
from app.services.retrieval.schemas import RetrievalCandidate, RetrievalResult
from app.services.search import SearchService, SearchServiceError

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeSession:
    async def flush(self) -> None:
        return None


class FakeHistoryRepo:
    def __init__(self) -> None:
        self.rows: list[SearchHistory] = []

    async def create(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        query_text: str,
        filters: dict[str, Any] | None,
        results_count: int,
    ) -> SearchHistory:
        row = SearchHistory(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            user_id=user_id,
            query_text=query_text,
            filters=filters,
            results_count=results_count,
            clicked_document_id=None,
            created_at=datetime.now(UTC),
        )
        self.rows.append(row)
        return row

    async def list_for_user(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[SearchHistory], int]:
        matched = [
            r
            for r in self.rows
            if r.workspace_id == workspace_id and r.user_id == user_id
        ]
        matched.sort(key=lambda r: r.created_at, reverse=True)
        start = (page - 1) * page_size
        return matched[start : start + page_size], len(matched)

    async def get_for_user(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        history_id: uuid.UUID,
    ) -> SearchHistory | None:
        for row in self.rows:
            if (
                row.id == history_id
                and row.workspace_id == workspace_id
                and row.user_id == user_id
            ):
                return row
        return None

    async def set_clicked_document(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        history_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> SearchHistory | None:
        row = await self.get_for_user(
            workspace_id=workspace_id,
            user_id=user_id,
            history_id=history_id,
        )
        if row is None:
            return None
        row.clicked_document_id = document_id
        return row


class FakeRetrievalRepo:
    def __init__(self, meta: dict[uuid.UUID, MetadataDocumentRow] | None = None) -> None:
        self.meta = meta or {}

    async def documents_meta_by_ids(
        self,
        workspace_id: uuid.UUID,
        document_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, MetadataDocumentRow]:
        return {
            did: row
            for did, row in self.meta.items()
            if did in document_ids and row.workspace_id == workspace_id
        }


def _candidate(
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
    *,
    method: str = "rerank",
    score: float = 0.9,
    rank: int = 1,
    text: str = "leave policy snippet",
) -> RetrievalCandidate:
    return RetrievalCandidate(
        workspace_id=workspace_id,
        document_id=document_id,
        chunk_id=uuid.uuid4(),
        text_snippet=text,
        retrieval_method=method,
        raw_score=score,
        score=score,
        rank=rank,
        source_methods=["vector", "bm25"],
    )


@pytest.fixture
def workspace_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def user_a() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def user_b() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# Service-level tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_calls_hybrid_and_writes_history(
    workspace_id: uuid.UUID,
    user_a: uuid.UUID,
) -> None:
    doc_id = uuid.uuid4()
    hybrid = AsyncMock()
    hybrid.retrieve = AsyncMock(
        return_value=RetrievalResult(
            items=[_candidate(workspace_id, doc_id)],
            latency_ms=42,
            sources_used=["vector", "bm25"],
            timings={},
        )
    )
    history = FakeHistoryRepo()
    service = SearchService(
        hybrid=hybrid,
        history_repo=history,  # type: ignore[arg-type]
        retrieval_repo=FakeRetrievalRepo(),  # type: ignore[arg-type]
    )

    resp = await service.search(
        workspace_id=workspace_id,
        user_id=user_a,
        body=SearchRequest(query_text="leave policy", top_k=10),
    )

    hybrid.retrieve.assert_awaited_once()
    assert resp.results_count == 1
    assert resp.results[0].document_id == doc_id
    assert resp.results[0].rank == 1
    assert len(history.rows) == 1
    assert history.rows[0].query_text == "leave policy"
    assert history.rows[0].results_count == 1
    assert history.rows[0].clicked_document_id is None
    assert resp.history_id == history.rows[0].id


@pytest.mark.asyncio
async def test_search_applies_file_type_filter(
    workspace_id: uuid.UUID,
    user_a: uuid.UUID,
) -> None:
    pdf_id = uuid.uuid4()
    docx_id = uuid.uuid4()
    now = datetime.now(UTC)
    meta = {
        pdf_id: MetadataDocumentRow(
            document_id=pdf_id,
            workspace_id=workspace_id,
            title="PDF Doc",
            file_type=FileType.pdf,
            created_at=now,
            updated_at=now,
            uploaded_by=None,
            version_number=1,
            status="ready",
        ),
        docx_id: MetadataDocumentRow(
            document_id=docx_id,
            workspace_id=workspace_id,
            title="DOCX Doc",
            file_type=FileType.docx,
            created_at=now,
            updated_at=now,
            uploaded_by=None,
            version_number=1,
            status="ready",
        ),
    }
    hybrid = AsyncMock()
    hybrid.retrieve = AsyncMock(
        return_value=RetrievalResult(
            items=[
                _candidate(workspace_id, pdf_id, rank=1, text="pdf hit"),
                _candidate(workspace_id, docx_id, rank=2, text="docx hit"),
            ],
            latency_ms=10,
            sources_used=["vector"],
            timings={},
        )
    )
    history = FakeHistoryRepo()
    service = SearchService(
        hybrid=hybrid,
        history_repo=history,  # type: ignore[arg-type]
        retrieval_repo=FakeRetrievalRepo(meta),  # type: ignore[arg-type]
    )

    resp = await service.search(
        workspace_id=workspace_id,
        user_id=user_a,
        body=SearchRequest(
            query_text="policy",
            filters={"file_type": "pdf"},
            top_k=10,
        ),
    )

    assert resp.results_count == 1
    assert resp.results[0].document_id == pdf_id
    assert history.rows[0].filters == {"file_type": "pdf"}


@pytest.mark.asyncio
async def test_history_only_current_user_newest_first_paginated(
    workspace_id: uuid.UUID,
    user_a: uuid.UUID,
    user_b: uuid.UUID,
) -> None:
    history = FakeHistoryRepo()
    base = datetime.now(UTC)
    for i, (uid, q) in enumerate(
        [
            (user_a, "a-old"),
            (user_b, "b-secret"),
            (user_a, "a-mid"),
            (user_a, "a-new"),
        ]
    ):
        row = SearchHistory(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            user_id=uid,
            query_text=q,
            filters=None,
            results_count=i,
            clicked_document_id=None,
            created_at=base + timedelta(seconds=i),
        )
        history.rows.append(row)

    service = SearchService(
        hybrid=AsyncMock(),
        history_repo=history,  # type: ignore[arg-type]
        retrieval_repo=FakeRetrievalRepo(),  # type: ignore[arg-type]
    )
    page1 = await service.list_history(
        workspace_id=workspace_id,
        user_id=user_a,
        page=1,
        page_size=2,
    )
    assert [h.query_text for h in page1] == ["a-new", "a-mid"]
    page2 = await service.list_history(
        workspace_id=workspace_id,
        user_id=user_a,
        page=2,
        page_size=2,
    )
    assert [h.query_text for h in page2] == ["a-old"]


@pytest.mark.asyncio
async def test_other_user_cannot_read_history(
    workspace_id: uuid.UUID,
    user_a: uuid.UUID,
    user_b: uuid.UUID,
) -> None:
    history = FakeHistoryRepo()
    history.rows.append(
        SearchHistory(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            user_id=user_a,
            query_text="private query",
            filters=None,
            results_count=3,
            clicked_document_id=None,
            created_at=datetime.now(UTC),
        )
    )
    service = SearchService(
        hybrid=AsyncMock(),
        history_repo=history,  # type: ignore[arg-type]
        retrieval_repo=FakeRetrievalRepo(),  # type: ignore[arg-type]
    )
    items = await service.list_history(
        workspace_id=workspace_id,
        user_id=user_b,
        page=1,
        page_size=20,
    )
    assert items == []


@pytest.mark.asyncio
async def test_retrieval_failure_does_not_write_history(
    workspace_id: uuid.UUID,
    user_a: uuid.UUID,
) -> None:
    hybrid = AsyncMock()
    hybrid.retrieve = AsyncMock(side_effect=RetrievalUnavailableError("all down"))
    history = FakeHistoryRepo()
    service = SearchService(
        hybrid=hybrid,
        history_repo=history,  # type: ignore[arg-type]
        retrieval_repo=FakeRetrievalRepo(),  # type: ignore[arg-type]
    )

    with pytest.raises(SearchServiceError) as exc_info:
        await service.search(
            workspace_id=workspace_id,
            user_id=user_a,
            body=SearchRequest(query_text="anything"),
        )
    assert exc_info.value.status_code == 503
    assert history.rows == []


# ---------------------------------------------------------------------------
# HTTP-level smoke (dependency overrides)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_search_http_ok(
    workspace_id: uuid.UUID,
    user_a: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc_id = uuid.uuid4()
    hybrid = AsyncMock()
    hybrid.retrieve = AsyncMock(
        return_value=RetrievalResult(
            items=[_candidate(workspace_id, doc_id)],
            latency_ms=5,
            sources_used=["bm25"],
            timings={},
        )
    )
    history = FakeHistoryRepo()
    service = SearchService(
        hybrid=hybrid,
        history_repo=history,  # type: ignore[arg-type]
        retrieval_repo=FakeRetrievalRepo(),  # type: ignore[arg-type]
    )

    async def _user() -> CurrentUser:
        return CurrentUser(id=user_a, email="a@example.com", full_name="A")

    async def _role(
        self: Any,
        *,
        user_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> RoleName | None:
        if workspace_id == ws_id and user_id == user_a:
            return RoleName.viewer
        return None

    ws_id = workspace_id

    async def _db():
        yield FakeSession()

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[get_search_service] = lambda: service
    app.dependency_overrides[get_workspace_rate_limiter] = (
        lambda: InMemoryWorkspaceRateLimiter()
    )
    monkeypatch.setattr(
        WorkspaceMemberRepository,
        "get_role_for_user",
        _role,
    )

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/workspaces/{workspace_id}/search",
                json={"query_text": "leave", "top_k": 5},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["results_count"] == 1
    assert payload["results"][0]["document_id"] == str(doc_id)
    assert payload["history_id"] == str(history.rows[0].id)
    assert len(history.rows) == 1


@pytest.mark.asyncio
async def test_record_click_idempotent(
    workspace_id: uuid.UUID,
    user_a: uuid.UUID,
) -> None:
    doc_id = uuid.uuid4()
    now = datetime.now(UTC)
    history = FakeHistoryRepo()
    row = SearchHistory(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        user_id=user_a,
        query_text="leave",
        filters=None,
        results_count=1,
        clicked_document_id=None,
        created_at=now,
    )
    history.rows.append(row)
    meta = {
        doc_id: MetadataDocumentRow(
            document_id=doc_id,
            workspace_id=workspace_id,
            title="Doc",
            file_type=FileType.pdf,
            created_at=now,
            updated_at=now,
            uploaded_by=None,
            version_number=1,
            status="ready",
        )
    }
    service = SearchService(
        hybrid=AsyncMock(),
        history_repo=history,  # type: ignore[arg-type]
        retrieval_repo=FakeRetrievalRepo(meta),  # type: ignore[arg-type]
    )

    first = await service.record_click(
        workspace_id=workspace_id,
        user_id=user_a,
        history_id=row.id,
        clicked_document_id=doc_id,
    )
    second = await service.record_click(
        workspace_id=workspace_id,
        user_id=user_a,
        history_id=row.id,
        clicked_document_id=doc_id,
    )
    assert first.clicked_document_id == doc_id
    assert second.clicked_document_id == doc_id


@pytest.mark.asyncio
async def test_record_click_other_user_history_not_found(
    workspace_id: uuid.UUID,
    user_a: uuid.UUID,
    user_b: uuid.UUID,
) -> None:
    doc_id = uuid.uuid4()
    now = datetime.now(UTC)
    history = FakeHistoryRepo()
    history.rows.append(
        SearchHistory(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            user_id=user_a,
            query_text="secret",
            filters=None,
            results_count=1,
            clicked_document_id=None,
            created_at=now,
        )
    )
    meta = {
        doc_id: MetadataDocumentRow(
            document_id=doc_id,
            workspace_id=workspace_id,
            title="Doc",
            file_type=FileType.pdf,
            created_at=now,
            updated_at=now,
            uploaded_by=None,
            version_number=1,
            status="ready",
        )
    }
    service = SearchService(
        hybrid=AsyncMock(),
        history_repo=history,  # type: ignore[arg-type]
        retrieval_repo=FakeRetrievalRepo(meta),  # type: ignore[arg-type]
    )
    with pytest.raises(SearchServiceError) as exc_info:
        await service.record_click(
            workspace_id=workspace_id,
            user_id=user_b,
            history_id=history.rows[0].id,
            clicked_document_id=doc_id,
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_history_http_isolation(
    workspace_id: uuid.UUID,
    user_a: uuid.UUID,
    user_b: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = FakeHistoryRepo()
    history.rows.append(
        SearchHistory(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            user_id=user_a,
            query_text="only-a",
            filters=None,
            results_count=1,
            clicked_document_id=None,
            created_at=datetime.now(UTC),
        )
    )
    service = SearchService(
        hybrid=AsyncMock(),
        history_repo=history,  # type: ignore[arg-type]
        retrieval_repo=FakeRetrievalRepo(),  # type: ignore[arg-type]
    )

    async def _user() -> CurrentUser:
        return CurrentUser(id=user_b, email="b@example.com", full_name="B")

    async def _role(
        self: Any,
        *,
        user_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> RoleName | None:
        return RoleName.editor

    async def _db():
        yield FakeSession()

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[get_search_service] = lambda: service
    app.dependency_overrides[get_workspace_rate_limiter] = (
        lambda: InMemoryWorkspaceRateLimiter()
    )
    monkeypatch.setattr(WorkspaceMemberRepository, "get_role_for_user", _role)

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/workspaces/{workspace_id}/search/history")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json() == []
