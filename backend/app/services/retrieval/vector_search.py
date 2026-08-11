# =============================================================================
# File: vector_search.py
# Module/Service: Search Service / Hybrid Retrieval — Vector branch
# Layer: Service
# Purpose: Semantic (dense) search via embedding + Qdrant (FR3).
# Responsibilities:
#   - Embed query when vector not supplied; query shared Qdrant collection
#   - Hydrate text_snippet / document_id from Postgres (workspace-scoped)
# Dependencies:
#   - app.adapters.qdrant_store, app.ai.embedding, app.repositories.retrieval
# Public Exports:
#   - VectorSearch
# Database/Table: document_chunks, document_versions, documents (hydration only)
# Related Modules: HybridRetrievalService
# Important Notes: 0 LLM. Prefer passing query_vector to avoid re-embedding.
# =============================================================================

from __future__ import annotations

import asyncio
from uuid import UUID

from app.adapters.qdrant_store import QdrantStoreAdapter
from app.ai.embedding import embed_texts_batch
from app.core.config import Settings
from app.core.logging import get_logger
from app.repositories.retrieval import RetrievalRepository
from app.services.retrieval.schemas import RetrievalCandidate

logger = get_logger(__name__)


class VectorSearch:
    """Semantic search over the shared Qdrant chunk collection."""

    def __init__(
        self,
        *,
        settings: Settings,
        qdrant: QdrantStoreAdapter,
        repo: RetrievalRepository | None = None,
    ) -> None:
        self._settings = settings
        self._qdrant = qdrant
        self._repo = repo

    async def search(
        self,
        workspace_id: UUID,
        query_text: str,
        top_k: int = 20,
        *,
        query_vector: list[float] | None = None,
    ) -> list[RetrievalCandidate]:
        """Run vector similarity search scoped to ``workspace_id``.

        Args:
            workspace_id: Tenant scope.
            query_text: Natural-language query (used if ``query_vector`` is None).
            top_k: Max hits from Qdrant.
            query_vector: Precomputed embedding — preferred to avoid duplicate embeds.

        Returns:
            Candidates with ``retrieval_method=vector``.
        """
        vector = query_vector
        if vector is None:
            vector = await self._embed_query(query_text)
        if not vector:
            return []

        hits = await asyncio.to_thread(
            self._qdrant.search_similar,
            workspace_id=workspace_id,
            query_vector=vector,
            top_k=top_k,
            kind="chunk",
        )
        if not hits:
            return []

        chunk_ids: list[UUID] = []
        for hit in hits:
            try:
                chunk_ids.append(UUID(str(hit["chunk_id"])))
            except (ValueError, TypeError, KeyError):
                continue

        hydrated = {}
        if self._repo is not None and chunk_ids:
            hydrated = await self._repo.hydrate_chunks(workspace_id, chunk_ids)

        max_chars = self._settings.retrieval_snippet_max_chars
        candidates: list[RetrievalCandidate] = []
        for hit in hits:
            try:
                cid = UUID(str(hit["chunk_id"]))
            except (ValueError, TypeError, KeyError):
                continue
            row = hydrated.get(cid)
            snippet = ""
            document_id = None
            page_number = None
            section_index = None
            section_title = None
            document_title = None
            heading_path = None
            chunk_index = None
            document_version_id = None
            if row is not None:
                snippet = (row.content or "")[:max_chars]
                document_id = row.document_id
                page_number = row.page_number
                section_index = row.section_index
                section_title = row.section
                document_title = row.title
                heading_path = row.heading_path
                chunk_index = row.chunk_index
                document_version_id = row.document_version_id
            else:
                payload = hit.get("payload") or {}
                snippet = str(payload.get("content") or payload.get("section") or "")[:max_chars]
                raw_doc = hit.get("document_id") or payload.get("document_id")
                if raw_doc:
                    try:
                        document_id = UUID(str(raw_doc))
                    except (ValueError, TypeError):
                        document_id = None

            candidates.append(
                RetrievalCandidate(
                    workspace_id=workspace_id,
                    chunk_id=cid,
                    document_id=document_id,
                    text_snippet=snippet,
                    raw_score=float(hit.get("score") or 0.0),
                    retrieval_method="vector",
                    source_methods=["vector"],
                    page_number=page_number,
                    section_index=section_index,
                    section_title=section_title,
                    document_title=document_title,
                    heading_path=heading_path,
                    chunk_index=chunk_index,
                    document_version_id=document_version_id,
                )
            )
        return candidates

    async def _embed_query(self, query_text: str) -> list[float]:
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
