# =============================================================================
# File: bm25_search.py
# Module/Service: Search Service / Hybrid Retrieval — BM25 branch
# Layer: Service
# Purpose: Keyword / full-text search via Elasticsearch BM25 (FR3).
# Responsibilities:
#   - Phrase + keyword + fuzzy BM25 query filtered by workspace_id
#   - Hydrate document_id from Postgres when missing from ES payload
# Dependencies:
#   - app.adapters.elasticsearch_bm25, app.repositories.retrieval
# Public Exports:
#   - Bm25Search
# Database/Table: document_chunks (hydration); ES index document_chunks
# Related Modules: HybridRetrievalService
# Important Notes: 0 LLM / 0 embedding. No cross-workspace leakage.
# =============================================================================

from __future__ import annotations

import asyncio
from uuid import UUID

from app.adapters.elasticsearch_bm25 import ElasticsearchBm25Adapter
from app.core.config import Settings
from app.core.logging import get_logger
from app.repositories.retrieval import RetrievalRepository
from app.services.retrieval.schemas import RetrievalCandidate

logger = get_logger(__name__)


class Bm25Search:
    """Full-text BM25 search over the shared Elasticsearch index."""

    def __init__(
        self,
        *,
        settings: Settings,
        elasticsearch: ElasticsearchBm25Adapter,
        repo: RetrievalRepository | None = None,
    ) -> None:
        self._settings = settings
        self._es = elasticsearch
        self._repo = repo

    async def search(
        self,
        workspace_id: UUID,
        query_text: str,
        top_k: int = 20,
    ) -> list[RetrievalCandidate]:
        """Run BM25 search scoped to ``workspace_id``.

        Args:
            workspace_id: Tenant scope.
            query_text: Keyword / natural-language query.
            top_k: Max hits from Elasticsearch.

        Returns:
            Candidates with ``retrieval_method=bm25``.
        """
        hits = await asyncio.to_thread(
            self._es.search,
            workspace_id=workspace_id,
            query_text=query_text,
            top_k=top_k,
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
            content = (hit.get("content") or "")[:max_chars]
            document_id = None
            page_number = None
            section_index = None
            section_title = None
            document_title = None
            if row is not None:
                content = (row.content or content)[:max_chars]
                document_id = row.document_id
                page_number = row.page_number
                section_index = row.section_index
                section_title = row.section
                document_title = row.title
            else:
                raw_doc = hit.get("document_id")
                if raw_doc:
                    try:
                        document_id = UUID(str(raw_doc))
                    except (ValueError, TypeError):
                        document_id = None
                elif self._repo is not None and hit.get("document_version_id"):
                    try:
                        vid = UUID(str(hit["document_version_id"]))
                        document_id = await self._repo.document_id_for_version(
                            workspace_id, vid
                        )
                    except (ValueError, TypeError):
                        document_id = None

            candidates.append(
                RetrievalCandidate(
                    workspace_id=workspace_id,
                    chunk_id=cid,
                    document_id=document_id,
                    text_snippet=content,
                    raw_score=float(hit.get("score") or 0.0),
                    retrieval_method="bm25",
                    source_methods=["bm25"],
                    page_number=page_number,
                    section_index=section_index,
                    section_title=section_title,
                    document_title=document_title,
                )
            )
        return candidates
