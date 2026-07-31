# =============================================================================
# File: cache_writer.py
# Module/Service: Query Router — Cache Write-back (FR11)
# Layer: Service
# Purpose: Persist verified answers into query_cache for Complex branch (later).
# Responsibilities:
#   - Reuse Part 3 normalize_query / hash_query; apply Settings TTL; insert row
# Dependencies:
#   - QueryCacheRepository, Settings, CitationRef
# Public Exports:
#   - QueryCacheWriter, write_cache, serialize_citation_refs
# Database/Table: query_cache
# Related Modules: Chat Service Complex branch (consumer); QueryCacheService (reader)
# Important Notes:
#   - Not wired into Orchestrator in Part 5 — internal API only.
#   - Does not overwrite existing rows (insert-only; no merge strategy yet).
#   - Stores normalized query in query_text (schema has no normalized_query col).
# =============================================================================

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Mapping, Sequence
from uuid import UUID

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.models.query import QueryCache
from app.repositories.query_cache import QueryCacheRepository, QueryCacheRepositoryError
from app.services.query_router.cache import build_normalized_query
from app.services.query_router.schemas import CitationRef

logger = get_logger(__name__)


def serialize_citation_refs(
    citation_refs: Sequence[CitationRef | Mapping[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    """Convert citation objects/dicts to JSONB-safe list of dicts.

    Preserves ``chunk_id``, ``document_id``, ``page_number``, ``verify``.
    """
    if citation_refs is None:
        return None
    out: list[dict[str, Any]] = []
    for item in citation_refs:
        if isinstance(item, CitationRef):
            out.append(
                {
                    "chunk_id": str(item.chunk_id) if item.chunk_id else None,
                    "document_id": str(item.document_id) if item.document_id else None,
                    "page_number": item.page_number,
                    "verify": bool(item.verify),
                }
            )
            continue
        if isinstance(item, Mapping):
            chunk_id = item.get("chunk_id")
            document_id = item.get("document_id")
            page_number = item.get("page_number")
            verify = item.get("verify", True)
            out.append(
                {
                    "chunk_id": str(chunk_id) if chunk_id is not None else None,
                    "document_id": str(document_id) if document_id is not None else None,
                    "page_number": int(page_number) if page_number is not None else None,
                    "verify": bool(verify),
                }
            )
            continue
        raise TypeError(f"Unsupported citation_refs element type: {type(item)!r}")
    return out


class QueryCacheWriter:
    """Write-back API for ``query_cache`` (Complex branch consumer)."""

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
            query_text: Raw user query (normalized via Part 3 helpers).
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
            row = await self._repo.create(
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
    """Module-level write-back helper matching the Part 5 public signature.

    Prefer injecting ``QueryCacheWriter`` in production DI; this helper suits
    Chat Service call sites and unit tests.
    """
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
