# =============================================================================
# File: test_query_router.py
# Module/Service: Query Router (FR11)
# Layer: Service
# Purpose: Unit tests for cache check + rule-based classification (Part 3).
# Responsibilities:
#   - Metadata / factoid / complex samples; exact + semantic cache; no LLM;
#     retrieval called at most once
# Dependencies:
#   - pytest, AsyncMock, app.services.query_router.*
# Public Exports:
#   - N/A
# Database/Table: N/A (fakes)
# Related Modules: QueryRouter, RuleBasedClassifier, QueryCacheService
# Important Notes: 0 live Qdrant/Postgres/LLM in CI.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config.router_rules import RouterRules, build_router_rules
from app.core.config import Settings
from app.models.enums import RouteType
from app.models.query import QueryCache
from app.services.query_router.cache import (
    QueryCacheService,
    build_normalized_query,
    hash_query,
    normalize_query,
)
from app.services.query_router.classifier import (
    RuleBasedClassifier,
    build_rule_based_classifier,
)
from app.services.query_router.embedding_provider import HashingNgramEmbeddingProvider
from app.services.query_router.router import QueryRouter
from app.services.retrieval.schemas import RetrievalCandidate, RetrievalResult

# ---------------------------------------------------------------------------
# Fixtures / fakes
# ---------------------------------------------------------------------------


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
        "query_router_classifier_confidence_threshold": 0.12,
        "query_router_classifier_margin_threshold": 0.03,
        "query_router_classifier_embedding_dimension": 256,
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

    async def get_exact(
        self,
        *,
        workspace_id: uuid.UUID,
        query_hash: str,
        now: datetime | None = None,
    ) -> QueryCache | None:
        return await self.find_exact_hit(
            workspace_id=workspace_id, query_hash=query_hash, now=now
        )

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

    async def get_similar(
        self,
        *,
        workspace_id: uuid.UUID,
        cache_ids: list[uuid.UUID],
        now: datetime | None = None,
    ) -> list[QueryCache]:
        out: list[QueryCache] = []
        for cid in cache_ids:
            row = await self.get_by_id(workspace_id=workspace_id, cache_id=cid, now=now)
            if row is not None:
                out.append(row)
        return out

    async def record_hit(self, cache: QueryCache, *, now: datetime | None = None) -> QueryCache:
        ts = now or datetime.now(UTC)
        cache.hit_count = int(cache.hit_count or 0) + 1
        cache.last_used_at = ts
        return cache


def _make_cache(
    *,
    workspace_id: uuid.UUID,
    query_text: str,
    query_hash: str | None = None,
    threshold: float = 0.9,
) -> QueryCache:
    nq = build_normalized_query(query_text)
    return QueryCache(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        query_embedding_id=None,
        query_hash=query_hash or nq.query_hash,
        query_text=query_text,
        answer="cached answer",
        citation_refs=None,
        similarity_threshold=threshold,
        hit_count=0,
        ttl_seconds=3600,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        created_at=datetime.now(UTC),
        last_used_at=None,
    )


def _retrieval(workspace_id: uuid.UUID, score: float, text: str = "snippet") -> RetrievalResult:
    return RetrievalResult(
        items=[
            RetrievalCandidate(
                workspace_id=workspace_id,
                document_id=uuid.uuid4(),
                chunk_id=uuid.uuid4(),
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
    has_return = getattr(qdrant.search_similar, "return_value", None) is not None
    has_side = bool(getattr(qdrant.search_similar, "side_effect", None))
    if not has_return and not has_side:
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
        embedding=HashingNgramEmbeddingProvider(dimension=32),
    )
    router = QueryRouter(
        rules=rules,
        cache=cache,
        classifier=build_rule_based_classifier(settings),
        hybrid=hybrid,
    )
    return router, repo, hybrid, qdrant


# ---------------------------------------------------------------------------
# Normalize / hash
# ---------------------------------------------------------------------------


def test_normalize_and_hash_stable() -> None:
    a = normalize_query("  Hello,   WORLD!!! ")
    b = normalize_query("hello world")
    assert a == b == "hello world"
    assert hash_query(a) == hash_query(b)


# ---------------------------------------------------------------------------
# 1. Metadata classification (≥5)
# ---------------------------------------------------------------------------

METADATA_SAMPLES = [
    "Có bao nhiêu tài liệu?",
    "Danh sách PDF",
    "Liệt kê tài liệu",
    "How many documents are there?",
    "Show all files in the workspace",
    "Thống kê số lượng tài liệu theo loại",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("query", METADATA_SAMPLES)
async def test_metadata_classification(query: str) -> None:
    router, _, hybrid, _ = _build_router()
    decision = await router.route(uuid.uuid4(), uuid.uuid4(), query)
    assert decision.route_type == RouteType.metadata
    hybrid.retrieve.assert_not_awaited()


# ---------------------------------------------------------------------------
# 2. Factoid classification (≥5) — high retrieval score
# ---------------------------------------------------------------------------

FACTOID_SAMPLES = [
    "AI là gì?",
    "Tác giả là ai?",
    "Khi nào ban hành?",
    "What is RAG?",
    "Who is the author?",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("query", FACTOID_SAMPLES)
async def test_factoid_classification(query: str) -> None:
    workspace_id = uuid.uuid4()
    hybrid = AsyncMock()
    hybrid.retrieve = AsyncMock(return_value=_retrieval(workspace_id, 0.95))
    router, _, hybrid_out, _ = _build_router(hybrid=hybrid)
    decision = await router.route(workspace_id, uuid.uuid4(), query)
    assert decision.route_type == RouteType.factoid
    # Lightweight retrieval is owned by FactoidHandler — router must not hybrid-retrieve.
    assert decision.retrieval_result is None
    hybrid_out.retrieve.assert_not_awaited()


# ---------------------------------------------------------------------------
# 3. Complex classification (≥5)
# ---------------------------------------------------------------------------

COMPLEX_SAMPLES = [
    "So sánh hai chính sách nghỉ phép năm 2023 và 2024",
    "Phân tích ưu nhược điểm của kiến trúc RAG hiện tại",
    "Tóm tắt toàn bộ tài liệu và đưa ra khuyến nghị",
    "Compare the onboarding processes across departments in detail",
    "Analyze multi-hop relationships between entities and summarize risks",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("query", COMPLEX_SAMPLES)
async def test_complex_classification(query: str) -> None:
    workspace_id = uuid.uuid4()
    hybrid = AsyncMock()
    # Low score so factoid gate fails even if a keyword slips through.
    hybrid.retrieve = AsyncMock(return_value=_retrieval(workspace_id, 0.2))
    router, _, hybrid_out, _ = _build_router(hybrid=hybrid)
    decision = await router.route(workspace_id, uuid.uuid4(), query)
    assert decision.route_type == RouteType.complex
    assert decision.retrieval_result is not None
    hybrid_out.retrieve.assert_awaited_once()


# ---------------------------------------------------------------------------
# 4–6. Cache: miss then hit; semantic; exact skips retrieval/classifier
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exact_cache_hit_increments_and_skips_retrieval() -> None:
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()
    query = "What is the leave policy?"
    router, repo, hybrid, qdrant = _build_router()

    # First call — cache miss → factoid/complex (factoid skips hybrid).
    first = await router.route(workspace_id, user_id, query)
    assert first.route_type != RouteType.cache_hit
    if first.route_type == RouteType.complex:
        assert hybrid.retrieve.await_count == 1
    else:
        hybrid.retrieve.assert_not_awaited()

    # Seed exact cache as if Part 4 wrote it after answering.
    seeded = repo.add(_make_cache(workspace_id=workspace_id, query_text=query))
    assert seeded.hit_count == 0

    hybrid.retrieve.reset_mock()
    qdrant.search_similar.reset_mock()
    second = await router.route(workspace_id, user_id, query)
    assert second.route_type == RouteType.cache_hit
    assert second.cache_entry is not None
    assert second.cache_entry.hit_count == 1
    assert second.cache_entry.last_used_at is not None
    assert second.reason == "exact_cache_hit"
    hybrid.retrieve.assert_not_awaited()
    qdrant.search_similar.assert_not_called()


@pytest.mark.asyncio
async def test_semantic_cache_hit() -> None:
    workspace_id = uuid.uuid4()
    cache_row = _make_cache(
        workspace_id=workspace_id,
        query_text="original cached question",
        threshold=0.85,
    )
    repo = FakeCacheRepo()
    repo.add(cache_row)
    qdrant = MagicMock()
    qdrant.search_similar.return_value = [
        {"score": 0.96, "cache_id": str(cache_row.id), "payload": {"cache_id": str(cache_row.id)}}
    ]
    hybrid = AsyncMock()
    hybrid.retrieve = AsyncMock()
    router, _, hybrid_out, _ = _build_router(repo=repo, qdrant=qdrant, hybrid=hybrid)

    # Different wording → different hash → exact miss → semantic hit.
    decision = await router.route(workspace_id, uuid.uuid4(), "slightly different wording")
    assert decision.route_type == RouteType.cache_hit
    assert decision.reason == "semantic_cache_hit"
    assert decision.similarity == pytest.approx(0.96)
    assert decision.cache_entry is not None
    assert decision.cache_entry.hit_count == 1
    hybrid_out.retrieve.assert_not_awaited()


@pytest.mark.asyncio
async def test_semantic_below_threshold_continues() -> None:
    workspace_id = uuid.uuid4()
    cache_row = _make_cache(workspace_id=workspace_id, query_text="cached", threshold=0.95)
    repo = FakeCacheRepo()
    repo.add(cache_row)
    qdrant = MagicMock()
    qdrant.search_similar.return_value = [
        {"score": 0.50, "cache_id": str(cache_row.id), "payload": {}}
    ]
    hybrid = AsyncMock()
    hybrid.retrieve = AsyncMock(return_value=_retrieval(workspace_id, 0.2))
    router, _, _, _ = _build_router(repo=repo, qdrant=qdrant, hybrid=hybrid)
    decision = await router.route(workspace_id, uuid.uuid4(), "unrelated complex analysis please")
    assert decision.route_type != RouteType.cache_hit


# ---------------------------------------------------------------------------
# 7. No LLM
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_never_calls_llm() -> None:
    workspace_id = uuid.uuid4()
    hybrid = AsyncMock()
    hybrid.retrieve = AsyncMock(return_value=_retrieval(workspace_id, 0.95))
    router, _, _, _ = _build_router(hybrid=hybrid)
    with patch(
        "app.adapters.anthropic_client.extract_structured_json",
        autospec=True,
    ) as llm_spy:
        await router.route(workspace_id, uuid.uuid4(), "AI là gì?")
        await router.route(workspace_id, uuid.uuid4(), "Có bao nhiêu tài liệu?")
        await router.route(
            workspace_id,
            uuid.uuid4(),
            "So sánh chi tiết hai phương án triển khai hệ thống",
        )
        llm_spy.assert_not_called()


# ---------------------------------------------------------------------------
# 8. Retrieval at most once
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_factoid_and_complex_call_retrieval_once() -> None:
    workspace_id = uuid.uuid4()
    hybrid = AsyncMock()
    hybrid.retrieve = AsyncMock(return_value=_retrieval(workspace_id, 0.95))
    router, _, hybrid_out, _ = _build_router(hybrid=hybrid)

    factoid = await router.route(workspace_id, uuid.uuid4(), "What is embedding?")
    assert factoid.route_type == RouteType.factoid
    hybrid_out.retrieve.assert_not_awaited()

    hybrid_out.retrieve.reset_mock()
    hybrid_out.retrieve = AsyncMock(return_value=_retrieval(workspace_id, 0.15))
    # Rebuild with new hybrid mock return
    router2, _, hybrid2, _ = _build_router(hybrid=hybrid_out)
    complex_decision = await router2.route(
        workspace_id,
        uuid.uuid4(),
        "Analyze and compare all policies then summarize recommendations",
    )
    assert complex_decision.route_type == RouteType.complex
    assert hybrid2.retrieve.await_count == 1
    assert complex_decision.retrieval_result is not None


@pytest.mark.asyncio
async def test_exact_cache_does_not_run_classifier_path() -> None:
    workspace_id = uuid.uuid4()
    query = "AI là gì?"
    repo = FakeCacheRepo()
    repo.add(_make_cache(workspace_id=workspace_id, query_text=query))
    router, _, hybrid, qdrant = _build_router(repo=repo)
    with patch.object(
        RuleBasedClassifier, "classify_detailed", autospec=True
    ) as classify_spy:
        decision = await router.route(workspace_id, uuid.uuid4(), query)
        assert decision.route_type == RouteType.cache_hit
        classify_spy.assert_not_called()
        hybrid.retrieve.assert_not_awaited()
        qdrant.search_similar.assert_not_called()
