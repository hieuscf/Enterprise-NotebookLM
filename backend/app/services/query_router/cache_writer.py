# =============================================================================
# File: cache_writer.py
# Module/Service: Query Router — Cache Write-back (FR11)
# Layer: Service
# Purpose: Persist verified answers into query_cache (Postgres row insert).
# Responsibilities:
#   - Reuse normalize/hash; apply caller TTL; insert via Repository.save
# Dependencies:
#   - QueryCacheRepository, Settings, cache.serialize_citation_refs
# Public Exports:
#   - QueryCacheWriter, write_cache, serialize_citation_refs
# Database/Table: query_cache
# Related Modules: QueryCacheService.save_query_cache (preferred when Qdrant upsert needed)
# Important Notes:
#   - Insert-only; does not overwrite existing rows.
#   - For semantic reuse prefer QueryCacheService.save_query_cache (upserts Qdrant).
# =============================================================================

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Mapping, Sequence
from uuid import UUID

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.models.query import QueryCache
from app.repositories.query_cache import QueryCacheRepository, QueryCacheRepositoryError
from app.services.query_router.cache import (
    build_normalized_query,
    serialize_citation_refs,
)
from app.services.query_router.schemas import CitationRef

logger = get_logger(__name__)


class QueryCacheWriter:
    """Postgres-only write-back API for ``query_cache``.

    Prefer ``QueryCacheService.save_query_cache`` when the caller also needs
    Qdrant vector upsert for semantic hits.
    """

    def __init__(
        self,
        *,
        repo: QueryCacheRepository,
        settings: Settings | None = None,
    ) -> None:
        self._repo = repo
        self._settings = settings or get_settings()

    async def write_cache(
        self,
        workspace_id: UUID,
        query_text: str,
        query_embedding_id: UUID | None,
        answer: str,
        citation_refs: Sequence[CitationRef | Mapping[str, Any]] | None,
        ttl_seconds: int | None = None,
        *,
        now: datetime | None = None,
    ) -> QueryCache:
        """Insert a new cache entry for ``workspace_id``.

        Args:
            workspace_id: Tenant scope — never write across workspaces.
            query_text: Raw user query (normalized via shared helpers).
            query_embedding_id: Optional embedding FK for semantic reuse.
            answer: Verified answer text to cache.
            citation_refs: Citations (``CitationRef`` or mapping).
            ttl_seconds: Override TTL; default from Settings.
            now: Optional clock for deterministic tests.

        Returns:
            Newly inserted ``QueryCache`` row.

        Raises:
            QueryCacheRepositoryError: When persistence fails.
            ValueError: When ``answer`` is empty or TTL is non-positive.
        """
        if not (answer or "").strip():
            raise ValueError("answer must not be empty")

        effective_ttl = (
            int(ttl_seconds)
            if ttl_seconds is not None
            else int(self._settings.query_cache_default_ttl_seconds)
        )
        if effective_ttl <= 0:
            raise ValueError("ttl_seconds must be positive")

        nq = build_normalized_query(query_text)
        ts = now or datetime.now(UTC)
        expires_at = ts + timedelta(seconds=effective_ttl)
        refs_json = serialize_citation_refs(citation_refs)

        try:
            row = await self._repo.save(
                workspace_id=workspace_id,
                query_hash=nq.query_hash,
                query_text=nq.normalized,
                answer=answer,
                citation_refs=refs_json,
                ttl_seconds=effective_ttl,
                expires_at=expires_at,
                similarity_threshold=float(
                    self._settings.query_cache_similarity_threshold
                ),
                query_embedding_id=query_embedding_id,
                hit_count=0,
                last_used_at=None,
                now=ts,
            )
        except QueryCacheRepositoryError:
            raise
        except Exception as exc:  # noqa: BLE001 — wrap unexpected repo failures
            raise QueryCacheRepositoryError(
                f"Failed to write query_cache: {exc}"
            ) from exc

        logger.info(
            "query_cache_written",
            workspace_id=str(workspace_id),
            query_hash=nq.query_hash,
            ttl_seconds=effective_ttl,
            expires_at=expires_at.isoformat(),
            cache_id=str(row.id),
        )
        return row


async def write_cache(
    workspace_id: UUID,
    query_text: str,
    query_embedding_id: UUID | None,
    answer: str,
    citation_refs: Sequence[CitationRef | Mapping[str, Any]] | None,
    ttl_seconds: int | None = None,
    *,
    repo: QueryCacheRepository,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> QueryCache:
    """Module-level write-back helper matching the public signature."""
    writer = QueryCacheWriter(repo=repo, settings=settings)
    return await writer.write_cache(
        workspace_id,
        query_text,
        query_embedding_id,
        answer,
        citation_refs,
        ttl_seconds,
        now=now,
    )
