# =============================================================================
# File: query_cache.py
# Module/Service: Query Router
# Layer: Repository
# Purpose: Async (+ sync cleanup) data access for query_cache (FR11 lifecycle).
# Responsibilities:
#   - Exact hash lookup; hit updates; insert write-back; delete expired rows
# Dependencies:
#   - SQLAlchemy AsyncSession / Session, app.models.query.QueryCache
# Public Exports:
#   - QueryCacheRepository, delete_expired_query_cache_sync
# Database/Table: query_cache
# Related Modules: app.services.query_router.cache, cache_writer, cleanup task
# Important Notes: Always filter by workspace_id on reads/writes; cleanup is
#   global by expires_at only (no cross-workspace targeting beyond expiry).
# =============================================================================

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

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
    """Postgres access for ``query_cache`` rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_exact_hit(
        self,
        *,
        workspace_id: uuid.UUID,
        query_hash: str,
        now: datetime | None = None,
    ) -> QueryCache | None:
        """Return a non-expired exact hash match for the workspace."""
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

    async def record_hit(self, cache: QueryCache, *, now: datetime | None = None) -> QueryCache:
        """Increment ``hit_count`` and set ``last_used_at`` (exact or semantic hit)."""
        ts = now or datetime.now(UTC)
        cache.hit_count = int(cache.hit_count or 0) + 1
        cache.last_used_at = ts
        await self._session.execute(
            update(QueryCache)
            .where(QueryCache.id == cache.id)
            .values(hit_count=cache.hit_count, last_used_at=ts)
        )
        await self._session.flush()
        return cache

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
            query_hash: SHA-256 of normalized query (Part 3 algorithm).
            query_text: Normalized query text (no separate normalized_query column).
            answer: Cached answer body.
            citation_refs: JSONB-serializable citation list/dict.
            ttl_seconds: TTL applied when computing ``expires_at``.
            expires_at: Timezone-aware expiry timestamp.
            similarity_threshold: Semantic hit threshold stored with the entry.
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
