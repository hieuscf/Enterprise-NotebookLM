# =============================================================================
# File: cache.py
# Module/Service: Query Router — Query Cache (FR11)
# Layer: Service
# Purpose: Exact hash + semantic Qdrant cache lookup / write-back helpers (0 LLM).
# Responsibilities:
#   - Reuse Task-1 normalize_query; SHA-256 hash; exact then similarity lookup
#   - Update hit_count / last_used_at on hit; save_query_cache after pipeline
# Dependencies:
#   - QueryCacheRepository, QdrantStoreAdapter, EmbeddingProvider, RouterRules
# Public Exports:
#   - normalize_query, hash_query, build_normalized_query
#   - QueryCacheService, check_exact_cache, check_similarity_cache, save_query_cache
#   - serialize_citation_refs, citation_refs_from_stored
# Database/Table: query_cache; Qdrant kind=query_cache
# Related Modules: router, cache_writer, embedding_provider
# Important Notes:
#   - Exact check always before semantic; never Retrieval / LLM on hit.
#   - Similarity uses per-entry similarity_threshold only (no global override).
# =============================================================================

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping, Sequence
from uuid import UUID

from app.adapters.qdrant_store import QdrantStoreAdapter
from app.config.router_rules import QDRANT_QUERY_CACHE_KIND, RouterRules
from app.core.config import Settings
from app.core.logging import get_logger
from app.models.query import QueryCache
from app.repositories.query_cache import QueryCacheRepository, QueryCacheRepositoryError
from app.services.query_router.embedding_provider import EmbeddingProvider
from app.services.query_router.normalizer import normalize_query as normalize_query
from app.services.query_router.schemas import CacheEntryView, CitationRef, NormalizedQuery

logger = get_logger(__name__)


def hash_query(normalized: str) -> str:
    """SHA-256 hex digest of the normalized query (deterministic)."""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def build_normalized_query(query_text: str) -> NormalizedQuery:
    """Build ``NormalizedQuery`` from raw text."""
    original = query_text or ""
    normalized = normalize_query(original)
    return NormalizedQuery(
        original=original,
        normalized=normalized,
        query_hash=hash_query(normalized),
    )


def cache_to_view(
    row: QueryCache,
    *,
    match_type: str,
    similarity: float | None = None,
) -> CacheEntryView:
    """Map ORM ``QueryCache`` to ``CacheEntryView``."""
    return CacheEntryView(
        id=row.id,
        workspace_id=row.workspace_id,
        query_hash=row.query_hash,
        query_text=row.query_text,
        answer=row.answer,
        citation_refs=row.citation_refs,
        similarity_threshold=row.similarity_threshold,
        hit_count=row.hit_count,
        expires_at=row.expires_at,
        last_used_at=row.last_used_at,
        match_type=match_type,
        similarity=similarity,
    )


def serialize_citation_refs(
    citation_refs: Sequence[CitationRef | Mapping[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    """Convert citation objects/dicts to JSONB-safe list of dicts."""
    if citation_refs is None:
        return None
    out: list[dict[str, Any]] = []
    for item in citation_refs:
        if isinstance(item, CitationRef):
            payload: dict[str, Any] = {
                "chunk_id": str(item.chunk_id) if item.chunk_id else None,
                "document_id": str(item.document_id) if item.document_id else None,
                "page_number": item.page_number,
                "verify": bool(item.verify),
            }
            if item.text_snippet:
                payload["text_snippet"] = item.text_snippet
            out.append(payload)
            continue
        if isinstance(item, Mapping):
            chunk_id = item.get("chunk_id")
            document_id = item.get("document_id")
            page_number = item.get("page_number")
            verify = item.get("verify", True)
            snippet = item.get("text_snippet")
            payload = {
                "chunk_id": str(chunk_id) if chunk_id is not None else None,
                "document_id": str(document_id) if document_id is not None else None,
                "page_number": int(page_number) if page_number is not None else None,
                "verify": bool(verify),
            }
            if snippet:
                payload["text_snippet"] = str(snippet)
            out.append(payload)
            continue
        raise TypeError(f"Unsupported citation_refs element type: {type(item)!r}")
    return out


def citation_refs_from_stored(
    raw: Sequence[Any] | Mapping[str, Any] | None,
) -> list[CitationRef]:
    """Rebuild ``CitationRef`` list from ``query_cache.citation_refs`` JSONB."""
    if raw is None:
        return []
    items: Sequence[Any]
    if isinstance(raw, Mapping):
        items = [raw]
    else:
        items = raw
    out: list[CitationRef] = []
    for item in items:
        if isinstance(item, CitationRef):
            out.append(item)
            continue
        if not isinstance(item, Mapping):
            continue
        chunk_raw = item.get("chunk_id")
        doc_raw = item.get("document_id")
        page_raw = item.get("page_number")
        snippet = item.get("text_snippet")
        try:
            chunk_id = UUID(str(chunk_raw)) if chunk_raw else None
        except (ValueError, TypeError):
            chunk_id = None
        try:
            document_id = UUID(str(doc_raw)) if doc_raw else None
        except (ValueError, TypeError):
            document_id = None
        page_number = int(page_raw) if page_raw is not None else None
        out.append(
            CitationRef(
                chunk_id=chunk_id,
                document_id=document_id,
                page_number=page_number,
                verify=bool(item.get("verify", True)),
                text_snippet=str(snippet) if snippet else None,
            )
        )
    return out


class QueryCacheService:
    """Exact + semantic query cache for the Query Router (Task 2)."""

    def __init__(
        self,
        *,
        settings: Settings,
        rules: RouterRules,
        repo: QueryCacheRepository,
        qdrant: QdrantStoreAdapter,
        embedding: EmbeddingProvider,
    ) -> None:
        self._settings = settings
        self._rules = rules
        self._repo = repo
        self._qdrant = qdrant
        self._embedding = embedding

    # ------------------------------------------------------------------
    # Public Task-2 API
    # ------------------------------------------------------------------

    async def check_exact_cache(
        self,
        *,
        workspace_id: UUID,
        query_hash: str,
    ) -> CacheEntryView | None:
        """Exact ``query_hash`` lookup; records hit on success (0 embedding)."""
        row = await self._repo.get_exact(
            workspace_id=workspace_id,
            query_hash=query_hash,
        )
        if row is None:
            logger.info(
                "query_cache_exact_miss",
                workspace_id=str(workspace_id),
                query_hash=query_hash,
            )
            return None
        row = await self._repo.record_hit(row)
        logger.info(
            "query_cache_exact_hit",
            workspace_id=str(workspace_id),
            query_hash=query_hash,
            cache_id=str(row.id),
            hit_count=row.hit_count,
        )
        return cache_to_view(row, match_type="exact", similarity=1.0)

    async def check_similarity_cache(
        self,
        *,
        workspace_id: UUID,
        normalized_text: str,
        query_vector: list[float] | None = None,
    ) -> tuple[CacheEntryView | None, list[float], float | None]:
        """Semantic cache via Qdrant Top-K + per-entry ``similarity_threshold``.

        Args:
            workspace_id: Tenant scope.
            normalized_text: Used to embed when ``query_vector`` is None.
            query_vector: Optional precomputed embedding (avoid double embed).

        Returns:
            ``(cache_view|None, vector_used, best_candidate_similarity|None)``.
        """
        vector = query_vector
        if vector is None:
            vector = await self._embed(normalized_text)
        if not vector:
            return None, [], None

        top_k = max(1, int(self._settings.query_cache_semantic_top_k))
        hits = await asyncio.to_thread(
            lambda: self._qdrant.search_similar(
                workspace_id=workspace_id,
                query_vector=vector,
                top_k=top_k,
                kind=self._rules.query_cache_kind,
            )
        )
        if not hits:
            logger.info(
                "query_cache_semantic_miss",
                workspace_id=str(workspace_id),
                reason="no_vector_hits",
            )
            return None, vector, None

        best_similarity: float | None = None
        cache_ids: list[UUID] = []
        score_by_id: dict[UUID, float] = {}
        for hit in hits:
            similarity = float(hit.get("score") or 0.0)
            if best_similarity is None:
                best_similarity = similarity
            raw_cache_id = hit.get("cache_id") or (hit.get("payload") or {}).get("cache_id")
            if not raw_cache_id:
                continue
            try:
                cache_id = UUID(str(raw_cache_id))
            except (ValueError, TypeError):
                continue
            cache_ids.append(cache_id)
            score_by_id[cache_id] = similarity

        if not cache_ids:
            logger.info(
                "query_cache_semantic_miss",
                workspace_id=str(workspace_id),
                reason="missing_cache_id",
                best_similarity=best_similarity,
            )
            return None, vector, best_similarity

        rows = await self._repo.get_similar(
            workspace_id=workspace_id,
            cache_ids=cache_ids,
        )
        for row in rows:
            similarity = score_by_id.get(row.id)
            if similarity is None:
                continue
            threshold = float(row.similarity_threshold)
            if similarity < threshold:
                logger.info(
                    "query_cache_semantic_below_threshold",
                    workspace_id=str(workspace_id),
                    cache_id=str(row.id),
                    similarity=similarity,
                    threshold=threshold,
                )
                continue
            row = await self._repo.record_hit(row)
            logger.info(
                "query_cache_semantic_hit",
                workspace_id=str(workspace_id),
                cache_id=str(row.id),
                similarity=similarity,
                threshold=threshold,
                hit_count=row.hit_count,
            )
            return (
                cache_to_view(row, match_type="semantic", similarity=similarity),
                vector,
                similarity,
            )

        logger.info(
            "query_cache_semantic_miss",
            workspace_id=str(workspace_id),
            reason="below_threshold_or_expired",
            best_similarity=best_similarity,
            candidates=len(cache_ids),
        )
        return None, vector, best_similarity

    async def save_query_cache(
        self,
        *,
        workspace_id: UUID,
        query_text: str,
        answer: str,
        citation_refs: Sequence[CitationRef | Mapping[str, Any]] | None,
        ttl_seconds: int,
        similarity_threshold: float | None = None,
        query_embedding_id: UUID | None = None,
        query_vector: list[float] | None = None,
        now: datetime | None = None,
    ) -> QueryCache:
        """Persist a cache entry after the downstream pipeline produces an answer.

        Does **not** write on lookup miss — only after answer generation.
        Upserts the query vector into Qdrant (``kind=query_cache``) when a
        vector is available so future semantic lookups can hit.

        Args:
            workspace_id: Tenant scope.
            query_text: Raw user query (normalized + hashed here).
            answer: Final answer text (must be non-empty).
            citation_refs: Citations to store as JSONB.
            ttl_seconds: Positive TTL used for ``expires_at = now + ttl``.
            similarity_threshold: Per-entry threshold; default from Settings.
            query_embedding_id: Optional FK to ``embeddings``.
            query_vector: Optional precomputed embedding; else embed normalized.
            now: Optional clock for deterministic tests.

        Returns:
            Inserted ``QueryCache`` row.

        Raises:
            ValueError: Empty answer or non-positive TTL.
            QueryCacheRepositoryError: Persistence failure.
        """
        if not (answer or "").strip():
            raise ValueError("answer must not be empty")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")

        nq = build_normalized_query(query_text)
        ts = now or datetime.now(UTC)
        expires_at = ts + timedelta(seconds=int(ttl_seconds))
        threshold = (
            float(similarity_threshold)
            if similarity_threshold is not None
            else float(self._settings.query_cache_similarity_threshold)
        )
        refs_json = serialize_citation_refs(citation_refs)

        try:
            row = await self._repo.save(
                workspace_id=workspace_id,
                query_hash=nq.query_hash,
                query_text=nq.normalized,
                answer=answer,
                citation_refs=refs_json,
                ttl_seconds=int(ttl_seconds),
                expires_at=expires_at,
                similarity_threshold=threshold,
                query_embedding_id=query_embedding_id,
                hit_count=0,
                last_used_at=None,
                now=ts,
            )
        except QueryCacheRepositoryError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise QueryCacheRepositoryError(
                f"Failed to save query_cache: {exc}"
            ) from exc

        vector = query_vector
        if vector is None:
            vector = await self._embed(nq.normalized)
        if vector:
            await self._upsert_cache_vector(
                workspace_id=workspace_id,
                cache_id=row.id,
                vector=vector,
            )

        logger.info(
            "query_cache_saved",
            workspace_id=str(workspace_id),
            cache_id=str(row.id),
            query_hash=nq.query_hash,
            ttl_seconds=ttl_seconds,
            expires_at=expires_at.isoformat(),
            vector_upserted=bool(vector),
        )
        return row

    # ------------------------------------------------------------------
    # Backward-compatible names used by QueryRouter
    # ------------------------------------------------------------------

    async def check_exact(
        self,
        *,
        workspace_id: UUID,
        query_hash: str,
    ) -> CacheEntryView | None:
        """Alias for ``check_exact_cache`` (router compatibility)."""
        return await self.check_exact_cache(
            workspace_id=workspace_id,
            query_hash=query_hash,
        )

    async def check_semantic(
        self,
        *,
        workspace_id: UUID,
        normalized_text: str,
        query_vector: list[float] | None = None,
    ) -> tuple[CacheEntryView | None, list[float], float | None]:
        """Alias for ``check_similarity_cache`` (router compatibility)."""
        return await self.check_similarity_cache(
            workspace_id=workspace_id,
            normalized_text=normalized_text,
            query_vector=query_vector,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _embed(self, text: str) -> list[float]:
        """Embed via Task-1 ``EmbeddingProvider`` (no hard-coded model)."""

        def _run() -> list[float]:
            matrix = self._embedding.embed([text])
            if matrix.size == 0:
                return []
            return [float(x) for x in matrix[0].tolist()]

        return await asyncio.to_thread(_run)

    async def _upsert_cache_vector(
        self,
        *,
        workspace_id: UUID,
        cache_id: UUID,
        vector: list[float],
    ) -> None:
        """Store query vector in Qdrant for semantic reuse."""

        def _run() -> None:
            self._qdrant.upsert_chunk_vector(
                point_id=str(cache_id),
                vector=vector,
                payload={
                    "workspace_id": str(workspace_id),
                    "cache_id": str(cache_id),
                    "kind": self._rules.query_cache_kind or QDRANT_QUERY_CACHE_KIND,
                },
            )

        await asyncio.to_thread(_run)


# Module-level helpers matching Task-2 naming (thin wrappers for call sites).


async def check_exact_cache(
    *,
    service: QueryCacheService,
    workspace_id: UUID,
    query_hash: str,
) -> CacheEntryView | None:
    """Module helper — prefer injecting ``QueryCacheService`` in DI."""
    return await service.check_exact_cache(
        workspace_id=workspace_id,
        query_hash=query_hash,
    )


async def check_similarity_cache(
    *,
    service: QueryCacheService,
    workspace_id: UUID,
    normalized_text: str,
    query_vector: list[float] | None = None,
) -> tuple[CacheEntryView | None, list[float], float | None]:
    """Module helper — prefer injecting ``QueryCacheService`` in DI."""
    return await service.check_similarity_cache(
        workspace_id=workspace_id,
        normalized_text=normalized_text,
        query_vector=query_vector,
    )


async def save_query_cache(
    *,
    service: QueryCacheService,
    workspace_id: UUID,
    query_text: str,
    answer: str,
    citation_refs: Sequence[CitationRef | Mapping[str, Any]] | None,
    ttl_seconds: int,
    similarity_threshold: float | None = None,
    query_embedding_id: UUID | None = None,
    query_vector: list[float] | None = None,
    now: datetime | None = None,
) -> QueryCache:
    """Module helper — prefer injecting ``QueryCacheService`` in DI."""
    return await service.save_query_cache(
        workspace_id=workspace_id,
        query_text=query_text,
        answer=answer,
        citation_refs=citation_refs,
        ttl_seconds=ttl_seconds,
        similarity_threshold=similarity_threshold,
        query_embedding_id=query_embedding_id,
        query_vector=query_vector,
        now=now,
    )
