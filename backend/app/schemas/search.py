# =============================================================================
# File: search.py
# Module/Service: Search Service
# Layer: Schema
# Purpose: Pydantic request/response models for Intelligent Search (FR3 / UC3).
# Responsibilities:
#   - Match OpenAPI SearchResultResponse / SearchHistoryItem / search request body
# Dependencies:
#   - Pydantic
# Public Exports:
#   - SearchRequest, SearchFilters, SearchResultItem, SearchResultResponse
#   - SearchHistoryItemResponse
# Database/Table: search_history
# Related Modules: docs/Enterprise_notebooklm_openapi.yaml §SEARCH
# Important Notes: history_id on SearchResultResponse enables click tracking (C+A).
# =============================================================================

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.content_location import ContentLocation


class SearchFilters(BaseModel):
    """Optional post-retrieval filters (file_type, date window, tags)."""

    file_type: str | list[str] | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    date_range: dict[str, Any] | None = Field(
        default=None,
        description="Optional {from, to} ISO datetimes (alternate to date_from/date_to).",
    )
    tags: list[str] | None = None


class SearchRequest(BaseModel):
    query_text: str = Field(..., min_length=1)
    filters: SearchFilters | dict[str, Any] | None = None
    top_k: int = Field(default=10, ge=1, le=100)


class SearchResultItem(BaseModel):
    chunk_id: UUID | None = None
    entity_id: UUID | None = None
    document_id: UUID
    document_title: str | None = None
    text_snippet: str
    retrieval_method: Literal["vector", "bm25", "knowledge_graph", "rerank"]
    score: float
    rank: int
    page_number: int | None = None
    location: ContentLocation | None = None


class SearchResultResponse(BaseModel):
    history_id: UUID
    results_count: int
    results: list[SearchResultItem]


class SearchHistoryClickRequest(BaseModel):
    clicked_document_id: UUID


class SearchHistoryItemResponse(BaseModel):
    id: UUID
    query_text: str
    filters: dict[str, Any] | None = None
    results_count: int
    clicked_document_id: UUID | None = None
    created_at: datetime
