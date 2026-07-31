# =============================================================================
# File: test_query_cache_lifecycle.py
# Module/Service: Query Cache Lifecycle (Part 5)
# Layer: Service / Worker
# Purpose: Unit + integration tests for cache write-back and expired cleanup.
# Responsibilities:
#   - write_cache hash/TTL/citations; repository errors; cleanup idempotency
# Dependencies:
#   - pytest, AsyncMock, app.services.query_router.cache_writer
# Public Exports:
#   - N/A
# Database/Table: N/A (in-memory fakes)
# Related Modules: QueryCacheWriter, cleanup_expired_cache, QueryCacheRepository
# Important Notes: No live Postgres/Celery broker in CI.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.models.query import QueryCache
from app.repositories.query_cache import (
    QueryCacheRepository,
    QueryCacheRepositoryError,
    delete_expired_query_cache_sync,
)
from app.services.query_router.cache import build_normalized_query, hash_query, normalize_query
from app.services.query_router.cache_writer import (
    QueryCacheWriter,
    serialize_citation_refs,
    write_cache,
)
from app.services.query_router.schemas import CitationRef
from app.tasks.cleanup_expired_cache import run_cleanup_expired_query_cache


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "embedding_model_name": "local-hash-embedding-v1",
        "embedding_dimension": 8,
        "embedding_provider": "local",
        "query_cache_similarity_threshold": 0.92,
        "query_cache_default_ttl_seconds": 3600,
        "query_cache_cleanup_interval_minutes": 15,
    }
    base.update(overrides)
    return Settings(**base)


class FakeQueryCacheRepo:
    """In-memory QueryCacheRepository stand-in for writer/cleanup tests."""

    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, QueryCache] = {}
        self.fail_create = False

    async def create(self, **kwargs: Any) -> QueryCache:
        if self.fail_create:
            raise QueryCacheRepositoryError("simulated insert failure")
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
        self.rows[row.id] = row
        return row

    async def delete_expired(self, *, now: datetime | None = None) -> int:
        ts = now or datetime.now(UTC)
        to_delete = [cid for cid, row in self.rows.items() if row.expires_at < ts]
        for cid in to_delete:
            del self.rows[cid]
        return len(to_delete)


# ---------------------------------------------------------------------------
# Cache Writer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_cache_inserts_with_correct_hash_and_citations() -> None:
    repo = FakeQueryCacheRepo()
    settings = _settings(query_cache_default_ttl_seconds=7200)
    writer = QueryCacheWriter(repo=repo, settings=settings)  # type: ignore[arg-type]
    workspace_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    raw = "  What IS  RAG??? "
    now = datetime(2026, 7, 31, 12, 0, 0, tzinfo=UTC)

    row = await writer.write_cache(
        workspace_id,
        raw,
        None,
        "RAG combines retrieval with generation.",
        [
            CitationRef(
                chunk_id=chunk_id,
                document_id=doc_id,
                page_number=4,
                verify=True,
            )
        ],
        now=now,
    )

    nq = build_normalized_query(raw)
    assert row.query_hash == nq.query_hash == hash_query(normalize_query(raw))
    assert row.query_text == nq.normalized
    assert row.answer == "RAG combines retrieval with generation."
    assert row.hit_count == 0
    assert row.last_used_at is None
    assert row.ttl_seconds == 7200
    assert row.expires_at == now + timedelta(seconds=7200)
    assert row.workspace_id == workspace_id
    assert row.citation_refs == [
        {
            "chunk_id": str(chunk_id),
            "document_id": str(doc_id),
            "page_number": 4,
            "verify": True,
        }
    ]
    assert len(repo.rows) == 1


@pytest.mark.asyncio
async def test_write_cache_ttl_override() -> None:
    repo = FakeQueryCacheRepo()
    settings = _settings(query_cache_default_ttl_seconds=3600)
    writer = QueryCacheWriter(repo=repo, settings=settings)  # type: ignore[arg-type]
    now = datetime(2026, 7, 31, 10, 0, 0, tzinfo=UTC)

    row = await writer.write_cache(
        uuid.uuid4(),
        "hello",
        None,
        "answer",
        [],
        ttl_seconds=120,
        now=now,
    )
    assert row.ttl_seconds == 120
    assert row.expires_at == now + timedelta(seconds=120)


@pytest.mark.asyncio
async def test_write_cache_uses_settings_default_ttl() -> None:
    repo = FakeQueryCacheRepo()
    settings = _settings(query_cache_default_ttl_seconds=5400)
    now = datetime(2026, 7, 31, 11, 0, 0, tzinfo=UTC)
    row = await write_cache(
        uuid.uuid4(),
        "count docs",
        None,
        "25 documents",
        None,
        ttl_seconds=None,
        repo=repo,  # type: ignore[arg-type]
        settings=settings,
        now=now,
    )
    assert row.ttl_seconds == 5400
    assert row.expires_at == now + timedelta(seconds=5400)


@pytest.mark.asyncio
async def test_write_cache_raises_repository_error() -> None:
    repo = FakeQueryCacheRepo()
    repo.fail_create = True
    writer = QueryCacheWriter(repo=repo, settings=_settings())  # type: ignore[arg-type]
    with pytest.raises(QueryCacheRepositoryError):
        await writer.write_cache(
            uuid.uuid4(),
            "q",
            None,
            "a",
            [],
        )


@pytest.mark.asyncio
async def test_repository_create_wraps_sqlalchemy_error() -> None:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock(side_effect=SQLAlchemyError("db down"))
    repo = QueryCacheRepository(session)
    with pytest.raises(QueryCacheRepositoryError):
        await repo.create(
            workspace_id=uuid.uuid4(),
            query_hash="abc",
            query_text="abc",
            answer="ans",
            citation_refs=None,
            ttl_seconds=60,
            expires_at=datetime.now(UTC) + timedelta(seconds=60),
            similarity_threshold=0.9,
        )


def test_serialize_citation_refs_preserves_fields() -> None:
    chunk_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    refs = serialize_citation_refs(
        [
            CitationRef(
                chunk_id=chunk_id,
                document_id=doc_id,
                page_number=1,
                verify=True,
            ),
            {
                "chunk_id": str(chunk_id),
                "document_id": str(doc_id),
                "page_number": 2,
                "verify": False,
            },
        ]
    )
    assert refs is not None
    assert refs[0]["page_number"] == 1
    assert refs[0]["verify"] is True
    assert refs[1]["verify"] is False


# ---------------------------------------------------------------------------
# Cleanup Job
# ---------------------------------------------------------------------------


class _MemRow:
    def __init__(self, expires_at: datetime) -> None:
        self.expires_at = expires_at
        self.id = uuid.uuid4()


def test_delete_expired_sync_only_removes_expired() -> None:
    """Simulate sync DELETE via session.execute return / in-memory filter."""
    now = datetime(2026, 7, 31, 12, 0, 0, tzinfo=UTC)
    store: dict[uuid.UUID, _MemRow] = {}
    expired = [_MemRow(now - timedelta(hours=1)) for _ in range(3)]
    valid = [_MemRow(now + timedelta(hours=1)) for _ in range(2)]
    for row in expired + valid:
        store[row.id] = row

    session = MagicMock()

    def _execute(stmt: Any) -> MagicMock:  # noqa: ARG001
        # Mimic DELETE WHERE expires_at < now
        deleted_ids = [rid for rid, row in list(store.items()) if row.expires_at < now]
        for rid in deleted_ids:
            del store[rid]
        result = MagicMock()
        result.rowcount = len(deleted_ids)
        return result

    session.execute.side_effect = _execute
    session.flush = MagicMock()

    deleted = delete_expired_query_cache_sync(session, now=now)
    assert deleted == 3
    assert len(store) == 2
    assert all(row.expires_at >= now for row in store.values())

    deleted_again = delete_expired_query_cache_sync(session, now=now)
    assert deleted_again == 0
    assert len(store) == 2


def test_cleanup_job_idempotent_second_run() -> None:
    now = datetime(2026, 7, 31, 15, 0, 0, tzinfo=UTC)
    session = MagicMock()
    # First call deletes 2; second deletes 0.
    first = MagicMock(rowcount=2)
    second = MagicMock(rowcount=0)
    session.execute.side_effect = [first, second]
    session.flush = MagicMock()

    result1 = run_cleanup_expired_query_cache(session, now=now)
    assert result1["deleted_count"] == 2
    assert "started_at" in result1
    assert "finished_at" in result1
    assert "duration_ms" in result1

    result2 = run_cleanup_expired_query_cache(session, now=now)
    assert result2["deleted_count"] == 0


def test_cleanup_propagates_repository_error() -> None:
    session = MagicMock()
    session.execute.side_effect = SQLAlchemyError("boom")
    with pytest.raises(QueryCacheRepositoryError):
        run_cleanup_expired_query_cache(session)


# ---------------------------------------------------------------------------
# Integration: write → cleanup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_then_cleanup_respects_ttl() -> None:
    repo = FakeQueryCacheRepo()
    settings = _settings(query_cache_default_ttl_seconds=3600)
    writer = QueryCacheWriter(repo=repo, settings=settings)  # type: ignore[arg-type]
    workspace_id = uuid.uuid4()
    t0 = datetime(2026, 7, 31, 8, 0, 0, tzinfo=UTC)

    live = await writer.write_cache(
        workspace_id,
        "live query",
        None,
        "live answer",
        [],
        ttl_seconds=3600,
        now=t0,
    )
    expired = await writer.write_cache(
        workspace_id,
        "expired query",
        None,
        "expired answer",
        [],
        ttl_seconds=60,
        now=t0 - timedelta(hours=2),
    )
    assert live.id in repo.rows
    assert expired.id in repo.rows

    # Before expiry of live entry: cleanup at t0+30m removes only expired.
    deleted = await repo.delete_expired(now=t0 + timedelta(minutes=30))
    assert deleted == 1
    assert live.id in repo.rows
    assert expired.id not in repo.rows

    # After live TTL: cleanup removes the remaining row.
    deleted2 = await repo.delete_expired(now=t0 + timedelta(hours=2))
    assert deleted2 == 1
    assert live.id not in repo.rows

    deleted3 = await repo.delete_expired(now=t0 + timedelta(hours=3))
    assert deleted3 == 0


def test_celery_beat_schedule_uses_settings_interval() -> None:
    with patch.dict(
        "os.environ",
        {"QUERY_CACHE_CLEANUP_INTERVAL_MINUTES": "20"},
        clear=False,
    ):
        # Re-import helper path: interval reader
        from app.workers.celery_app import _cleanup_interval_minutes

        assert _cleanup_interval_minutes() == 20


def test_celery_app_registers_cleanup_beat_entry() -> None:
    from app.workers import celery_app as celery_mod

    assert "cleanup-expired-query-cache" in celery_mod.celery_app.conf.beat_schedule
    entry = celery_mod.celery_app.conf.beat_schedule["cleanup-expired-query-cache"]
    assert entry["task"] == "cleanup_expired_query_cache"
