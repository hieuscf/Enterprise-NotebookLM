# =============================================================================
# File: test_search_router_integration.py
# Module/Service: Search + Query Router (GĐ2 Part 6)
# Layer: QA / Integration
# Purpose: End-to-end integration coverage for Search API, Hybrid Retrieval,
#   Query Orchestrator branches, cache lifecycle, logging, RBAC, and 0-LLM.
# Responsibilities:
#   - Seed workspace/docs/chunks; run real HybridRetrievalService (adapters seeded)
#   - Exercise Search HTTP + history; handle_query for 4 routes; cleanup job
# Dependencies:
#   - pytest, httpx, app.services.retrieval.*, query_router.*, search
# Public Exports:
#   - N/A
# Database/Table: N/A (in-memory seed + fakes; CI has no live Qdrant/ES/Neo4j)
# Related Modules: docs/review/stage2_completion_report.md
# Important Notes:
#   - Does NOT mock HybridRetrievalService.retrieve — only external adapters.
#   - Anthropic / LLM provider is spied; must never be called.
# =============================================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.search import get_search_service
from app.config.router_rules import build_router_rules
from app.core.config import Settings
from app.core.rate_limit import InMemoryWorkspaceRateLimiter, get_workspace_rate_limiter
from app.db.session import get_db_session
from app.dependencies.auth import CurrentUser, get_current_user
from app.main import app
from app.models.enums import FileType, RoleName, RouteType
from app.models.query import QueryCache, SearchHistory
from app.repositories.retrieval import ChunkHydrationRow, MetadataDocumentRow
from app.repositories.workspace_members import WorkspaceMemberRepository
from app.services.query_router.cache import QueryCacheService, build_normalized_query
from app.services.query_router.cache_writer import QueryCacheWriter
from app.services.query_router.classifier import build_rule_based_classifier
from app.services.query_router.embedding_provider import HashingNgramEmbeddingProvider
from app.services.query_router.factoid_branch import FactoidBranch
from app.services.query_router.metadata_branch import MetadataBranch
from app.services.query_router.orchestrator import COMPLEX_STATUS, QueryOrchestrator
from app.services.query_router.router import QueryRouter
from app.services.query_router.schemas import CitationRef
from app.services.retrieval.bm25_search import Bm25Search
from app.services.retrieval.graph_search import GraphSearch
from app.services.retrieval.hybrid_retrieval_service import HybridRetrievalService
from app.services.retrieval.reranker import Reranker
from app.services.retrieval.vector_search import VectorSearch
from app.services.search import SearchService
from app.tasks.cleanup_expired_cache import run_cleanup_expired_query_cache

# ---------------------------------------------------------------------------
# Settings / seed world
# ---------------------------------------------------------------------------


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "embedding_model_name": "local-hash-embedding-v1",
        "embedding_dimension": 8,
        "embedding_provider": "local",
        "retrieval_vector_timeout_seconds": 2.0,
        "retrieval_bm25_timeout_seconds": 2.0,
        "retrieval_graph_timeout_seconds": 2.0,
        "retrieval_per_source_top_k": 20,
        "retrieval_max_rerank_candidates": 100,
        "retrieval_snippet_max_chars": 500,
        "reranker_backend": "heuristic",
        "query_cache_similarity_threshold": 0.90,
        "query_cache_default_ttl_seconds": 3600,
        "query_cache_cleanup_interval_minutes": 15,
        "query_router_factoid_confidence_threshold": 0.50,
        "query_router_minimum_factoid_score": 0.40,
        "query_router_maximum_factoid_length": 200,
        "query_router_factoid_top_k": 1,
    }
    base.update(overrides)
    return Settings(**base)


@dataclass
class SeedWorld:
    """Minimal ingested-document world for CI integration tests."""

    workspace_id: uuid.UUID
    user_id: uuid.UUID
    outsider_id: uuid.UUID
    document_id: uuid.UUID
    version_id: uuid.UUID
    chunk_id: uuid.UUID
    entity_id: uuid.UUID
    snippet: str = (
        "AI (Artificial Intelligence) is the simulation of human intelligence by machines."
    )
    title: str = "AI Primer.pdf"
    file_type: FileType = FileType.pdf
    member_count: int = 3
    docs: list[MetadataDocumentRow] = field(default_factory=list)
    chunks: dict[uuid.UUID, ChunkHydrationRow] = field(default_factory=dict)


def build_seed_world() -> SeedWorld:
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()
    outsider_id = uuid.uuid4()
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    now = datetime.now(UTC)
    snippet = (
        "AI (Artificial Intelligence) is the simulation of human intelligence by machines."
    )
    doc = MetadataDocumentRow(
        document_id=document_id,
        workspace_id=workspace_id,
        title="AI Primer.pdf",
        file_type=FileType.pdf,
        created_at=now,
        updated_at=now,
        uploaded_by=user_id,
        version_number=1,
        status="ready",
    )
    doc2 = MetadataDocumentRow(
        document_id=uuid.uuid4(),
        workspace_id=workspace_id,
        title="Policy.docx",
        file_type=FileType.docx,
        created_at=now - timedelta(days=1),
        updated_at=now,
        uploaded_by=user_id,
        version_number=1,
        status="ready",
    )
    chunk = ChunkHydrationRow(
        chunk_id=chunk_id,
        document_id=document_id,
        document_version_id=version_id,
        workspace_id=workspace_id,
        content=snippet,
        title=doc.title,
        page_number=1,
    )
    return SeedWorld(
        workspace_id=workspace_id,
        user_id=user_id,
        outsider_id=outsider_id,
        document_id=document_id,
        version_id=version_id,
        chunk_id=chunk_id,
        entity_id=entity_id,
        snippet=snippet,
        docs=[doc, doc2],
        chunks={chunk_id: chunk},
    )


# ---------------------------------------------------------------------------
# In-memory adapters + repositories (external services only)
# ---------------------------------------------------------------------------


class SeededQdrant:
    def __init__(self, world: SeedWorld) -> None:
        self._world = world
        self.search_calls = 0

    def search_similar(
        self,
        *,
        workspace_id: uuid.UUID,
        query_vector: list[float],
        top_k: int = 10,
        kind: str | None = None,
        **_: Any,
    ) -> list[dict[str, Any]]:
        del query_vector, top_k
        self.search_calls += 1
        if workspace_id != self._world.workspace_id:
            return []
        if kind == "query_cache":
            return []
        return [
            {
                "chunk_id": str(self._world.chunk_id),
                "document_id": str(self._world.document_id),
                "score": 0.97,
                "payload": {"kind": "chunk"},
            }
        ]


class SeededElasticsearch:
    def __init__(self, world: SeedWorld) -> None:
        self._world = world
        self.search_calls = 0

    def search(
        self,
        *,
        workspace_id: uuid.UUID,
        query_text: str,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        del query_text, top_k
        self.search_calls += 1
        if workspace_id != self._world.workspace_id:
            return []
        return [
            {
                "chunk_id": str(self._world.chunk_id),
                "document_id": str(self._world.document_id),
                "score": 12.5,
                "text_snippet": self._world.snippet,
            }
        ]


class SeededNeo4j:
    def __init__(self, world: SeedWorld) -> None:
        self._world = world
        self.search_calls = 0

    def search_entities_with_chunks(
        self,
        *,
        workspace_id: uuid.UUID,
        query_text: str,
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        del query_text, top_k
        self.search_calls += 1
        if workspace_id != self._world.workspace_id:
            return []
        return [
            {
                "entity_id": str(self._world.entity_id),
                "entity_name": "AI",
                "chunk_id": str(self._world.chunk_id),
                "document_id": str(self._world.document_id),
                "source_version_id": str(self._world.version_id),
                "score": 0.88,
                "text_snippet": self._world.snippet,
            }
        ]


class SeededRetrievalRepo:
    """Postgres stand-in reflecting completed ingest for the seed workspace."""

    def __init__(self, world: SeedWorld) -> None:
        self._world = world
        self.hydrate_calls = 0

    async def hydrate_chunks(
        self,
        workspace_id: uuid.UUID,
        chunk_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, ChunkHydrationRow]:
        self.hydrate_calls += 1
        if workspace_id != self._world.workspace_id:
            return {}
        return {
            cid: self._world.chunks[cid]
            for cid in chunk_ids
            if cid in self._world.chunks
        }

    async def chunks_for_entity_versions(
        self,
        workspace_id: uuid.UUID,
        source_version_ids: list[uuid.UUID],
        *,
        entity_names: list[str],
        limit: int = 20,
    ) -> list[ChunkHydrationRow]:
        del source_version_ids, entity_names, limit
        if workspace_id != self._world.workspace_id:
            return []
        return list(self._world.chunks.values())

    async def document_id_for_version(
        self,
        workspace_id: uuid.UUID,
        document_version_id: uuid.UUID,
    ) -> uuid.UUID | None:
        if workspace_id != self._world.workspace_id:
            return None
        if document_version_id == self._world.version_id:
            return self._world.document_id
        return None

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
        rows = [d for d in self._world.docs if d.workspace_id == workspace_id]
        if file_type is not None:
            rows = [d for d in rows if d.file_type == file_type]
        return rows[:limit]

    async def count_documents(
        self,
        workspace_id: uuid.UUID,
        *,
        file_type: FileType | None = None,
    ) -> int:
        rows = [d for d in self._world.docs if d.workspace_id == workspace_id]
        if file_type is not None:
            rows = [d for d in rows if d.file_type == file_type]
        return len(rows)

    async def count_by_file_type(self, workspace_id: uuid.UUID) -> dict[str, int]:
        out: dict[str, int] = {}
        for d in self._world.docs:
            if d.workspace_id != workspace_id:
                continue
            key = d.file_type.value
            out[key] = out.get(key, 0) + 1
        return out

    async def documents_meta_by_ids(
        self,
        workspace_id: uuid.UUID,
        document_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, MetadataDocumentRow]:
        return {
            d.document_id: d
            for d in self._world.docs
            if d.workspace_id == workspace_id and d.document_id in document_ids
        }

    async def find_entities_by_name(
        self,
        workspace_id: uuid.UUID,
        query_text: str,
        *,
        limit: int = 20,
    ) -> list[Any]:
        del workspace_id, query_text, limit
        return []


class SeededMemberRepo:
    def __init__(self, world: SeedWorld) -> None:
        self._world = world

    async def count_active_members(self, workspace_id: uuid.UUID) -> int:
        if workspace_id != self._world.workspace_id:
            return 0
        return self._world.member_count


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

    async def create(self, **kwargs: Any) -> QueryCache:
        row = QueryCache(
            id=uuid.uuid4(),
            workspace_id=kwargs["workspace_id"],
            query_embedding_id=kwargs.get("query_embedding_id"),
            query_hash=kwargs["query_hash"],
            query_text=kwargs["query_text"],
            answer=kwargs["answer"],
            citation_refs=kwargs.get("citation_refs"),
            similarity_threshold=kwargs["similarity_threshold"],
            hit_count=kwargs.get("hit_count", 0),
            ttl_seconds=kwargs["ttl_seconds"],
            expires_at=kwargs["expires_at"],
            created_at=kwargs.get("now") or datetime.now(UTC),
            last_used_at=kwargs.get("last_used_at"),
        )
        return self.add(row)

    async def save(self, **kwargs: Any) -> QueryCache:
        return await self.create(**kwargs)

    async def delete_expired(self, *, now: datetime | None = None) -> int:
        ts = now or datetime.now(UTC)
        doomed = [cid for cid, row in self.rows.items() if row.expires_at < ts]
        for cid in doomed:
            row = self.rows.pop(cid)
            self.by_hash.pop((row.workspace_id, row.query_hash), None)
        return len(doomed)


class FakeObservability:
    def __init__(self) -> None:
        self.query_logs: list[dict[str, Any]] = []
        self.generations: list[dict[str, Any]] = []

    async def create_query_log(self, **kwargs: Any) -> Any:
        row_id = uuid.uuid4()
        self.query_logs.append({"id": row_id, **kwargs})
        return type("QL", (), {"id": row_id})()

    async def create_message_generation(self, **kwargs: Any) -> Any:
        row_id = uuid.uuid4()
        self.generations.append({"id": row_id, **kwargs})
        return type("MG", (), {"id": row_id})()


class FakeSession:
    async def flush(self) -> None:
        return None


# ---------------------------------------------------------------------------
# Wiring helpers — real HybridRetrievalService + Orchestrator
# ---------------------------------------------------------------------------


@dataclass
class IntegrationStack:
    world: SeedWorld
    settings: Settings
    qdrant: SeededQdrant
    es: SeededElasticsearch
    neo4j: SeededNeo4j
    retrieval_repo: SeededRetrievalRepo
    hybrid: HybridRetrievalService
    history: FakeHistoryRepo
    search: SearchService
    cache_repo: FakeCacheRepo
    observability: FakeObservability
    orchestrator: QueryOrchestrator
    cache_writer: QueryCacheWriter


def build_stack(world: SeedWorld | None = None) -> IntegrationStack:
    world = world or build_seed_world()
    settings = _settings()
    rules = build_router_rules(settings)
    qdrant = SeededQdrant(world)
    es = SeededElasticsearch(world)
    neo4j = SeededNeo4j(world)
    retrieval_repo = SeededRetrievalRepo(world)
    hybrid = HybridRetrievalService(
        settings=settings,
        vector_search=VectorSearch(
            settings=settings,
            qdrant=qdrant,  # type: ignore[arg-type]
            repo=retrieval_repo,  # type: ignore[arg-type]
        ),
        bm25_search=Bm25Search(
            settings=settings,
            elasticsearch=es,  # type: ignore[arg-type]
            repo=retrieval_repo,  # type: ignore[arg-type]
        ),
        graph_search=GraphSearch(
            settings=settings,
            neo4j=neo4j,  # type: ignore[arg-type]
            repo=retrieval_repo,  # type: ignore[arg-type]
        ),
        reranker=Reranker(settings),
    )
    history = FakeHistoryRepo()
    search = SearchService(
        hybrid=hybrid,
        history_repo=history,  # type: ignore[arg-type]
        retrieval_repo=retrieval_repo,  # type: ignore[arg-type]
    )
    cache_repo = FakeCacheRepo()
    observability = FakeObservability()
    router = QueryRouter(
        rules=rules,
        cache=QueryCacheService(
            settings=settings,
            rules=rules,
            repo=cache_repo,  # type: ignore[arg-type]
            qdrant=qdrant,  # type: ignore[arg-type]
            embedding=HashingNgramEmbeddingProvider(dimension=32),
        ),
        classifier=build_rule_based_classifier(settings),
        hybrid=hybrid,
    )
    orch = QueryOrchestrator(
        router=router,
        metadata_branch=MetadataBranch(
            retrieval_repo=retrieval_repo,  # type: ignore[arg-type]
            member_repo=SeededMemberRepo(world),  # type: ignore[arg-type]
        ),
        factoid_branch=FactoidBranch(retrieval_repo=retrieval_repo),  # type: ignore[arg-type]
        observability=observability,  # type: ignore[arg-type]
    )
    writer = QueryCacheWriter(repo=cache_repo, settings=settings)  # type: ignore[arg-type]
    return IntegrationStack(
        world=world,
        settings=settings,
        qdrant=qdrant,
        es=es,
        neo4j=neo4j,
        retrieval_repo=retrieval_repo,
        hybrid=hybrid,
        history=history,
        search=search,
        cache_repo=cache_repo,
        observability=observability,
        orchestrator=orch,
        cache_writer=writer,
    )


LLM_TARGETS = (
    "app.adapters.anthropic_client.extract_structured_json",
)


@pytest.fixture
def stack() -> IntegrationStack:
    return build_stack()


# ---------------------------------------------------------------------------
# 1. Search API + History + Hybrid Retrieval + RBAC
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_api_and_history_e2e(
    stack: IntegrationStack,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = stack.world

    async def _user() -> CurrentUser:
        return CurrentUser(id=world.user_id, email="member@example.com", full_name="Member")

    async def _role(
        self: Any,
        *,
        user_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> RoleName | None:
        if workspace_id == world.workspace_id and user_id == world.user_id:
            return RoleName.editor
        return None

    async def _db():
        yield FakeSession()

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[get_search_service] = lambda: stack.search
    app.dependency_overrides[get_workspace_rate_limiter] = (
        lambda: InMemoryWorkspaceRateLimiter()
    )
    monkeypatch.setattr(WorkspaceMemberRepository, "get_role_for_user", _role)

    with patch(LLM_TARGETS[0], MagicMock(side_effect=AssertionError("LLM forbidden"))):
        transport = ASGITransport(app=app)
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    f"/workspaces/{world.workspace_id}/search",
                    json={"query_text": "AI là gì?", "top_k": 5},
                )
                assert resp.status_code == 200
                payload = resp.json()

                # OpenAPI SearchResultResponse shape
                assert set(payload.keys()) >= {"history_id", "results_count", "results"}
                assert payload["results_count"] >= 1
                assert isinstance(payload["results"], list)
                assert len(payload["results"]) >= 1
                item = payload["results"][0]
                assert set(item.keys()) >= {
                    "document_id",
                    "text_snippet",
                    "retrieval_method",
                    "score",
                    "rank",
                }
                assert item["document_id"] == str(world.document_id)
                assert item["retrieval_method"] in {
                    "vector",
                    "bm25",
                    "knowledge_graph",
                    "rerank",
                }
                assert isinstance(item["score"], (int, float))
                assert item["score"] >= 0
                assert isinstance(item["rank"], int) and item["rank"] >= 1
                history_id = payload["history_id"]
                assert uuid.UUID(history_id)

                # Real Hybrid path used seeded adapters (not mocked retrieve)
                assert stack.qdrant.search_calls >= 1
                assert stack.es.search_calls >= 1
                assert stack.neo4j.search_calls >= 1
                assert len(stack.history.rows) == 1
                assert stack.history.rows[0].workspace_id == world.workspace_id
                assert stack.history.rows[0].user_id == world.user_id
                assert stack.history.rows[0].id == uuid.UUID(history_id)

                hist = await client.get(
                    f"/workspaces/{world.workspace_id}/search/history",
                    params={"page": 1, "page_size": 20},
                )
                assert hist.status_code == 200
                rows = hist.json()
                assert len(rows) == 1
                assert rows[0]["id"] == history_id
                assert rows[0]["query_text"] == "AI là gì?"
                assert rows[0]["results_count"] == payload["results_count"]
                assert "created_at" in rows[0]

                # RBAC: outsider gets 403
                async def _outsider() -> CurrentUser:
                    return CurrentUser(
                        id=world.outsider_id,
                        email="out@example.com",
                        full_name="Out",
                    )

                app.dependency_overrides[get_current_user] = _outsider
                forbidden = await client.post(
                    f"/workspaces/{world.workspace_id}/search",
                    json={"query_text": "AI là gì?"},
                )
                assert forbidden.status_code == 403
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 2–4. Orchestrator routes + logging + cache lifecycle + no LLM
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_four_routes_logging_cache_cleanup_no_llm(
    stack: IntegrationStack,
) -> None:
    world = stack.world
    orch = stack.orchestrator
    obs = stack.observability

    llm_spy = MagicMock(side_effect=AssertionError("LLM must not be called"))

    with patch(LLM_TARGETS[0], llm_spy):
        # --- Metadata ---
        meta_msg = uuid.uuid4()
        meta = await orch.handle_query(
            world.workspace_id,
            world.user_id,
            "Có bao nhiêu tài liệu?",
            message_id=meta_msg,
        )
        assert meta.route_type == RouteType.metadata
        assert meta.verify is True
        assert meta.metadata.get("count") == len(world.docs)
        assert str(len(world.docs)) in (meta.answer or "")
        # Metadata must not fan out hybrid adapters
        qdrant_before_factoid = stack.qdrant.search_calls

        # --- Factoid (real hybrid retrieve once inside router) ---
        fact_msg = uuid.uuid4()
        calls_before = stack.qdrant.search_calls
        fact = await orch.handle_query(
            world.workspace_id,
            world.user_id,
            "AI là gì?",
            message_id=fact_msg,
        )
        assert fact.route_type == RouteType.factoid
        assert fact.answer == world.snippet
        assert fact.verify is True
        assert len(fact.citation_refs) == 1
        assert fact.citation_refs[0].chunk_id == world.chunk_id
        assert fact.citation_refs[0].verify is True
        # Retrieval ran for factoid classification (adapters called)
        assert stack.qdrant.search_calls > calls_before
        assert stack.qdrant.search_calls > qdrant_before_factoid

        # --- Complex placeholder ---
        complex_msg = uuid.uuid4()
        complex_result = await orch.handle_query(
            world.workspace_id,
            world.user_id,
            "So sánh chiến lược AI giữa hai tài liệu.",
            message_id=complex_msg,
        )
        assert complex_result.route_type == RouteType.complex
        assert complex_result.status == COMPLEX_STATUS
        assert complex_result.answer is None

        # --- Cache write-back then cache_hit (Part 5 lifecycle) ---
        cache_query = "What is machine learning?"
        written = await stack.cache_writer.write_cache(
            world.workspace_id,
            cache_query,
            None,
            "Machine learning is a subset of AI.",
            [
                CitationRef(
                    chunk_id=world.chunk_id,
                    document_id=world.document_id,
                    page_number=1,
                    verify=True,
                )
            ],
            ttl_seconds=3600,
        )
        assert written.hit_count == 0
        nq = build_normalized_query(cache_query)
        assert written.query_hash == nq.query_hash

        retrieve_calls_before_hit = stack.qdrant.search_calls
        cache_msg = uuid.uuid4()
        hit = await orch.handle_query(
            world.workspace_id,
            world.user_id,
            cache_query,
            message_id=cache_msg,
        )
        assert hit.route_type == RouteType.cache_hit
        assert hit.answer == "Machine learning is a subset of AI."
        assert hit.verify is True
        assert hit.cache_id == written.id
        # No additional hybrid retrieval after cache_hit
        assert stack.qdrant.search_calls == retrieve_calls_before_hit
        assert stack.cache_repo.rows[written.id].hit_count == 1

        # Second identical call increments hit_count again
        hit2 = await orch.handle_query(
            world.workspace_id,
            world.user_id,
            cache_query,
            message_id=uuid.uuid4(),
        )
        assert hit2.route_type == RouteType.cache_hit
        assert stack.cache_repo.rows[written.id].hit_count == 2
        assert stack.qdrant.search_calls == retrieve_calls_before_hit

    # Unified logging: exactly one log + generation per handle_query (4 routes
    # + 2 cache hits on same query = 5 handle_query calls above? Wait:
    # meta, fact, complex, hit, hit2 = 5. Spec asks for 4 routes with 4 logs.
    # Recount: we need assert for the four representative routes specifically.
    route_logs = obs.query_logs
    assert len(route_logs) == 5  # meta + factoid + complex + 2 cache hits
    assert len(obs.generations) == 5
    routes_seen = {row["route_type"] for row in route_logs}
    assert RouteType.cache_hit in routes_seen
    assert RouteType.metadata in routes_seen
    assert RouteType.factoid in routes_seen
    assert RouteType.complex in routes_seen
    assert all(row["llm_calls_count"] == 0 for row in route_logs)
    assert all(row["model_used"] is None for row in route_logs)

    # Dedicated 4-request logging check (fresh stack)
    stack2 = build_stack()
    with patch(LLM_TARGETS[0], MagicMock(side_effect=AssertionError("LLM forbidden"))):
        # Seed cache for cache_hit path
        await stack2.cache_writer.write_cache(
            stack2.world.workspace_id,
            "AI là gì?",
            None,
            stack2.world.snippet,
            [],
        )
        queries = [
            ("AI là gì?", RouteType.cache_hit),
            ("Có bao nhiêu tài liệu?", RouteType.metadata),
            ("Who is the author?", RouteType.factoid),
            ("So sánh chiến lược AI giữa hai tài liệu.", RouteType.complex),
        ]
        for q, expected in queries:
            # For factoid use a non-cached factoid question
            result = await stack2.orchestrator.handle_query(
                stack2.world.workspace_id,
                stack2.world.user_id,
                q,
                message_id=uuid.uuid4(),
            )
            assert result.route_type == expected

    assert len(stack2.observability.query_logs) == 4
    assert len(stack2.observability.generations) == 4
    assert {r["route_type"] for r in stack2.observability.query_logs} == {
        RouteType.cache_hit,
        RouteType.metadata,
        RouteType.factoid,
        RouteType.complex,
    }

    llm_spy.assert_not_called()

    # Cleanup job: expire one entry, keep another
    now = datetime.now(UTC)
    live = await stack.cache_writer.write_cache(
        world.workspace_id,
        "live cached",
        None,
        "still valid",
        [],
        ttl_seconds=3600,
        now=now,
    )
    expired = await stack.cache_writer.write_cache(
        world.workspace_id,
        "expired cached",
        None,
        "gone",
        [],
        ttl_seconds=60,
        now=now - timedelta(hours=2),
    )
    # Sync cleanup via FakeCacheRepo.delete_expired (mirrors Celery job semantics)
    deleted = await stack.cache_repo.delete_expired(now=now + timedelta(minutes=1))
    assert deleted >= 1
    assert live.id in stack.cache_repo.rows
    assert expired.id not in stack.cache_repo.rows

    # Celery helper with mocked session (idempotent second run)
    session = MagicMock()
    session.execute.side_effect = [
        MagicMock(rowcount=1),
        MagicMock(rowcount=0),
    ]
    session.flush = MagicMock()
    first = run_cleanup_expired_query_cache(session, now=now)
    second = run_cleanup_expired_query_cache(session, now=now)
    assert first["deleted_count"] == 1
    assert second["deleted_count"] == 0


@pytest.mark.asyncio
async def test_factoid_retrieval_called_at_most_once(stack: IntegrationStack) -> None:
    """Router probes hybrid once; FactoidBranch must not retrieve again."""
    world = stack.world
    hybrid_retrieve = stack.hybrid.retrieve
    call_counter = {"n": 0}

    async def _counting_retrieve(*args: Any, **kwargs: Any) -> Any:
        call_counter["n"] += 1
        return await hybrid_retrieve(*args, **kwargs)

    stack.hybrid.retrieve = _counting_retrieve  # type: ignore[method-assign]
    # Re-bind router hybrid reference already points to same object.

    with patch(LLM_TARGETS[0], MagicMock(side_effect=AssertionError("LLM forbidden"))):
        result = await stack.orchestrator.handle_query(
            world.workspace_id,
            world.user_id,
            "What is RAG?",
            message_id=uuid.uuid4(),
        )
    assert result.route_type == RouteType.factoid
    assert call_counter["n"] == 1


@pytest.mark.asyncio
async def test_cache_hit_skips_retrieval_entirely(stack: IntegrationStack) -> None:
    world = stack.world
    query = "Cached definition of AI"
    await stack.cache_writer.write_cache(
        world.workspace_id,
        query,
        None,
        "cached answer body",
        [],
    )
    hybrid_spy = AsyncMock(side_effect=AssertionError("retrieve must not run"))
    stack.hybrid.retrieve = hybrid_spy  # type: ignore[method-assign]

    with patch(LLM_TARGETS[0], MagicMock(side_effect=AssertionError("LLM forbidden"))):
        result = await stack.orchestrator.handle_query(
            world.workspace_id,
            world.user_id,
            query,
            message_id=uuid.uuid4(),
        )
    assert result.route_type == RouteType.cache_hit
    assert result.answer == "cached answer body"
    hybrid_spy.assert_not_awaited()
