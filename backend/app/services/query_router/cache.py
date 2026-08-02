# =============================================================================
# File: cache.py
# Module/Service: Query Router — Cache Check (FR11)
# Layer: Service
# Purpose: Exact hash + semantic vector cache lookup (0 LLM).
# Responsibilities:
#   - Normalize/hash helpers; exact Postgres match; semantic Qdrant match
#   - Record hit_count / last_used_at on hit
# Dependencies:
#   - QueryCacheRepository, QdrantStoreAdapter, embed_texts_batch, RouterRules
# Public Exports:
#   - normalize_query, hash_query, QueryCacheService
# Database/Table: query_cache; Qdrant kind=query_cache
# Related Modules: app.services.query_router.router, app.config.router_rules
# Important Notes: Exact check always before semantic; workspace-scoped only.
# =============================================================================

from __future__ import annotations

import asyncio
import hashlib
from uuid import UUID

from app.adapters.qdrant_store import QdrantStoreAdapter
from app.ai.embedding import embed_texts_batch
from app.config.router_rules import RouterRules
from app.core.config import Settings
from app.core.logging import get_logger
from app.models.query import QueryCache
from app.repositories.query_cache import QueryCacheRepository
from app.services.query_router.normalizer import normalize_query as normalize_query
from app.services.query_router.schemas import CacheEntryView, NormalizedQuery

logger = get_logger(__name__)

def hash_query(normalized: str) -> str:
    """SHA-256 hex digest of the normalized query."""
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


class QueryCacheService:
    """Exact + semantic query cache checks for the Query Router."""

    def __init__(
        self,
        *,
        settings: Settings,
        rules: RouterRules,
        repo: QueryCacheRepository,
        qdrant: QdrantStoreAdapter,
    ) -> None:
        self._settings = settings
        self._rules = rules
        self._repo = repo
        self._qdrant = qdrant

    async def check_exact(
        self,
        *,
        workspace_id: UUID,
        query_hash: str,
    ) -> CacheEntryView | None:
        """Exact ``query_hash`` lookup; records hit on success."""
        row = await self._repo.find_exact_hit(
            workspace_id=workspace_id,
            query_hash=query_hash,
        )
        if row is None:
            return None
        row = await self._repo.record_hit(row)
        return cache_to_view(row, match_type="exact", similarity=1.0)

    async def check_semantic(
        self,
        *,
        workspace_id: UUID,
        normalized_text: str,
        query_vector: list[float] | None = None,
    ) -> tuple[CacheEntryView | None, list[float], float | None]:
        """Semantic cache via Qdrant ``kind=query_cache``.

        Args:
            workspace_id: Tenant scope.
            normalized_text: Used to embed when ``query_vector`` is None.
            query_vector: Optional precomputed embedding (avoid double embed).

        Returns:
            Tuple of ``(cache_view|None, vector_used, best_similarity|None)``.
        """
        vector = query_vector
        if vector is None:
            vector = await self._embed(normalized_text)
        if not vector:
            return None, [], None

        hits = await asyncio.to_thread(
            lambda: self._qdrant.search_similar(
                workspace_id=workspace_id,
                query_vector=vector,
                top_k=1,
                kind=self._rules.query_cache_kind,
            )
        )
        if not hits:
            return None, vector, None

        best = hits[0]
        similarity = float(best.get("score") or 0.0)
        raw_cache_id = best.get("cache_id") or (best.get("payload") or {}).get("cache_id")
        if not raw_cache_id:
            logger.info(
                "semantic_cache_hit_missing_cache_id",
                workspace_id=str(workspace_id),
                similarity=similarity,
            )
            return None, vector, similarity

        try:
            cache_id = UUID(str(raw_cache_id))
        except (ValueError, TypeError):
            return None, vector, similarity

        row = await self._repo.get_by_id(workspace_id=workspace_id, cache_id=cache_id)
        if row is None:
            return None, vector, similarity

        # Prefer per-entry threshold when set; else global rules threshold.
        effective = (
            float(row.similarity_threshold)
            if row.similarity_threshold is not None and row.similarity_threshold > 0
            else float(self._rules.similarity_threshold)
        )
        if similarity < effective:
            return None, vector, similarity

        row = await self._repo.record_hit(row)
        return (
            cache_to_view(row, match_type="semantic", similarity=similarity),
            vector,
            similarity,
        )

    async def _embed(self, text: str) -> list[float]:
        settings = self._settings

        def _run() -> list[float]:
            vectors = embed_texts_batch(
                [text],
                model_name=settings.embedding_model_name,
                dimension=settings.embedding_dimension,
                provider=settings.embedding_provider,
                api_key=settings.embedding_api_key,
                batch_size=1,
            )
            return list(vectors[0].values) if vectors else []

        return await asyncio.to_thread(_run)
