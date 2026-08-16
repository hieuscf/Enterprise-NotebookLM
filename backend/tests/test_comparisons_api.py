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
            review={},
            comments=[],
            audit=[],
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

    async def update_review(
        self,
        *,
        workspace_id: uuid.UUID,
        comparison_id: uuid.UUID,
        review: dict[str, Any],
    ) -> ComparisonWithDocuments | None:
        item = self.rows.get(comparison_id)
        if item is None or item.comparison.workspace_id != workspace_id:
            return None
        item.comparison.review = dict(review)
        return item

    async def update_comments(
        self,
        *,
        workspace_id: uuid.UUID,
        comparison_id: uuid.UUID,
        comments: list[dict[str, Any]],
    ) -> ComparisonWithDocuments | None:
        item = self.rows.get(comparison_id)
        if item is None or item.comparison.workspace_id != workspace_id:
            return None
        item.comparison.comments = list(comments)
        return item

    async def append_audit(
        self,
        *,
        workspace_id: uuid.UUID,
        comparison_id: uuid.UUID,
        audit: list[dict[str, Any]],
    ) -> ComparisonWithDocuments | None:
        item = self.rows.get(comparison_id)
        if item is None or item.comparison.workspace_id != workspace_id:
            return None
        item.comparison.audit = list(audit)
        return item


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


def _complete_with_clause_report(
    comparisons_repo: FakeComparisonRepo,
    comparison_id: uuid.UUID,
) -> dict[str, Any]:
    item = comparisons_repo.rows[comparison_id]
    result = {
        "similarities": ["Both cap liability."],
        "differences": ["Cap increased."],
        "contract_comparison": {
            "clauses": {
                "modified": [
                    {
                        "clause_id": "CLAUSE:8.2",
                        "status": "MODIFIED",
                        "risk": {"risk_level": "CRITICAL"},
                        "exact_differences": [
                            {
                                "value_type": "MONEY",
                                "old": {"raw": "480,000,000"},
                                "new": {"raw": "600,000,000"},
                            }
                        ],
                        "evidence": [{"evidence_id": "ev-1", "page_number": 4}],
                    }
                ],
                "added": [],
                "removed": [],
                "unchanged": [],
                "unresolved": [],
            }
        },
    }
    item.comparison.status = ComparisonStatus.completed
    item.comparison.result = result
    item.comparison.review = {}
    item.comparison.comments = []
    return result


@pytest.mark.asyncio
async def test_patch_review_does_not_mutate_analysis(
    client: AsyncClient,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    docs_repo: FakeDocumentRepo,
    summaries_repo: FakeSummaryRepo,
    comparisons_repo: FakeComparisonRepo,
) -> None:
    _set_role(RoleName.editor)
    doc_a = _seed_document(
        docs_repo, summaries_repo, workspace_id=workspace_id, user_id=user_id, title="A"
    )
    doc_b = _seed_document(
        docs_repo, summaries_repo, workspace_id=workspace_id, user_id=user_id, title="B"
    )
    created = await client.post(
        f"/workspaces/{workspace_id}/comparisons",
        json={"document_ids": [str(doc_a.id), str(doc_b.id)]},
    )
    assert created.status_code == 202
    comparison_id = uuid.UUID(created.json()["id"])
    original = _complete_with_clause_report(comparisons_repo, comparison_id)

    resp = await client.patch(
        f"/workspaces/{workspace_id}/comparisons/{comparison_id}/review",
        json={"clause_id": "CLAUSE:8.2", "status": "REVIEWED"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["review"]["CLAUSE:8.2"]["status"] == "REVIEWED"
    assert body["review"]["CLAUSE:8.2"]["reviewer_name"] == "U"
    assert body["result"]["similarities"] == original["similarities"]
    assert body["result"]["differences"] == original["differences"]
    clause = body["result"]["contract_comparison"]["clauses"]["modified"][0]
    assert clause["status"] == "MODIFIED"
    assert clause["risk"]["risk_level"] == "CRITICAL"
    stored = comparisons_repo.rows[comparison_id].comparison
    assert stored.result == original
    assert stored.review["CLAUSE:8.2"]["status"] == "REVIEWED"

    reset = await client.patch(
        f"/workspaces/{workspace_id}/comparisons/{comparison_id}/review",
        json={"clause_id": "CLAUSE:8.2", "status": "OPEN"},
    )
    assert reset.status_code == 200
    assert reset.json()["review"] == {}
    assert comparisons_repo.rows[comparison_id].comparison.result == original


@pytest.mark.asyncio
async def test_patch_review_viewer_forbidden(
    client: AsyncClient,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    docs_repo: FakeDocumentRepo,
    summaries_repo: FakeSummaryRepo,
    comparisons_repo: FakeComparisonRepo,
) -> None:
    _set_role(RoleName.editor)
    doc_a = _seed_document(
        docs_repo, summaries_repo, workspace_id=workspace_id, user_id=user_id, title="A"
    )
    doc_b = _seed_document(
        docs_repo, summaries_repo, workspace_id=workspace_id, user_id=user_id, title="B"
    )
    created = await client.post(
        f"/workspaces/{workspace_id}/comparisons",
        json={"document_ids": [str(doc_a.id), str(doc_b.id)]},
    )
    comparison_id = uuid.UUID(created.json()["id"])
    _complete_with_clause_report(comparisons_repo, comparison_id)
    _set_role(RoleName.viewer)
    resp = await client.patch(
        f"/workspaces/{workspace_id}/comparisons/{comparison_id}/review",
        json={"clause_id": "CLAUSE:8.2", "status": "ACKNOWLEDGED"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_post_comment_does_not_mutate_analysis(
    client: AsyncClient,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    docs_repo: FakeDocumentRepo,
    summaries_repo: FakeSummaryRepo,
    comparisons_repo: FakeComparisonRepo,
) -> None:
    _set_role(RoleName.editor)
    doc_a = _seed_document(
        docs_repo, summaries_repo, workspace_id=workspace_id, user_id=user_id, title="A"
    )
    doc_b = _seed_document(
        docs_repo, summaries_repo, workspace_id=workspace_id, user_id=user_id, title="B"
    )
    created = await client.post(
        f"/workspaces/{workspace_id}/comparisons",
        json={"document_ids": [str(doc_a.id), str(doc_b.id)]},
    )
    comparison_id = uuid.UUID(created.json()["id"])
    original = _complete_with_clause_report(comparisons_repo, comparison_id)

    resp = await client.post(
        f"/workspaces/{workspace_id}/comparisons/{comparison_id}/comments",
        json={
            "clause_id": "CLAUSE:8.2",
            "body": "Please confirm whether the new cap is acceptable.",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert len(body["comments"]) == 1
    assert body["comments"][0]["clause_id"] == "CLAUSE:8.2"
    assert body["comments"][0]["target_type"] == "CLAUSE"
    assert "acceptable" in body["comments"][0]["body"]
    assert body["result"]["similarities"] == original["similarities"]
    assert body["result"]["differences"] == original["differences"]
    clause = body["result"]["contract_comparison"]["clauses"]["modified"][0]
    assert clause["status"] == "MODIFIED"
    assert clause["risk"]["risk_level"] == "CRITICAL"
    stored = comparisons_repo.rows[comparison_id].comparison
    assert stored.result == original
    assert stored.review == {}

    comment_id = body["comments"][0]["id"]
    edited = await client.patch(
        f"/workspaces/{workspace_id}/comparisons/{comparison_id}/comments/{comment_id}",
        json={"body": "Need legal confirmation on the cap."},
    )
    assert edited.status_code == 200
    assert edited.json()["comments"][0]["body"] == "Need legal confirmation on the cap."
    assert comparisons_repo.rows[comparison_id].comparison.result == original

    evidence = await client.post(
        f"/workspaces/{workspace_id}/comparisons/{comparison_id}/comments",
        json={
            "clause_id": "CLAUSE:8.2",
            "body": "Check page 4 excerpt.",
            "target_type": "EVIDENCE",
            "target_id": "ev-1",
        },
    )
    assert evidence.status_code == 201
    assert any(item["target_type"] == "EVIDENCE" for item in evidence.json()["comments"])

    diff = await client.post(
        f"/workspaces/{workspace_id}/comparisons/{comparison_id}/comments",
        json={
            "clause_id": "CLAUSE:8.2",
            "body": "Delta looks material.",
            "target_type": "EXACT_DIFFERENCE",
            "target_id": "0",
        },
    )
    assert diff.status_code == 201

    removed = await client.delete(
        f"/workspaces/{workspace_id}/comparisons/{comparison_id}/comments/{comment_id}",
    )
    assert removed.status_code == 200
    remaining = removed.json()["comments"]
    assert all(item["id"] != comment_id for item in remaining)
    assert comparisons_repo.rows[comparison_id].comparison.result == original


@pytest.mark.asyncio
async def test_post_comment_viewer_forbidden(
    client: AsyncClient,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    docs_repo: FakeDocumentRepo,
    summaries_repo: FakeSummaryRepo,
    comparisons_repo: FakeComparisonRepo,
) -> None:
    _set_role(RoleName.editor)
    doc_a = _seed_document(
        docs_repo, summaries_repo, workspace_id=workspace_id, user_id=user_id, title="A"
    )
    doc_b = _seed_document(
        docs_repo, summaries_repo, workspace_id=workspace_id, user_id=user_id, title="B"
    )
    created = await client.post(
        f"/workspaces/{workspace_id}/comparisons",
        json={"document_ids": [str(doc_a.id), str(doc_b.id)]},
    )
    comparison_id = uuid.UUID(created.json()["id"])
    _complete_with_clause_report(comparisons_repo, comparison_id)
    _set_role(RoleName.viewer)
    resp = await client.post(
        f"/workspaces/{workspace_id}/comparisons/{comparison_id}/comments",
        json={"clause_id": "CLAUSE:8.2", "body": "Viewer note"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_audit_trail_records_review_and_comments_without_mutating_analysis(
    client: AsyncClient,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    docs_repo: FakeDocumentRepo,
    summaries_repo: FakeSummaryRepo,
    comparisons_repo: FakeComparisonRepo,
) -> None:
    _set_role(RoleName.editor)
    doc_a = _seed_document(
        docs_repo, summaries_repo, workspace_id=workspace_id, user_id=user_id, title="A"
    )
    doc_b = _seed_document(
        docs_repo, summaries_repo, workspace_id=workspace_id, user_id=user_id, title="B"
    )
    created = await client.post(
        f"/workspaces/{workspace_id}/comparisons",
        json={"document_ids": [str(doc_a.id), str(doc_b.id)]},
    )
    comparison_id = uuid.UUID(created.json()["id"])
    original = _complete_with_clause_report(comparisons_repo, comparison_id)
    base = f"/workspaces/{workspace_id}/comparisons/{comparison_id}"

    opened = await client.post(
        f"{base}/audit",
        json={"action": "CLAUSE_OPENED", "clause_id": "CLAUSE:8.2"},
    )
    assert opened.status_code == 200
    opened_actions = [item["action"] for item in opened.json()["events"]]
    assert "COMPARISON_CREATED" in opened_actions
    opened_row = next(
        item for item in opened.json()["events"] if item["action"] == "CLAUSE_OPENED"
    )
    first_id = opened_row["id"]

    debounced = await client.post(
        f"{base}/audit",
        json={"action": "CLAUSE_OPENED", "clause_id": "CLAUSE:8.2"},
    )
    assert debounced.status_code == 200
    opened_ids = [
        item["id"]
        for item in debounced.json()["events"]
        if item["action"] == "CLAUSE_OPENED"
    ]
    assert opened_ids == [first_id]

    reviewed = await client.patch(
        f"{base}/review",
        json={"clause_id": "CLAUSE:8.2", "status": "REVIEWED"},
    )
    assert reviewed.status_code == 200
    assert "audit" not in reviewed.json()

    noop = await client.patch(
        f"{base}/review",
        json={"clause_id": "CLAUSE:8.2", "status": "REVIEWED"},
    )
    assert noop.status_code == 200

    commented = await client.post(
        f"{base}/comments",
        json={"clause_id": "CLAUSE:8.2", "body": "Need to confirm the cap."},
    )
    assert commented.status_code == 201
    comment_id = commented.json()["comments"][0]["id"]

    edited = await client.patch(
        f"{base}/comments/{comment_id}",
        json={"body": "Need legal confirmation on the cap."},
    )
    assert edited.status_code == 200

    removed = await client.delete(f"{base}/comments/{comment_id}")
    assert removed.status_code == 200

    trail = await client.get(f"{base}/audit")
    assert trail.status_code == 200
    actions = [item["action"] for item in trail.json()["events"]]
    assert actions[0] == "COMPARISON_CREATED"
    assert "CLAUSE_MAPPING_COMPLETED" not in actions
    assert actions[-5:] == [
        "CLAUSE_OPENED",
        "REVIEW_STATUS_CHANGED",
        "COMMENT_ADDED",
        "COMMENT_EDITED",
        "COMMENT_DELETED",
    ]
    review_event = next(
        item for item in trail.json()["events"] if item["action"] == "REVIEW_STATUS_CHANGED"
    )
    assert review_event["before"]["status"] == "OPEN"
    assert review_event["after"]["status"] == "REVIEWED"
    assert next(
        item["id"] for item in trail.json()["events"] if item["action"] == "CLAUSE_OPENED"
    ) == first_id

    stored = comparisons_repo.rows[comparison_id].comparison
    assert stored.result == original
    assert stored.review["CLAUSE:8.2"]["status"] == "REVIEWED"
    detail = await client.get(base)
    assert "audit" not in detail.json()
    assert detail.json()["result"]["similarities"] == original["similarities"]


@pytest.mark.asyncio
async def test_audit_viewer_can_read_and_record_open_but_not_mutate(
    client: AsyncClient,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    docs_repo: FakeDocumentRepo,
    summaries_repo: FakeSummaryRepo,
    comparisons_repo: FakeComparisonRepo,
) -> None:
    _set_role(RoleName.editor)
    doc_a = _seed_document(
        docs_repo, summaries_repo, workspace_id=workspace_id, user_id=user_id, title="A"
    )
    doc_b = _seed_document(
        docs_repo, summaries_repo, workspace_id=workspace_id, user_id=user_id, title="B"
    )
    created = await client.post(
        f"/workspaces/{workspace_id}/comparisons",
        json={"document_ids": [str(doc_a.id), str(doc_b.id)]},
    )
    comparison_id = uuid.UUID(created.json()["id"])
    _complete_with_clause_report(comparisons_repo, comparison_id)
    base = f"/workspaces/{workspace_id}/comparisons/{comparison_id}"
    _set_role(RoleName.viewer)

    listing = await client.get(f"{base}/audit")
    assert listing.status_code == 200
    assert [item["action"] for item in listing.json()["events"]] == ["COMPARISON_CREATED"]

    opened = await client.post(
        f"{base}/audit",
        json={"action": "CLAUSE_OPENED", "clause_id": "CLAUSE:8.2"},
    )
    assert opened.status_code == 200
    assert [item["action"] for item in opened.json()["events"]][-1] == "CLAUSE_OPENED"

    forbidden_review = await client.patch(
        f"{base}/review",
        json={"clause_id": "CLAUSE:8.2", "status": "REVIEWED"},
    )
    assert forbidden_review.status_code == 403
    forbidden_comment = await client.post(
        f"{base}/comments",
        json={"clause_id": "CLAUSE:8.2", "body": "Viewer note"},
    )
    assert forbidden_comment.status_code == 403
    stored = comparisons_repo.rows[comparison_id].comparison
    assert stored.review == {}
    assert stored.comments == []


@pytest.mark.asyncio
async def test_audit_non_member_cannot_read_other_workspace(
    client: AsyncClient,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    docs_repo: FakeDocumentRepo,
    summaries_repo: FakeSummaryRepo,
    comparisons_repo: FakeComparisonRepo,
) -> None:
    _set_role(RoleName.editor)
    doc_a = _seed_document(
        docs_repo, summaries_repo, workspace_id=workspace_id, user_id=user_id, title="A"
    )
    doc_b = _seed_document(
        docs_repo, summaries_repo, workspace_id=workspace_id, user_id=user_id, title="B"
    )
    created = await client.post(
        f"/workspaces/{workspace_id}/comparisons",
        json={"document_ids": [str(doc_a.id), str(doc_b.id)]},
    )
    comparison_id = uuid.UUID(created.json()["id"])
    other_workspace = uuid.uuid4()
    resp = await client.get(
        f"/workspaces/{other_workspace}/comparisons/{comparison_id}/audit"
    )
    assert resp.status_code == 403
    own = await client.get(
        f"/workspaces/{workspace_id}/comparisons/{comparison_id}/audit"
    )
    assert own.status_code == 200
    assert [item["action"] for item in own.json()["events"]] == ["COMPARISON_CREATED"]
    assert own.json()["events"][0]["metadata"]["document_count"] == 2

