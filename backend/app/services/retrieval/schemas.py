# =============================================================================
# File: schemas.py
# Module/Service: Search Service / Hybrid Retrieval
# Layer: Service
# Purpose: Shared dataclasses for Hybrid Retrieval candidates and results (FR3).
# Responsibilities:
#   - Define RetrievalCandidate / RetrievalResult used by all retrieval sources
# Dependencies:
#   - N/A
# Public Exports:
#   - RetrievalCandidate, RetrievalResult
# Database/Table: N/A
# Related Modules: app.services.retrieval.*, Enterprise_notebooklm_openapi.yaml SearchResult
# Important Notes:
#   - retrieval_method values: vector | bm25 | knowledge_graph | rerank | metadata
#   - Search API maps to OpenAPI enum (excludes metadata).
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID


@dataclass(slots=True)
class RetrievalCandidate:
    """One retrieval hit before or after cross-encoder re-ranking."""

    workspace_id: UUID
    text_snippet: str
    retrieval_method: str
    raw_score: float
    document_id: UUID | None = None
    chunk_id: UUID | None = None
    entity_id: UUID | None = None
    score: float | None = None
    rank: int | None = None
    source_methods: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RetrievalResult:
    """Unified Hybrid Retrieval output after merge + re-rank."""

    items: list[RetrievalCandidate]
    latency_ms: int
    sources_used: list[str]
    timings: dict[str, int | None] = field(default_factory=dict)
