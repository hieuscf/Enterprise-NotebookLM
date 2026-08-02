# =============================================================================
# File: query_cache.py
# Module/Service: Query Router — Query Cache (FR11)
# Layer: Repository
# Purpose: Async (+ sync cleanup) data access for query_cache (exact + hits).
# Responsibilities:
#   - get_exact / get_by_ids / save / update_hit / delete_expired
#   - Atomic hit_count increment (no lost updates under concurrent hits)
# Dependencies:
#   - SQLAlchemy AsyncSession / Session, app.models.query.QueryCache
# Public Exports:
#   - QueryCacheRepository, QueryCacheRepositoryError, delete_expired_query_cache_sync
# Database/Table: query_cache
# Related Modules: app.services.query_router.cache, cache_writer, cleanup task
# Important Notes:
#   - Always filter by workspace_id on tenant reads.
#   - Schema is fixed — do not add/drop columns here.
#   - Vector similarity search lives in Qdrant adapter (not SQL brute-force).
# =============================================================================

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Sequence

from sqlalchemy import delete, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.query import QueryCache


class QueryCacheRepositoryError(Exception):
    """Raised when query_cache insert/delete persistence fails."""

    def __init__(self, message: str, *, code: str = "query_cache_repository_error") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class QueryCacheRepository:
    """Postgres access for ``query_cache`` rows (no SQL in services)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Exact lookup
    # ------------------------------------------------------------------

    async def get_exact(
        self,
        *,
        workspace_id: uuid.UUID,
        query_hash: str,
        now: datetime | None = None,
    ) -> QueryCache | None:
        """Return a non-expired exact hash match for the workspace.

        Equivalent SQL::

            SELECT * FROM query_cache
            WHERE workspace_id = :ws AND query_hash = :hash AND expires_at > NOW()
            ORDER BY created_at DESC LIMIT 1
        """
        return await self.find_exact_hit(
            workspace_id=workspace_id,
            query_hash=query_hash,
            now=now,
        )

    async def find_exact_hit(
        self,
        *,
        workspace_id: uuid.UUID,
        query_hash: str,
        now: datetime | None = None,
    ) -> QueryCache | None:
        """Backward-compatible alias for ``get_exact``."""
        ts = now or datetime.now(UTC)
        stmt = (
            select(QueryCache)
            .where(
                QueryCache.workspace_id == workspace_id,
                QueryCache.query_hash == query_hash,
                QueryCache.expires_at > ts,
            )
            .order_by(QueryCache.created_at.desc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_id(
        self,
        *,
        workspace_id: uuid.UUID,
        cache_id: uuid.UUID,
        now: datetime | None = None,
    ) -> QueryCache | None:
        """Load a non-expired cache row by id within ``workspace_id``."""
        ts = now or datetime.now(UTC)
        stmt = select(QueryCache).where(
            QueryCache.id == cache_id,
            QueryCache.workspace_id == workspace_id,
            QueryCache.expires_at > ts,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_similar(
        self,
        *,
        workspace_id: uuid.UUID,
        cache_ids: Sequence[uuid.UUID],
        now: datetime | None = None,
    ) -> list[QueryCache]:
        """Load non-expired rows for Qdrant candidate ids (workspace-scoped).

        Vector ANN happens in Qdrant; this method only hydrates Postgres rows
        and filters ``expires_at > now``. Order follows ``cache_ids``.
        """
        if not cache_ids:
            return []
        ts = now or datetime.now(UTC)
        stmt = select(QueryCache).where(
            QueryCache.workspace_id == workspace_id,
            QueryCache.id.in_(list(cache_ids)),
            QueryCache.expires_at > ts,
        )
        rows = list((await self._session.execute(stmt)).scalars().all())
        by_id = {row.id: row for row in rows}
        return [by_id[cid] for cid in cache_ids if cid in by_id]

    # ------------------------------------------------------------------
    # Hit update (transaction-safe)
    # ------------------------------------------------------------------

    async def update_hit(
        self,
        cache_id: uuid.UUID,
        *,
        now: datetime | None = None,
    ) -> QueryCache | None:
        """Atomically increment ``hit_count`` and set ``last_used_at``.

        Uses ``hit_count = hit_count + 1`` in SQL so concurrent hits do not
        lose increments under read-modify-write races.
        """
        ts = now or datetime.now(UTC)
        stmt = (
            update(QueryCache)
            .where(QueryCache.id == cache_id)
            .values(
                hit_count=QueryCache.hit_count + 1,
                last_used_at=ts,
            )
            .returning(QueryCache)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        await self._session.flush()
        return row

    async def record_hit(self, cache: QueryCache, *, now: datetime | None = None) -> QueryCache:
        """Backward-compatible hit update returning the refreshed ORM row."""
        updated = await self.update_hit(cache.id, now=now)
        if updated is None:
            # Row vanished mid-flight — keep in-memory best-effort.
            ts = now or datetime.now(UTC)
            cache.hit_count = int(cache.hit_count or 0) + 1
            cache.last_used_at = ts
            return cache
        cache.hit_count = updated.hit_count
        cache.last_used_at = updated.last_used_at
        return cache

    # ------------------------------------------------------------------
    # Persist
    # ------------------------------------------------------------------

    async def save(
        self,
        *,
        workspace_id: uuid.UUID,
        query_hash: str,
        query_text: str,
        answer: str,
        citation_refs: list[dict[str, Any]] | dict[str, Any] | None,
        ttl_seconds: int,
        expires_at: datetime,
        similarity_threshold: float,
        query_embedding_id: uuid.UUID | None = None,
        hit_count: int = 0,
        last_used_at: datetime | None = None,
        now: datetime | None = None,
    ) -> QueryCache:
        """Insert a new ``query_cache`` row (preferred Task-2 name)."""
        return await self.create(
            workspace_id=workspace_id,
            query_hash=query_hash,
            query_text=query_text,
            answer=answer,
            citation_refs=citation_refs,
            ttl_seconds=ttl_seconds,
            expires_at=expires_at,
            similarity_threshold=similarity_threshold,
            query_embedding_id=query_embedding_id,
            hit_count=hit_count,
            last_used_at=last_used_at,
            now=now,
        )

    async def create(
        self,
        *,
        workspace_id: uuid.UUID,
        query_hash: str,
        query_text: str,
        answer: str,
        citation_refs: list[dict[str, Any]] | dict[str, Any] | None,
        ttl_seconds: int,
        expires_at: datetime,
        similarity_threshold: float,
        query_embedding_id: uuid.UUID | None = None,
        hit_count: int = 0,
        last_used_at: datetime | None = None,
        now: datetime | None = None,
    ) -> QueryCache:
        """Insert a new ``query_cache`` row (does not overwrite existing rows).

        Args:
            workspace_id: Tenant scope — must match caller's workspace.
            query_hash: SHA-256 of normalized query.
            query_text: Normalized query text (schema has no separate column).
            answer: Cached answer body.
            citation_refs: JSONB-serializable citation list/dict.
            ttl_seconds: TTL applied when computing ``expires_at``.
            expires_at: Timezone-aware expiry timestamp.
            similarity_threshold: Per-entry semantic hit threshold.
            query_embedding_id: Optional FK to ``embeddings``.
            hit_count: Initial hit count (default 0).
            last_used_at: Initial last-used (default NULL).
            now: Optional created_at override (tests).

        Returns:
            Persisted ``QueryCache`` instance.

        Raises:
            QueryCacheRepositoryError: On SQLAlchemy persistence failure.
        """
        created = now or datetime.now(UTC)
        row = QueryCache(
            workspace_id=workspace_id,
            query_embedding_id=query_embedding_id,
            query_hash=query_hash,
            query_text=query_text,
            answer=answer,
            citation_refs=citation_refs,
            similarity_threshold=similarity_threshold,
            hit_count=hit_count,
            ttl_seconds=ttl_seconds,
            expires_at=expires_at,
            created_at=created,
            last_used_at=last_used_at,
        )
        try:
            self._session.add(row)
            await self._session.flush()
        except SQLAlchemyError as exc:
            raise QueryCacheRepositoryError(
                f"Failed to insert query_cache: {exc}"
            ) from exc
        return row

    async def delete_expired(self, *, now: datetime | None = None) -> int:
        """Delete all rows with ``expires_at < now`` (uses expires_at index).

        Returns:
            Number of deleted rows.

        Raises:
            QueryCacheRepositoryError: On SQLAlchemy failure.
        """
        ts = now or datetime.now(UTC)
        try:
            result = await self._session.execute(
                delete(QueryCache).where(QueryCache.expires_at < ts)
            )
            await self._session.flush()
        except SQLAlchemyError as exc:
            raise QueryCacheRepositoryError(
                f"Failed to delete expired query_cache: {exc}"
            ) from exc
        return int(result.rowcount or 0)


def delete_expired_query_cache_sync(
    session: Session,
    *,
    now: datetime | None = None,
) -> int:
    """Synchronous expired-row delete for Celery workers.

    Args:
        session: Sync SQLAlchemy session (Celery).
        now: Optional clock override for tests.

    Returns:
        Number of deleted rows.

    Raises:
        QueryCacheRepositoryError: On SQLAlchemy failure.
    """
    ts = now or datetime.now(UTC)
    try:
        result = session.execute(delete(QueryCache).where(QueryCache.expires_at < ts))
        session.flush()
    except SQLAlchemyError as exc:
        raise QueryCacheRepositoryError(
            f"Failed to delete expired query_cache: {exc}"
        ) from exc
    return int(result.rowcount or 0)
