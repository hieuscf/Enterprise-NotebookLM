# =============================================================================
# File: schemas.py
# Module/Service: Query Router (FR11) + Execution (Part 4)
# Layer: Service
# Purpose: RouteDecision and unified QueryExecutionResult for Chat Service.
# Responsibilities:
#   - Define RouteDecision (classification) and QueryExecutionResult (execution)
# Dependencies:
#   - app.models.enums.RouteType, app.services.retrieval.schemas.RetrievalResult
# Public Exports:
#   - CacheEntryView, RouteDecision, NormalizedQuery, CitationRef, QueryExecutionResult
# Database/Table: query_cache (view fields)
# Related Modules: app.services.query_router.router, orchestrator
# Important Notes: Router never answers — Orchestrator executes 0-LLM branches.
#   CitationRef.verify is owned by Citation Verification (FR5), not the LLM mapper.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from app.models.enums import RouteType
from app.services.retrieval.schemas import RetrievalResult


@dataclass(frozen=True, slots=True)
class NormalizedQuery:
    """Normalized query text + deterministic hash."""

    original: str
    normalized: str
    query_hash: str


@dataclass(slots=True)
class CacheEntryView:
    """Serializable view of a ``query_cache`` hit for downstream reuse."""

    id: UUID
    workspace_id: UUID
    query_hash: str
    query_text: str
    answer: str
    citation_refs: dict[str, Any] | list[Any] | None
    similarity_threshold: float
    hit_count: int
    expires_at: datetime
    last_used_at: datetime | None = None
    match_type: str = "exact"  # exact | semantic
    similarity: float | None = None


@dataclass(slots=True)
class RouteDecision:
    """Outcome of Query Router — classification only (no answer generation)."""

    route_type: RouteType
    reason: str
    latency_ms: int
    query_hash: str
    cache_entry: CacheEntryView | None = None
    retrieval_result: RetrievalResult | None = None
    metadata_payload: dict[str, Any] | None = None
    similarity: float | None = None
    factoid_score: float | None = None
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CitationRef:
    """Deterministic citation for extractive / cached answers."""

    chunk_id: UUID | None
    document_id: UUID | None
    page_number: int | None = None
    verify: bool = True
    text_snippet: str | None = None
    document_version_id: UUID | None = None
    workspace_id: UUID | None = None


@dataclass(slots=True)
class QueryExecutionResult:
    """Unified orchestrator response for Chat Service (0-LLM branches + complex stub)."""

    route_type: RouteType
    answer: str | None
    citation_refs: list[CitationRef]
    metadata: dict[str, Any]
    verify: bool
    latency_ms: int
    status: str | None = None
    cache_id: UUID | None = None
    llm_calls_count: int = 0
    model_used: str | None = None
    query_log_id: UUID | None = None
    message_generation_id: UUID | None = None
