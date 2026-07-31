# =============================================================================
# File: query_cache.py
# Module/Service: Query Router
# Layer: Repository
# Purpose: Async data access for query_cache (FR11 exact + hit updates).
# Responsibilities:
#   - Exact hash lookup scoped by workspace_id and expires_at
#   - Load by id; increment hit_count / last_used_at on cache hit
# Dependencies:
#   - SQLAlchemy AsyncSession, app.models.query.QueryCache
# Public Exports:
#   - QueryCacheRepository
# Database/Table: query_cache
# Related Modules: app.services.query_router.cache
# Important Notes: Always filter by workspace_id — multi-tenant isolation.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.query import QueryCache


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
