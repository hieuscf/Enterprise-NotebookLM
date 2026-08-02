# =============================================================================
# File: retriever.py
# Module/Service: Query Router — Simple Factoid (FR11)
# Layer: Adapter (Protocol)
# Purpose: Retriever abstraction for lightweight factoid retrieval (0 LLM).
# Responsibilities:
#   - Define retrieve(query, top_k) → RetrievedChunk list
# Dependencies:
#   - N/A (Protocol only)
# Public Exports:
#   - RetrievedChunk, Retriever
# Database/Table: N/A
# Related Modules: handlers.factoid_handler, lightweight_retriever
# Important Notes: FactoidHandler must not depend on Qdrant/pgvector directly.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    """One lightweight retrieval hit for extractive factoid answers."""

    chunk_id: UUID | None
    document_id: UUID | None
    text: str
    score: float
    page_number: int | None = None
    char_start: int | None = None
    char_end: int | None = None


@runtime_checkable
class Retriever(Protocol):
    """Lightweight retriever used by Simple Factoid (no hybrid / rerank / graph)."""

    async def retrieve(
        self,
        query: str,
        top_k: int,
        *,
        workspace_id: UUID,
    ) -> list[RetrievedChunk]:
        """Return up to ``top_k`` chunks for ``workspace_id``.

        Args:
            query: User question (raw or normalized).
            top_k: Max chunks to return.
            workspace_id: Tenant scope (required for multi-tenant isolation).

        Returns:
            Chunks ordered by descending score.
        """
        ...
