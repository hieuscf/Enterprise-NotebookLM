# =============================================================================
# File: hybrid_retrieval_service.py
# Module/Service: Search Service / Hybrid Retrieval
# Layer: Service
# Purpose: Sole system-wide Hybrid Retrieval orchestrator (FR3).
# Responsibilities:
#   - Embed query once; fan-out Vector/BM25/Graph in parallel with per-source timeouts
#   - Merge + dedupe; cap candidates; cross-encoder rerank; return top_k
# Dependencies:
#   - vector_search, bm25_search, graph_search, reranker, embedding, Settings
# Public Exports:
#   - HybridRetrievalService
# Database/Table: N/A (delegates to adapters/repos)
# Related Modules: Search API, Query Router, Chat Service, Citation Service
# Important Notes:
#   - 0 LLM. Do not duplicate this logic elsewhere.
#   - Partial source failure is tolerated; all-fail → RetrievalUnavailableError.
# =============================================================================

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import UUID

from app.ai.embedding import embed_texts_batch
from app.core.config import Settings
from app.core.logging import get_logger
from app.services.retrieval.bm25_search import Bm25Search
from app.services.retrieval.exceptions import RetrievalUnavailableError
from app.services.retrieval.graph_search import GraphSearch
from app.services.retrieval.reranker import Reranker
from app.services.retrieval.schemas import RetrievalCandidate, RetrievalResult
from app.services.retrieval.vector_search import VectorSearch

logger = get_logger(__name__)

T = TypeVar("T")


class HybridRetrievalService:
    """Shared Hybrid Retrieval: Vector + BM25 + Knowledge Graph → Rerank."""

    def __init__(
        self,
        *,
        settings: Settings,
        vector_search: VectorSearch,
        bm25_search: Bm25Search,
        graph_search: GraphSearch,
        reranker: Reranker,
    ) -> None:
        self._settings = settings
        self._vector = vector_search
        self._bm25 = bm25_search
        self._graph = graph_search
        self._reranker = reranker

    async def retrieve(
        self,
        workspace_id: UUID,
        query_text: str,
        top_k: int = 10,
    ) -> RetrievalResult:
        """Run the Hybrid Retrieval pipeline for one workspace query.

        Args:
            workspace_id: Tenant scope (RBAC enforced by callers).
            query_text: User search / chat query.
            top_k: Number of final ranked results.

        Returns:
            ``RetrievalResult`` with reranked items and per-source timings.

        Raises:
            RetrievalUnavailableError: If Vector, BM25, and Graph all fail.
        """
        started = time.perf_counter()
        q = (query_text or "").strip()
        per_source = self._settings.retrieval_per_source_top_k
        max_rerank = self._settings.retrieval_max_rerank_candidates

        query_vector = await self._embed_once(q) if q else []

        vector_task = self._timed_source(
            "vector",
            self._settings.retrieval_vector_timeout_seconds,
            lambda: self._vector.search(
                workspace_id,
                q,
                per_source,
                query_vector=query_vector or None,
            ),
        )
        bm25_task = self._timed_source(
            "bm25",
            self._settings.retrieval_bm25_timeout_seconds,
            lambda: self._bm25.search(workspace_id, q, per_source),
        )
        graph_task = self._timed_source(
            "graph",
            self._settings.retrieval_graph_timeout_seconds,
            lambda: self._graph.search(workspace_id, q, per_source),
        )

        (vector_items, vector_ms, vector_ok), (bm25_items, bm25_ms, bm25_ok), (
            graph_items,
            graph_ms,
            graph_ok,
        ) = await asyncio.gather(vector_task, bm25_task, graph_task)

        sources_used: list[str] = []
        if vector_ok:
            sources_used.append("vector")
        if bm25_ok:
            sources_used.append("bm25")
        if graph_ok:
            sources_used.append("graph")

        if not sources_used:
            logger.error(
                "retrieval_all_sources_failed",
                workspace_id=str(workspace_id),
                query=q[:200],
            )
            raise RetrievalUnavailableError(
                "Vector, BM25, and Knowledge Graph retrieval all failed"
            )

        merged = _merge_dedupe(
            [
                *(vector_items or []),
                *(bm25_items or []),
                *(graph_items or []),
            ]
        )
        candidate_count = len(merged)
        capped = merged[:max_rerank]

        rerank_started = time.perf_counter()
        ranked = await self._reranker.rerank(q, capped)
        rerank_ms = int((time.perf_counter() - rerank_started) * 1000)

        final = ranked[: max(1, top_k)]
        for i, item in enumerate(final, start=1):
            item.rank = i

        total_ms = int((time.perf_counter() - started) * 1000)
        timings: dict[str, int | None] = {
            "vector_ms": vector_ms,
            "bm25_ms": bm25_ms,
            "graph_ms": graph_ms,
            "rerank_ms": rerank_ms,
            "total_ms": total_ms,
        }

        logger.info(
            "hybrid_retrieval_completed",
            workspace_id=str(workspace_id),
            query=q[:200],
            vector_latency=vector_ms,
            bm25_latency=bm25_ms,
            graph_latency=graph_ms,
            rerank_latency=rerank_ms,
            total_latency=total_ms,
            candidate_count=candidate_count,
            final_count=len(final),
            sources_used=sources_used,
        )

        return RetrievalResult(
            items=final,
            latency_ms=total_ms,
            sources_used=sources_used,
            timings=timings,
        )

    async def _embed_once(self, query_text: str) -> list[float]:
        """Produce a single query embedding (shared by Vector Search)."""
        settings = self._settings

        def _run() -> list[float]:
            vectors = embed_texts_batch(
                [query_text],
                model_name=settings.embedding_model_name,
                dimension=settings.embedding_dimension,
                provider=settings.embedding_provider,
                api_key=settings.embedding_api_key,
                batch_size=1,
            )
            return list(vectors[0].values) if vectors else []

        return await asyncio.to_thread(_run)

    async def _timed_source(
        self,
        name: str,
        timeout_seconds: float,
        factory: Callable[[], Awaitable[list[RetrievalCandidate]]],
    ) -> tuple[list[RetrievalCandidate] | None, int | None, bool]:
        """Run one source with timeout; return (items|None, latency_ms|None, ok)."""
        started = time.perf_counter()
        try:
            items = await asyncio.wait_for(factory(), timeout=timeout_seconds)
            latency = int((time.perf_counter() - started) * 1000)
            return items, latency, True
        except TimeoutError:
            latency = int((time.perf_counter() - started) * 1000)
            logger.warning(
                "retrieval_source_timeout",
                source=name,
                timeout_seconds=timeout_seconds,
                latency_ms=latency,
            )
            return None, latency, False
        except Exception as exc:  # noqa: BLE001 — isolate source failures
            latency = int((time.perf_counter() - started) * 1000)
            logger.warning(
                "retrieval_source_error",
                source=name,
                error=str(exc),
                latency_ms=latency,
            )
            return None, latency, False


def _merge_dedupe(candidates: list[RetrievalCandidate]) -> list[RetrievalCandidate]:
    """Deduplicate by chunk_id (preferred) or entity_id; keep highest raw_score."""
    best: dict[str, RetrievalCandidate] = {}
    for cand in candidates:
        if cand.chunk_id is not None:
            key = f"chunk:{cand.chunk_id}"
        elif cand.entity_id is not None:
            key = f"entity:{cand.entity_id}"
        else:
            key = f"doc:{cand.document_id}:{hash(cand.text_snippet)}"
        existing = best.get(key)
        if existing is None:
            best[key] = RetrievalCandidate(
                workspace_id=cand.workspace_id,
                text_snippet=cand.text_snippet,
                retrieval_method=cand.retrieval_method,
                raw_score=cand.raw_score,
                document_id=cand.document_id,
                chunk_id=cand.chunk_id,
                entity_id=cand.entity_id,
                score=cand.score,
                rank=cand.rank,
                source_methods=list(cand.source_methods) or [cand.retrieval_method],
                page_number=cand.page_number,
                section_index=cand.section_index,
                section_title=cand.section_title,
                document_title=cand.document_title,
            )
            continue
        methods = list(
            dict.fromkeys(
                (existing.source_methods or [existing.retrieval_method])
                + (cand.source_methods or [cand.retrieval_method])
            )
        )
        if cand.raw_score > existing.raw_score:
            best[key] = RetrievalCandidate(
                workspace_id=cand.workspace_id,
                text_snippet=cand.text_snippet or existing.text_snippet,
                retrieval_method=cand.retrieval_method,
                raw_score=cand.raw_score,
                document_id=cand.document_id or existing.document_id,
                chunk_id=cand.chunk_id or existing.chunk_id,
                entity_id=cand.entity_id or existing.entity_id,
                score=None,
                rank=None,
                source_methods=methods,
                page_number=cand.page_number
                if cand.page_number is not None
                else existing.page_number,
                section_index=cand.section_index
                if cand.section_index is not None
                else existing.section_index,
                section_title=cand.section_title or existing.section_title,
                document_title=cand.document_title or existing.document_title,
            )
        else:
            existing.source_methods = methods
            if not existing.text_snippet and cand.text_snippet:
                existing.text_snippet = cand.text_snippet
            if existing.document_id is None and cand.document_id is not None:
                existing.document_id = cand.document_id
            if existing.entity_id is None and cand.entity_id is not None:
                existing.entity_id = cand.entity_id
            if existing.page_number is None and cand.page_number is not None:
                existing.page_number = cand.page_number
            if existing.section_index is None and cand.section_index is not None:
                existing.section_index = cand.section_index
            if not existing.section_title and cand.section_title:
                existing.section_title = cand.section_title
            if not existing.document_title and cand.document_title:
                existing.document_title = cand.document_title

    merged = list(best.values())
    merged.sort(key=lambda c: c.raw_score, reverse=True)
    return merged
