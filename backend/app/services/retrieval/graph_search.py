# =============================================================================
# File: graph_search.py
# Module/Service: Search Service / Hybrid Retrieval — Knowledge Graph branch
# Layer: Service
# Purpose: Low-Level entity→chunk retrieval via Neo4j (FR3).
# Responsibilities:
#   - Match Entity by name/alias; follow MENTIONED_IN → Chunk
#   - Postgres fallback for chunks when Neo4j has entity-only nodes
# Dependencies:
#   - app.adapters.neo4j_graph, app.repositories.retrieval
# Public Exports:
#   - GraphSearch
# Database/Table: entities, document_chunks (fallback hydration)
# Related Modules: HybridRetrievalService, Neo4jGraphAdapter
# Important Notes: 0 LLM. Workspace filter on every Cypher / SQL path.
# =============================================================================

from __future__ import annotations

import asyncio
from uuid import UUID

from app.adapters.neo4j_graph import Neo4jGraphAdapter
from app.core.config import Settings
from app.core.logging import get_logger
from app.repositories.retrieval import RetrievalRepository
from app.services.retrieval.schemas import RetrievalCandidate

logger = get_logger(__name__)


class GraphSearch:
    """Knowledge-graph retrieval: Entity match → linked Chunks."""

    def __init__(
        self,
        *,
        settings: Settings,
        neo4j: Neo4jGraphAdapter,
        repo: RetrievalRepository | None = None,
    ) -> None:
        self._settings = settings
        self._neo4j = neo4j
        self._repo = repo

    async def search(
        self,
        workspace_id: UUID,
        query_text: str,
        top_k: int = 20,
    ) -> list[RetrievalCandidate]:
        """Search Neo4j for entities matching ``query_text``, return chunk hits.

        Args:
            workspace_id: Tenant scope.
            query_text: Query used for entity name/alias matching.
            top_k: Max candidates.

        Returns:
            Candidates with ``retrieval_method=knowledge_graph``.
        """
        rows = await asyncio.to_thread(
            self._neo4j.search_entities_with_chunks,
            workspace_id=workspace_id,
            query_text=query_text,
            top_k=top_k,
        )
        max_chars = self._settings.retrieval_snippet_max_chars
        candidates: list[RetrievalCandidate] = []
        need_fallback_versions: list[UUID] = []
        entity_names: list[str] = []
        entity_ids_by_version: dict[UUID, UUID] = {}

        for row in rows:
            entity_id = _as_uuid(row.get("entity_id"))
            chunk_id = _as_uuid(row.get("chunk_id"))
            document_id = _as_uuid(row.get("document_id"))
            source_version_id = _as_uuid(row.get("source_version_id"))
            name = str(row.get("entity_name") or "")
            score = float(row.get("score") or 0.0)

            if chunk_id is not None:
                snippet = str(row.get("content") or "")[:max_chars]
                page_number: int | None = None
                section_index: int | None = None
                section_title: str | None = None
                document_title: str | None = None
                heading_path: str | None = None
                chunk_index: int | None = None
                document_version_id: UUID | None = None
                if self._repo is not None:
                    hydrated = await self._repo.hydrate_chunks(workspace_id, [chunk_id])
                    h = hydrated.get(chunk_id)
                    if h is not None:
                        snippet = (h.content or snippet)[:max_chars]
                        document_id = document_id or h.document_id
                        page_number = h.page_number
                        section_index = h.section_index
                        section_title = h.section
                        document_title = h.title
                        heading_path = h.heading_path
                        chunk_index = h.chunk_index
                        document_version_id = h.document_version_id
                candidates.append(
                    RetrievalCandidate(
                        workspace_id=workspace_id,
                        chunk_id=chunk_id,
                        entity_id=entity_id,
                        document_id=document_id,
                        text_snippet=snippet or name,
                        raw_score=score,
                        retrieval_method="knowledge_graph",
                        source_methods=["knowledge_graph"],
                        page_number=page_number,
                        section_index=section_index,
                        section_title=section_title,
                        document_title=document_title,
                        heading_path=heading_path,
                        chunk_index=chunk_index,
                        document_version_id=document_version_id,
                    )
                )
            elif source_version_id is not None:
                need_fallback_versions.append(source_version_id)
                if name:
                    entity_names.append(name)
                if entity_id is not None:
                    entity_ids_by_version[source_version_id] = entity_id

        if (
            len(candidates) < top_k
            and self._repo is not None
            and need_fallback_versions
        ):
            remaining = top_k - len(candidates)
            fallback = await self._repo.chunks_for_entity_versions(
                workspace_id,
                list(dict.fromkeys(need_fallback_versions)),
                entity_names=list(dict.fromkeys(entity_names)),
                limit=remaining,
            )
            for row in fallback:
                eid = entity_ids_by_version.get(row.document_version_id)
                candidates.append(
                    RetrievalCandidate(
                        workspace_id=workspace_id,
                        chunk_id=row.chunk_id,
                        entity_id=eid,
                        document_id=row.document_id,
                        text_snippet=(row.content or "")[:max_chars],
                        raw_score=0.6,
                        retrieval_method="knowledge_graph",
                        source_methods=["knowledge_graph"],
                        page_number=row.page_number,
                        section_index=row.section_index,
                        section_title=row.section,
                        document_title=row.title,
                        heading_path=row.heading_path,
                        chunk_index=row.chunk_index,
                        document_version_id=row.document_version_id,
                    )
                )

        return candidates[:top_k]


def _as_uuid(value: object) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None
