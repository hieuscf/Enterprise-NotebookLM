# =============================================================================
# File: test_query_execution.py
# Module/Service: Query Router Execution (Part 4)
# Layer: Service
# Purpose: Unit tests for metadata/factoid/cache branches, logging, orchestrator.
# Responsibilities:
#   - Whitelist metadata intents; extractive factoid; cache_hit; complex stub;
#     unified query_logs + message_generations; 0 LLM
# Dependencies:
#   - pytest, AsyncMock, app.services.query_router.*
# Public Exports:
#   - N/A
# Database/Table: N/A (fakes)
# Related Modules: QueryOrchestrator, MetadataBranch, FactoidBranch
# Important Notes: Does not modify QueryRouter; no live LLM/DB.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config.router_rules import RouterRules, build_router_rules
from app.core.config import Settings
from app.models.enums import FileType, RouteType
from app.models.query import QueryCache
from app.repositories.retrieval import ChunkHydrationRow, MetadataDocumentRow
from app.services.query_router.cache import QueryCacheService, build_normalized_query
from app.services.query_router.classifier import build_rule_based_classifier
from app.services.query_router.factoid_branch import FactoidBranch
from app.services.query_router.metadata_branch import (
    MetadataBranch,
    MetadataIntent,
    map_metadata_intent,
)
from app.services.query_router.orchestrator import COMPLEX_STATUS, QueryOrchestrator
from app.services.query_router.router import QueryRouter
from app.services.query_router.schemas import CitationRef, RouteDecision
from app.services.retrieval.schemas import RetrievalCandidate, RetrievalResult

# Reuse Part 3 sample sets for logging coverage.
METADATA_SAMPLES = [
    "Có bao nhiêu tài liệu?",
    "Danh sách PDF",
    "Liệt kê tài liệu",
    "How many documents are there?",
    "Show all files in the workspace",
    "Thống kê số lượng tài liệu theo loại",
]
FACTOID_SAMPLES = [
    "AI là gì?",
    "Tác giả là ai?",
    "Khi nào ban hành?",
    "What is RAG?",
    "Who is the author?",
]
COMPLEX_SAMPLES = [
    "So sánh hai chính sách nghỉ phép năm 2023 và 2024",
    "Phân tích ưu nhược điểm của kiến trúc RAG hiện tại",
    "Tóm tắt toàn bộ tài liệu và đưa ra khuyến nghị",
    "Compare the onboarding processes across departments in detail",
    "Analyze multi-hop relationships between entities and summarize risks",
]
ALL_PART3_SAMPLES = METADATA_SAMPLES + FACTOID_SAMPLES + COMPLEX_SAMPLES


def _settings(**overrides: Any) -> Settings:
    base = {
        "embedding_model_name": "local-hash-embedding-v1",
        "embedding_dimension": 8,
        "embedding_provider": "local",
        "query_cache_similarity_threshold": 0.90,
        "query_router_factoid_confidence_threshold": 0.75,
        "query_router_minimum_factoid_score": 0.70,
        "query_router_maximum_factoid_length": 80,
        "query_router_factoid_top_k": 1,
        "reranker_backend": "heuristic",
    }
    base.update(overrides)
    return Settings(**base)


def _rules(settings: Settings | None = None) -> RouterRules:
    return build_router_rules(settings or _settings())


class FakeCacheRepo:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, QueryCache] = {}
        self.by_hash: dict[tuple[uuid.UUID, str], QueryCache] = {}

    def add(self, row: QueryCache) -> QueryCache:
        self.rows[row.id] = row
        self.by_hash[(row.workspace_id, row.query_hash)] = row
        return row

    async def find_exact_hit(
        self,
        *,
        workspace_id: uuid.UUID,
        query_hash: str,
        now: datetime | None = None,
    ) -> QueryCache | None:
        row = self.by_hash.get((workspace_id, query_hash))
        if row is None:
            return None
        ts = now or datetime.now(UTC)
        if row.expires_at <= ts:
            return None
        return row

    async def get_by_id(
        self,
        *,
        workspace_id: uuid.UUID,
        cache_id: uuid.UUID,
        now: datetime | None = None,
    ) -> QueryCache | None:
        row = self.rows.get(cache_id)
        if row is None or row.workspace_id != workspace_id:
            return None
        ts = now or datetime.now(UTC)
        if row.expires_at <= ts:
            return None
        return row

    async def record_hit(self, cache: QueryCache, *, now: datetime | None = None) -> QueryCache:
        ts = now or datetime.now(UTC)
        cache.hit_count = int(cache.hit_count or 0) + 1
        cache.last_used_at = ts
        return cache


class FakeObservability:
    def __init__(self) -> None:
        self.query_logs: list[dict[str, Any]] = []
        self.generations: list[dict[str, Any]] = []

    async def create_query_log(self, **kwargs: Any) -> SimpleNamespace:
        row_id = uuid.uuid4()
        self.query_logs.append({"id": row_id, **kwargs})
        return SimpleNamespace(id=row_id)

    async def create_message_generation(self, **kwargs: Any) -> SimpleNamespace:
        row_id = uuid.uuid4()
        self.generations.append({"id": row_id, **kwargs})
        return SimpleNamespace(id=row_id)


class FakeRetrievalRepo:
    """Seed-like metadata counters for unit tests."""

    def __init__(self) -> None:
        self.hydrate_calls = 0
        self.workspace_id = uuid.uuid4()
        self._docs = [
            MetadataDocumentRow(
                document_id=uuid.uuid4(),
                workspace_id=self.workspace_id,
                title="Policy.pdf",
                file_type=FileType.pdf,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                uploaded_by=uuid.uuid4(),
                version_number=1,
                status="ready",
            ),
            MetadataDocumentRow(
                document_id=uuid.uuid4(),
                workspace_id=self.workspace_id,
                title="Guide.docx",
                file_type=FileType.docx,
                created_at=datetime.now(UTC) - timedelta(days=1),
                updated_at=datetime.now(UTC),
                uploaded_by=uuid.uuid4(),
                version_number=1,
                status="ready",
            ),
        ]

    async def count_documents(
        self,
        workspace_id: uuid.UUID,
        *,
        file_type: FileType | None = None,
    ) -> int:
        del workspace_id
        if file_type is None:
            return 25
        return sum(1 for d in self._docs if d.file_type == file_type)

    async def list_documents_metadata(
        self,
        workspace_id: uuid.UUID,
        *,
        file_type: FileType | None = None,
        uploaded_after: datetime | None = None,
        uploaded_before: datetime | None = None,
        title_contains: str | None = None,
        limit: int = 50,
    ) -> list[MetadataDocumentRow]:
        del uploaded_after, uploaded_before, title_contains
        rows = [d for d in self._docs if d.workspace_id == workspace_id or True]
        if file_type is not None:
            rows = [d for d in rows if d.file_type == file_type]
        return rows[:limit]

    async def count_by_file_type(self, workspace_id: uuid.UUID) -> dict[str, int]:
        del workspace_id
        return {"pdf": 3, "docx": 2, "txt": 1}

    async def hydrate_chunks(
        self,
        workspace_id: uuid.UUID,
        chunk_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, ChunkHydrationRow]:
        self.hydrate_calls += 1
        out: dict[uuid.UUID, ChunkHydrationRow] = {}
        for cid in chunk_ids:
            out[cid] = ChunkHydrationRow(
                chunk_id=cid,
                document_id=uuid.uuid4(),
                document_version_id=uuid.uuid4(),
                workspace_id=workspace_id,
                content="ignored",
                title="Doc",
                page_number=7,
            )
        return out


class FakeMemberRepo:
    async def count_active_members(self, workspace_id: uuid.UUID) -> int:
        del workspace_id
        return 4


def _make_cache(
    *,
    workspace_id: uuid.UUID,
    query_text: str,
    answer: str = "cached answer",
    citation_refs: Any = None,
) -> QueryCache:
    nq = build_normalized_query(query_text)
    return QueryCache(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        query_embedding_id=None,
        query_hash=nq.query_hash,
        query_text=query_text,
        answer=answer,
        citation_refs=citation_refs,
        similarity_threshold=0.9,
        hit_count=0,
        ttl_seconds=3600,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        created_at=datetime.now(UTC),
        last_used_at=None,
    )


def _retrieval(
    workspace_id: uuid.UUID,
    score: float,
    text: str = "exact snippet text",
    *,
    chunk_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
) -> RetrievalResult:
    return RetrievalResult(
        items=[
            RetrievalCandidate(
                workspace_id=workspace_id,
                document_id=document_id or uuid.uuid4(),
                chunk_id=chunk_id or uuid.uuid4(),
                text_snippet=text,
                retrieval_method="rerank",
                raw_score=score,
                score=score,
                rank=1,
                source_methods=["vector"],
            )
        ],
        latency_ms=5,
        sources_used=["vector"],
        timings={},
    )


def _build_router(
    *,
    settings: Settings | None = None,
    repo: FakeCacheRepo | None = None,
    qdrant: MagicMock | None = None,
    hybrid: AsyncMock | None = None,
) -> tuple[QueryRouter, FakeCacheRepo, AsyncMock, MagicMock]:
    settings = settings or _settings()
    rules = _rules(settings)
    repo = repo or FakeCacheRepo()
    qdrant = qdrant or MagicMock()
    if getattr(qdrant.search_similar, "return_value", None) is None and not getattr(
        qdrant.search_similar, "side_effect", None
    ):
        qdrant.search_similar.return_value = []
    if hybrid is None:
        hybrid = AsyncMock()
        hybrid.retrieve = AsyncMock(
            return_value=RetrievalResult(items=[], latency_ms=1, sources_used=[], timings={})
        )
    cache = QueryCacheService(
        settings=settings,
        rules=rules,
        repo=repo,  # type: ignore[arg-type]
        qdrant=qdrant,
    )
    router = QueryRouter(
        rules=rules,
        cache=cache,
        classifier=build_rule_based_classifier(settings),
        hybrid=hybrid,
    )
    return router, repo, hybrid, qdrant


def _build_orchestrator(
    *,
    router: QueryRouter | None = None,
    retrieval_repo: FakeRetrievalRepo | None = None,
    member_repo: FakeMemberRepo | None = None,
    observability: FakeObservability | None = None,
    hybrid: AsyncMock | None = None,
    cache_repo: FakeCacheRepo | None = None,
) -> tuple[QueryOrchestrator, FakeObservability, AsyncMock, FakeRetrievalRepo]:
    retrieval_repo = retrieval_repo or FakeRetrievalRepo()
    member_repo = member_repo or FakeMemberRepo()
    observability = observability or FakeObservability()
    if router is None:
        router, _, hybrid_out, _ = _build_router(repo=cache_repo, hybrid=hybrid)
    else:
        hybrid_out = hybrid or AsyncMock()
    orch = QueryOrchestrator(
        router=router,
        metadata_branch=MetadataBranch(
            retrieval_repo=retrieval_repo,  # type: ignore[arg-type]
            member_repo=member_repo,  # type: ignore[arg-type]
        ),
        factoid_branch=FactoidBranch(retrieval_repo=retrieval_repo),  # type: ignore[arg-type]
        observability=observability,  # type: ignore[arg-type]
    )
    return orch, observability, hybrid_out, retrieval_repo


# ---------------------------------------------------------------------------
# Metadata intent mapping
# ---------------------------------------------------------------------------


def test_map_count_documents() -> None:
    intent, ft = map_metadata_intent("Có bao nhiêu tài liệu?")
    assert intent == MetadataIntent.COUNT_DOCUMENTS
    assert ft is None


def test_map_list_pdf() -> None:
    intent, ft = map_metadata_intent("Danh sách PDF")
    assert intent == MetadataIntent.LIST_BY_FILE_TYPE
    assert ft == FileType.pdf


def test_map_stats_file_type() -> None:
    intent, ft = map_metadata_intent("Thống kê số lượng tài liệu theo loại")
    assert intent == MetadataIntent.STATS_FILE_TYPE
    assert ft is None


def test_map_count_members() -> None:
    intent, ft = map_metadata_intent("Đếm số thành viên workspace")
    assert intent == MetadataIntent.COUNT_MEMBERS
    assert ft is None


def test_map_tags_unsupported() -> None:
    intent, ft = map_metadata_intent("Thống kê tag trong workspace")
    assert intent is None
    assert ft is None


# ---------------------------------------------------------------------------
# Metadata Branch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_metadata_count_documents() -> None:
    branch = MetadataBranch(
        retrieval_repo=FakeRetrievalRepo(),  # type: ignore[arg-type]
        member_repo=FakeMemberRepo(),  # type: ignore[arg-type]
    )
    decision = RouteDecision(
        route_type=RouteType.metadata,
        reason="test",
        latency_ms=1,
        query_hash="x",
    )
    result = await branch.execute(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        query_text="Có bao nhiêu tài liệu?",
        decision=decision,
    )
    assert result.route_type == RouteType.metadata
    assert result.verify is True
    assert result.citation_refs == []
    assert result.metadata["count"] == 25
    assert "25" in (result.answer or "")


@pytest.mark.asyncio
async def test_metadata_list_documents() -> None:
    repo = FakeRetrievalRepo()
    branch = MetadataBranch(
        retrieval_repo=repo,  # type: ignore[arg-type]
        member_repo=FakeMemberRepo(),  # type: ignore[arg-type]
    )
    result = await branch.execute(
        workspace_id=repo.workspace_id,
        user_id=uuid.uuid4(),
        query_text="Liệt kê tài liệu",
        decision=RouteDecision(
            route_type=RouteType.metadata, reason="t", latency_ms=1, query_hash="h"
        ),
    )
    assert result.route_type == RouteType.metadata
    assert result.metadata["count"] == 2
    assert result.verify is True


@pytest.mark.asyncio
async def test_metadata_count_members() -> None:
    branch = MetadataBranch(
        retrieval_repo=FakeRetrievalRepo(),  # type: ignore[arg-type]
        member_repo=FakeMemberRepo(),  # type: ignore[arg-type]
    )
    result = await branch.execute(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        query_text="How many members are in the workspace?",
        decision=RouteDecision(
            route_type=RouteType.metadata, reason="t", latency_ms=1, query_hash="h"
        ),
    )
    assert result.route_type == RouteType.metadata
    assert result.metadata["count"] == 4
    assert "4" in (result.answer or "")


@pytest.mark.asyncio
async def test_metadata_stats_file_type() -> None:
    branch = MetadataBranch(
        retrieval_repo=FakeRetrievalRepo(),  # type: ignore[arg-type]
        member_repo=FakeMemberRepo(),  # type: ignore[arg-type]
    )
    result = await branch.execute(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        query_text="Thống kê số lượng tài liệu theo loại",
        decision=RouteDecision(
            route_type=RouteType.metadata, reason="t", latency_ms=1, query_hash="h"
        ),
    )
    assert result.route_type == RouteType.metadata
    assert result.metadata["by_file_type"]["pdf"] == 3
    assert result.verify is True


@pytest.mark.asyncio
async def test_metadata_unknown_falls_back_complex() -> None:
    branch = MetadataBranch(
        retrieval_repo=FakeRetrievalRepo(),  # type: ignore[arg-type]
        member_repo=FakeMemberRepo(),  # type: ignore[arg-type]
    )
    result = await branch.execute(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        query_text="Thống kê tag trong workspace",
        decision=RouteDecision(
            route_type=RouteType.metadata, reason="t", latency_ms=1, query_hash="h"
        ),
    )
    assert result.route_type == RouteType.complex
    assert result.status == COMPLEX_STATUS
    assert result.verify is False


# ---------------------------------------------------------------------------
# Factoid Branch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_factoid_extractive_answer_and_citation() -> None:
    workspace_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    document_id = uuid.uuid4()
    snippet = "RAG combines retrieval with generation."
    repo = FakeRetrievalRepo()
    hybrid = AsyncMock()
    hybrid.retrieve = AsyncMock()

    branch = FactoidBranch(retrieval_repo=repo)  # type: ignore[arg-type]
    decision = RouteDecision(
        route_type=RouteType.factoid,
        reason="test",
        latency_ms=1,
        query_hash="h",
        retrieval_result=_retrieval(
            workspace_id, 0.95, snippet, chunk_id=chunk_id, document_id=document_id
        ),
        factoid_score=0.95,
    )
    result = await branch.execute(workspace_id=workspace_id, decision=decision)

    assert result.route_type == RouteType.factoid
    assert result.answer == snippet
    assert result.verify is True
    assert result.metadata == {}
    assert len(result.citation_refs) == 1
    cite = result.citation_refs[0]
    assert cite.chunk_id == chunk_id
    assert cite.document_id == document_id
    assert cite.page_number == 7
    assert cite.verify is True
    hybrid.retrieve.assert_not_awaited()
    assert repo.hydrate_calls == 1


@pytest.mark.asyncio
async def test_factoid_does_not_call_hybrid_again() -> None:
    workspace_id = uuid.uuid4()
    hybrid = AsyncMock()
    hybrid.retrieve = AsyncMock(return_value=_retrieval(workspace_id, 0.99))
    orch, _, hybrid_out, _ = _build_orchestrator(hybrid=hybrid)
    with patch(
        "app.adapters.anthropic_client.extract_structured_json",
        MagicMock(side_effect=AssertionError("LLM must not be called")),
    ):
        result = await orch.handle_query(
            workspace_id,
            uuid.uuid4(),
            "What is RAG?",
            message_id=uuid.uuid4(),
        )
    assert result.route_type == RouteType.factoid
    assert result.answer == "exact snippet text"
    assert hybrid_out.retrieve.await_count == 1


# ---------------------------------------------------------------------------
# Cache Hit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_hit_returns_cached_answer_without_branches() -> None:
    workspace_id = uuid.uuid4()
    query = "What is the leave policy?"
    chunk_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    cache_repo = FakeCacheRepo()
    cache_repo.add(
        _make_cache(
            workspace_id=workspace_id,
            query_text=query,
            answer="Leave is 12 days per year.",
            citation_refs=[
                {
                    "chunk_id": str(chunk_id),
                    "document_id": str(doc_id),
                    "page_number": 3,
                    "verify": True,
                }
            ],
        )
    )
    hybrid = AsyncMock()
    hybrid.retrieve = AsyncMock(side_effect=AssertionError("no retrieval on cache_hit"))
    meta = AsyncMock()
    fact = AsyncMock()

    router, _, hybrid_out, _ = _build_router(repo=cache_repo, hybrid=hybrid)
    obs = FakeObservability()
    orch = QueryOrchestrator(
        router=router,
        metadata_branch=meta,
        factoid_branch=fact,
        observability=obs,  # type: ignore[arg-type]
    )
    with patch(
        "app.adapters.anthropic_client.extract_structured_json",
        MagicMock(side_effect=AssertionError("LLM must not be called")),
    ):
        result = await orch.handle_query(
            workspace_id,
            uuid.uuid4(),
            query,
            message_id=uuid.uuid4(),
        )

    assert result.route_type == RouteType.cache_hit
    assert result.answer == "Leave is 12 days per year."
    assert result.verify is True
    assert result.citation_refs[0].chunk_id == chunk_id
    assert result.cache_id is not None
    hybrid_out.retrieve.assert_not_awaited()
    meta.execute.assert_not_awaited()
    fact.execute.assert_not_awaited()
    assert len(obs.query_logs) == 1
    assert len(obs.generations) == 1


# ---------------------------------------------------------------------------
# Complex placeholder
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complex_placeholder_logs_no_llm() -> None:
    workspace_id = uuid.uuid4()
    hybrid = AsyncMock()
    hybrid.retrieve = AsyncMock(return_value=_retrieval(workspace_id, 0.2))
    orch, obs, _, _ = _build_orchestrator(hybrid=hybrid)
    with patch(
        "app.adapters.anthropic_client.extract_structured_json",
        MagicMock(side_effect=AssertionError("LLM must not be called")),
    ) as llm_spy:
        result = await orch.handle_query(
            workspace_id,
            uuid.uuid4(),
            COMPLEX_SAMPLES[0],
            message_id=uuid.uuid4(),
        )
        llm_spy.assert_not_called()

    assert result.route_type == RouteType.complex
    assert result.status == COMPLEX_STATUS
    assert result.answer is None
    assert result.metadata.get("status") == COMPLEX_STATUS
    assert len(obs.query_logs) == 1
    assert len(obs.generations) == 1
    assert obs.query_logs[0]["llm_calls_count"] == 0
    assert obs.query_logs[0]["model_used"] is None
    assert obs.generations[0]["prompt_tokens"] == 0
    assert obs.generations[0]["cost_usd"] == Decimal("0")


# ---------------------------------------------------------------------------
# Logging for all Part 3 samples + cache_hit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ALL_PART3_SAMPLES)
async def test_handle_query_logs_one_row_each(query: str) -> None:
    workspace_id = uuid.uuid4()
    # High score so factoid samples succeed; low score for complex samples.
    is_complexish = query in COMPLEX_SAMPLES
    score = 0.2 if is_complexish else 0.95
    hybrid = AsyncMock()
    hybrid.retrieve = AsyncMock(return_value=_retrieval(workspace_id, score))
    orch, obs, _, _ = _build_orchestrator(hybrid=hybrid)
    message_id = uuid.uuid4()

    with patch(
        "app.adapters.anthropic_client.extract_structured_json",
        MagicMock(side_effect=AssertionError("LLM must not be called")),
    ):
        result = await orch.handle_query(
            workspace_id,
            uuid.uuid4(),
            query,
            message_id=message_id,
        )

    assert len(obs.query_logs) == 1
    assert len(obs.generations) == 1
    assert obs.query_logs[0]["route_type"] == result.route_type
    assert obs.query_logs[0]["llm_calls_count"] == 0
    assert obs.generations[0]["message_id"] == message_id
    assert obs.generations[0]["route_type"] == result.route_type
    assert result.query_log_id == obs.query_logs[0]["id"]
    assert result.message_generation_id == obs.generations[0]["id"]


@pytest.mark.asyncio
async def test_cache_hit_logging_included() -> None:
    workspace_id = uuid.uuid4()
    query = "Cached factoid question?"
    cache_repo = FakeCacheRepo()
    cache_repo.add(_make_cache(workspace_id=workspace_id, query_text=query))
    orch, obs, hybrid, _ = _build_orchestrator(cache_repo=cache_repo)
    result = await orch.handle_query(
        workspace_id, uuid.uuid4(), query, message_id=uuid.uuid4()
    )
    assert result.route_type == RouteType.cache_hit
    assert len(obs.query_logs) == 1
    assert len(obs.generations) == 1
    assert obs.query_logs[0]["cache_id"] == result.cache_id
    hybrid.retrieve.assert_not_awaited()


# ---------------------------------------------------------------------------
# No LLM across orchestrator paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_llm_on_metadata_factoid_cache_complex() -> None:
    workspace_id = uuid.uuid4()
    cases = [
        ("Có bao nhiêu tài liệu?", RouteType.metadata, 0.95),
        ("What is RAG?", RouteType.factoid, 0.95),
        (
            "Analyze multi-hop relationships between entities and summarize risks",
            RouteType.complex,
            0.1,
        ),
    ]
    with patch(
        "app.adapters.anthropic_client.extract_structured_json",
        MagicMock(side_effect=AssertionError("LLM must not be called")),
    ) as llm_spy:
        for query, expected, score in cases:
            hybrid = AsyncMock()
            hybrid.retrieve = AsyncMock(return_value=_retrieval(workspace_id, score))
            orch, _, _, _ = _build_orchestrator(hybrid=hybrid)
            result = await orch.handle_query(
                workspace_id, uuid.uuid4(), query, message_id=uuid.uuid4()
            )
            assert result.route_type == expected
        # cache hit
        cache_repo = FakeCacheRepo()
        q = "unique cached query xyz"
        cache_repo.add(_make_cache(workspace_id=workspace_id, query_text=q))
        orch, _, _, _ = _build_orchestrator(cache_repo=cache_repo)
        result = await orch.handle_query(
            workspace_id, uuid.uuid4(), q, message_id=uuid.uuid4()
        )
        assert result.route_type == RouteType.cache_hit
        llm_spy.assert_not_called()


@pytest.mark.asyncio
async def test_citation_ref_dataclass() -> None:
    ref = CitationRef(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        page_number=2,
        verify=True,
    )
    assert ref.verify is True
