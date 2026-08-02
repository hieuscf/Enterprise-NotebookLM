# =============================================================================
# File: lightweight_retriever.py
# Module/Service: Query Router — Simple Factoid (FR11)
# Layer: Adapter
# Purpose: Retriever adapter over VectorSearch only (no hybrid / BM25 / graph / rerank).
# Responsibilities:
#   - Map VectorSearch hits → RetrievedChunk for FactoidHandler
# Dependencies:
#   - VectorSearch, Retriever Protocol
# Public Exports:
#   - LightweightVectorRetriever
# Database/Table: N/A (via VectorSearch hydration)
# Related Modules: handlers.factoid_handler
# Important Notes: 0 LLM; FactoidHandler depends only on Retriever Protocol.
# =============================================================================

from __future__ import annotations

from uuid import UUID

from app.services.query_router.interfaces.retriever import RetrievedChunk
from app.services.retrieval.vector_search import VectorSearch


class LightweightVectorRetriever:
    """Top-K vector-only retriever for Simple Factoid."""

    def __init__(self, vector_search: VectorSearch) -> None:
        self._vector = vector_search

    async def retrieve(
        self,
        query: str,
        top_k: int,
        *,
        workspace_id: UUID,
    ) -> list[RetrievedChunk]:
        hits = await self._vector.search(
            workspace_id,
            query,
            top_k=max(1, top_k),
        )
        out: list[RetrievedChunk] = []
        for hit in hits:
            score = float(hit.score if hit.score is not None else hit.raw_score or 0.0)
            out.append(
                RetrievedChunk(
                    chunk_id=hit.chunk_id,
                    document_id=hit.document_id,
                    text=hit.text_snippet or "",
                    score=score,
                    page_number=hit.page_number,
                )
            )
        return out
