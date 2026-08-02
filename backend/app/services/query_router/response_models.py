# =============================================================================
# File: response_models.py
# Module/Service: Query Router — Metadata / Factoid Handlers (FR11)
# Layer: Schema
# Purpose: Unified QueryRouterResult for Chat Service (0-LLM branches).
# Responsibilities:
#   - Single response shape for metadata + factoid (+ complex downgrade)
# Dependencies:
#   - pydantic, app.models.enums.RouteType, CitationRef
# Public Exports:
#   - QueryRouterResult
# Database/Table: N/A
# Related Modules: handlers.metadata_handler, handlers.factoid_handler, orchestrator
# Important Notes: Chat Service must not branch on handler internals.
# =============================================================================

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import RouteType
from app.services.query_router.schemas import CitationRef


class QueryRouterResult(BaseModel):
    """Unified handler result consumed by Chat / Orchestrator."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    route_type: RouteType
    answer: str | None = None
    citation_refs: list[CitationRef] = Field(default_factory=list)
    confidence: float | None = None
    verify: bool = False
    status: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
