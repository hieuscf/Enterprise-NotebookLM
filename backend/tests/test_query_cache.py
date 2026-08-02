# =============================================================================
# File: test_query_cache.py
# Module/Service: Query Router — Query Cache (FR11 / Task 2)
# Layer: Service
# Purpose: Unit tests for exact + semantic cache, save, hit updates, indexes.
# Responsibilities:
#   - normalize/hash; exact hit/miss/expired/isolation; similarity threshold;
#     save TTL; migration index presence
# Dependencies:
#   - pytest, numpy, app.services.query_router.cache, repositories.query_cache
# Public Exports:
#   - N/A
# Database/Table: query_cache (fakes + model/migration assertions)
# Related Modules: QueryCacheService, QueryCacheRepository, EmbeddingProvider
# Important Notes: 0 live Postgres/Qdrant/LLM in CI.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest
from numpy.typing import NDArray

from app.config.router_rules import build_router_rules
from app.core.config import Settings
from app.models.query import QueryCache
from app.services.query_router.cache import (
    QueryCacheService,
    build_normalized_query,
    hash_query,
    normalize_query,
)
from app.services.query_router.embedding_provider import HashingNgramEmbeddingProvider
from app.services.query_router.schemas import CitationRef


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "embedding_model_name": "local-hash-embedding-v1",
        "embedding_dimension": 8,
        "embedding_provider": "local",
        "query_cache_similarity_threshold": 0.90,
        "query_cache_default_ttl_seconds": 3600,
        "query_cache_semantic_top_k": 5,
    }
    base.update(overrides)
    return Settings(**base)


class FakeEmbedding:
    """Fixed-vector provider for deterministic semantic tests."""

    def __init__(self, vector: list[float] | None = None) -> None:
        self._vector = np.asarray(vector or [1.0, 0.0, 0.0, 0.0], dtype=np.float64)
        self.calls = 0

    def embed(self, texts: list[str]) -> NDArray[np.float64]:
        self.calls += 1
        return np.vstack([self._vector for _ in texts])


class FakeCacheRepo:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, QueryCache] = {}
        self.by_hash: dict[tuple[uuid.UUID, str], QueryCache] = {}
        self.hit_updates = 0

    def add(self, row: QueryCache) -> QueryCache:
        self.rows[row.id] = row
        self.by_hash[(row.workspace_id, row.query_hash)] = row
        return row

    async def get_exact(
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
        self.hit_updates += 1
        ts = now or datetime.now(UTC)
        cache.hit_count = int(cache.hit_count or 0) + 1
        cache.last_used_at = ts
        return cache

    async def update_hit(
        self, cache_id: uuid.UUID, *, now: datetime | None = None
    ) -> QueryCache | None:
        row = self.rows.get(cache_id)
        if row is None:
            return None
        return await self.record_hit(row, now=now)

    async def save(self, **kwargs: Any) -> QueryCache:
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


def _make_row(
    *,
    workspace_id: uuid.UUID,
    query_text: str,
    answer: str = "cached answer",
    threshold: float = 0.85,
    expires_at: datetime | None = None,
    hit_count: int = 0,
) -> QueryCache:
    nq = build_normalized_query(query_text)
    return QueryCache(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        query_embedding_id=None,
        query_hash=nq.query_hash,
        query_text=nq.normalized,
        answer=answer,
        citation_refs=[{"chunk_id": str(uuid.uuid4()), "verify": True}],
        similarity_threshold=threshold,
        hit_count=hit_count,
        ttl_seconds=3600,
        expires_at=expires_at or (datetime.now(UTC) + timedelta(hours=1)),
        created_at=datetime.now(UTC),
        last_used_at=None,
    )


def _service(
    *,
    repo: FakeCacheRepo | None = None,
    qdrant: MagicMock | None = None,
    embedding: Any | None = None,
    settings: Settings | None = None,
) -> tuple[QueryCacheService, FakeCacheRepo, MagicMock, Any]:
    settings = settings or _settings()
    rules = build_router_rules(settings)
    repo = repo or FakeCacheRepo()
    qdrant = qdrant or MagicMock()
    if getattr(qdrant.search_similar, "return_value", None) is None and not getattr(
        qdrant.search_similar, "side_effect", None
    ):
        qdrant.search_similar.return_value = []
    embedding = embedding or FakeEmbedding()
    svc = QueryCacheService(
        settings=settings,
        rules=rules,
        repo=repo,  # type: ignore[arg-type]
        qdrant=qdrant,
        embedding=embedding,
    )
    return svc, repo, qdrant, embedding


# ---------------------------------------------------------------------------
# normalize_query / hash
# ---------------------------------------------------------------------------


def test_normalize_lowercase_trim_spaces_punctuation() -> None:
    assert normalize_query("  What IS   Apple's CEO??? ") == "what is apple ceo"


def test_normalize_unicode_nfkc() -> None:
    # Fullwidth digits collapse via NFKC
    assert "hello" in normalize_query("Ｈｅｌｌｏ!!!")


def test_hash_deterministic_sha256() -> None:
    a = hash_query("what is apple ceo")
    b = hash_query("what is apple ceo")
    assert a == b
    assert len(a) == 64
    assert a != hash_query("what is apple ceo ")


# ---------------------------------------------------------------------------
# Exact cache
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exact_cache_hit_updates_counters_and_answer() -> None:
    ws = uuid.uuid4()
    row = _make_row(workspace_id=ws, query_text="What is RAG?", answer="Retrieval + gen")
    repo = FakeCacheRepo()
    repo.add(row)
    svc, _, qdrant, embedding = _service(repo=repo)

    view = await svc.check_exact_cache(workspace_id=ws, query_hash=row.query_hash)
    assert view is not None
    assert view.answer == "Retrieval + gen"
    assert view.match_type == "exact"
    assert view.hit_count == 1
    assert view.last_used_at is not None
    assert repo.hit_updates == 1
    qdrant.search_similar.assert_not_called()
    assert embedding.calls == 0


@pytest.mark.asyncio
async def test_exact_cache_miss() -> None:
    svc, _, _, embedding = _service()
    view = await svc.check_exact_cache(
        workspace_id=uuid.uuid4(),
        query_hash=hash_query("missing query"),
    )
    assert view is None
    assert embedding.calls == 0


@pytest.mark.asyncio
async def test_exact_cache_expired() -> None:
    ws = uuid.uuid4()
    row = _make_row(
        workspace_id=ws,
        query_text="old question",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    repo = FakeCacheRepo()
    repo.add(row)
    svc, _, _, _ = _service(repo=repo)
    view = await svc.check_exact_cache(workspace_id=ws, query_hash=row.query_hash)
    assert view is None
    assert repo.hit_updates == 0


@pytest.mark.asyncio
async def test_exact_cache_workspace_isolation() -> None:
    ws_a, ws_b = uuid.uuid4(), uuid.uuid4()
    row = _make_row(workspace_id=ws_a, query_text="shared wording")
    repo = FakeCacheRepo()
    repo.add(row)
    svc, _, _, _ = _service(repo=repo)
    assert await svc.check_exact_cache(workspace_id=ws_b, query_hash=row.query_hash) is None
    assert await svc.check_exact_cache(workspace_id=ws_a, query_hash=row.query_hash) is not None


# ---------------------------------------------------------------------------
# Similarity cache
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_similarity_cache_hit_uses_per_entry_threshold() -> None:
    ws = uuid.uuid4()
    row = _make_row(workspace_id=ws, query_text="original", threshold=0.80, answer="sem answer")
    repo = FakeCacheRepo()
    repo.add(row)
    qdrant = MagicMock()
    qdrant.search_similar.return_value = [
        {"score": 0.91, "cache_id": str(row.id), "payload": {"cache_id": str(row.id)}}
    ]
    svc, _, _, embedding = _service(repo=repo, qdrant=qdrant)

    view, vector, sim = await svc.check_similarity_cache(
        workspace_id=ws,
        normalized_text="slightly different",
    )
    assert view is not None
    assert view.answer == "sem answer"
    assert view.match_type == "semantic"
    assert view.hit_count == 1
    assert sim == pytest.approx(0.91)
    assert len(vector) > 0
    assert embedding.calls == 1
    qdrant.search_similar.assert_called_once()
    assert qdrant.search_similar.call_args.kwargs["top_k"] == 5


@pytest.mark.asyncio
async def test_similarity_below_entry_threshold_is_miss() -> None:
    ws = uuid.uuid4()
    row = _make_row(workspace_id=ws, query_text="original", threshold=0.95)
    repo = FakeCacheRepo()
    repo.add(row)
    qdrant = MagicMock()
    qdrant.search_similar.return_value = [
        {"score": 0.90, "cache_id": str(row.id), "payload": {"cache_id": str(row.id)}}
    ]
    svc, _, _, _ = _service(repo=repo, qdrant=qdrant)
    view, _, sim = await svc.check_similarity_cache(
        workspace_id=ws, normalized_text="close but not enough"
    )
    assert view is None
    assert sim == pytest.approx(0.90)
    assert repo.hit_updates == 0


@pytest.mark.asyncio
async def test_similarity_expired_candidate_skipped() -> None:
    ws = uuid.uuid4()
    row = _make_row(
        workspace_id=ws,
        query_text="expired",
        threshold=0.50,
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    repo = FakeCacheRepo()
    repo.add(row)
    qdrant = MagicMock()
    qdrant.search_similar.return_value = [
        {"score": 0.99, "cache_id": str(row.id), "payload": {"cache_id": str(row.id)}}
    ]
    svc, _, _, _ = _service(repo=repo, qdrant=qdrant)
    view, _, _ = await svc.check_similarity_cache(
        workspace_id=ws, normalized_text="anything"
    )
    assert view is None


@pytest.mark.asyncio
async def test_similarity_other_workspace_not_returned() -> None:
    ws_a, ws_b = uuid.uuid4(), uuid.uuid4()
    row = _make_row(workspace_id=ws_a, query_text="cached", threshold=0.50)
    repo = FakeCacheRepo()
    repo.add(row)
    qdrant = MagicMock()
    # Even if Qdrant misbehaves and returns foreign id, repo filters workspace.
    qdrant.search_similar.return_value = [
        {"score": 0.99, "cache_id": str(row.id), "payload": {"cache_id": str(row.id)}}
    ]
    svc, _, _, _ = _service(repo=repo, qdrant=qdrant)
    view, _, _ = await svc.check_similarity_cache(
        workspace_id=ws_b, normalized_text="cached"
    )
    assert view is None


@pytest.mark.asyncio
async def test_similarity_picks_first_candidate_above_its_threshold() -> None:
    ws = uuid.uuid4()
    low = _make_row(workspace_id=ws, query_text="a", threshold=0.99, answer="too strict")
    good = _make_row(workspace_id=ws, query_text="b", threshold=0.70, answer="good hit")
    repo = FakeCacheRepo()
    repo.add(low)
    repo.add(good)
    qdrant = MagicMock()
    qdrant.search_similar.return_value = [
        {"score": 0.85, "cache_id": str(low.id), "payload": {"cache_id": str(low.id)}},
        {"score": 0.80, "cache_id": str(good.id), "payload": {"cache_id": str(good.id)}},
    ]
    svc, _, _, _ = _service(repo=repo, qdrant=qdrant)
    view, _, sim = await svc.check_similarity_cache(
        workspace_id=ws, normalized_text="query"
    )
    assert view is not None
    assert view.answer == "good hit"
    assert view.id == good.id
    assert sim == pytest.approx(0.80)


# ---------------------------------------------------------------------------
# Save cache
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_query_cache_ttl_hash_and_vector_upsert() -> None:
    ws = uuid.uuid4()
    emb_id = uuid.uuid4()
    qdrant = MagicMock()
    embedding = FakeEmbedding([0.1, 0.2, 0.3, 0.4])
    svc, repo, _, _ = _service(qdrant=qdrant, embedding=embedding)
    now = datetime(2026, 8, 2, 12, 0, 0, tzinfo=UTC)

    row = await svc.save_query_cache(
        workspace_id=ws,
        query_text="  What IS  caching??? ",
        answer="Reuse prior answers.",
        citation_refs=[
            CitationRef(
                chunk_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                page_number=2,
                verify=True,
            )
        ],
        ttl_seconds=1800,
        similarity_threshold=0.88,
        query_embedding_id=emb_id,
        now=now,
    )
    assert row.workspace_id == ws
    assert row.query_hash == hash_query(normalize_query("  What IS  caching??? "))
    assert row.query_text == "what is caching"
    assert row.ttl_seconds == 1800
    assert row.expires_at == now + timedelta(seconds=1800)
    assert row.similarity_threshold == pytest.approx(0.88)
    assert row.query_embedding_id == emb_id
    assert row.hit_count == 0
    assert row.id in repo.rows
    qdrant.upsert_chunk_vector.assert_called_once()
    payload = qdrant.upsert_chunk_vector.call_args.kwargs["payload"]
    assert payload["cache_id"] == str(row.id)
    assert payload["workspace_id"] == str(ws)
    assert payload["kind"] == "query_cache"


@pytest.mark.asyncio
async def test_save_rejects_empty_answer_and_bad_ttl() -> None:
    svc, _, _, _ = _service()
    with pytest.raises(ValueError, match="answer"):
        await svc.save_query_cache(
            workspace_id=uuid.uuid4(),
            query_text="q",
            answer="  ",
            citation_refs=None,
            ttl_seconds=60,
        )
    with pytest.raises(ValueError, match="ttl"):
        await svc.save_query_cache(
            workspace_id=uuid.uuid4(),
            query_text="q",
            answer="ok",
            citation_refs=None,
            ttl_seconds=0,
        )


# ---------------------------------------------------------------------------
# Migration / index validation
# ---------------------------------------------------------------------------


def test_query_hash_index_declared_on_model() -> None:
    index_names = {idx.name for idx in QueryCache.__table__.indexes}
    assert "ix_query_cache_query_hash" in index_names
    assert "ix_query_cache_workspace_id_expires_at" in index_names
    assert "ix_query_cache_expires_at" in index_names


def test_query_hash_index_in_alembic_initial_migration() -> None:
    root = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    initial = root / "6ebf6936f6c1_initial_schema_v2.py"
    text = initial.read_text(encoding="utf-8")
    assert 'op.create_index("ix_query_cache_query_hash"' in text
    assert '"query_cache"' in text
    assert '"query_hash"' in text


def test_hashing_embedding_provider_reusable_from_task1() -> None:
    provider = HashingNgramEmbeddingProvider(dimension=32)
    svc, _, qdrant, _ = _service(embedding=provider)
    assert svc._embedding is provider  # noqa: SLF001 — DI wiring check
    qdrant.search_similar.return_value = []
