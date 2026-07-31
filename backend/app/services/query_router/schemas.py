# =============================================================================
# File: schemas.py
# Module/Service: Query Router (FR11)
# Layer: Service
# Purpose: RouteDecision and cache view models for Query Router output.
# Responsibilities:
#   - Define RouteDecision returned to Chat / Part 4 handlers
# Dependencies:
#   - app.models.enums.RouteType, app.services.retrieval.schemas.RetrievalResult
# Public Exports:
#   - CacheEntryView, RouteDecision, NormalizedQuery
# Database/Table: query_cache (view fields)
# Related Modules: app.services.query_router.router
# Important Notes: Router never answers — only routes + optional reuse payloads.
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
