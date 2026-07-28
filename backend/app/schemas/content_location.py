# =============================================================================
# File: content_location.py
# Module/Service: Citation Verification / Search Service
# Layer: Schema
# Purpose: Shared ContentLocation + Citation/Search schemas for FR5 locators.
# Responsibilities:
#   - Expose page_number XOR section_index per file_type (OpenAPI ContentLocation)
#   - Helpers to build location payloads from document_chunks
# Dependencies:
#   - Pydantic; app.models.knowledge.DocumentChunk (for helper typing)
# Public Exports:
#   - ContentLocation, CitationResponse, SearchResultItem, SearchResultResponse
#   - content_location_from_chunk
# Database/Table: document_chunks (page_number, section_index, section)
# Related Modules: Enterprise_notebooklm_openapi.yaml; FR5 Business Context
# Important Notes: Do not invent the missing locator field from the other one.
# =============================================================================

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ContentLocation(BaseModel):
    """Vị trí nội dung trong tài liệu gốc (đúng 1 locator theo file_type)."""

    page_number: int | None = Field(
        default=None,
        description="Physical page/slide/sheet (PDF/PPTX/XLSX). Null for DOCX.",
    )
    section_index: int | None = Field(
        default=None,
        description="1-based logical section index (DOCX). Null for PDF/PPTX/XLSX.",
    )
    section_title: str | None = Field(
        default=None,
        description="Nearest heading/sheet/slide title; used especially for DOCX UI.",
    )


class CitationResponse(BaseModel):
    id: UUID
    message_id: UUID
    retrieval_id: UUID
    document_id: UUID
    text_snippet: str
    verified: bool
    order_index: int
    location: ContentLocation | None = None


class SearchResultItem(BaseModel):
    chunk_id: UUID | None = None
    entity_id: UUID | None = None
    document_id: UUID
    text_snippet: str
    retrieval_method: Literal["vector", "bm25", "knowledge_graph", "rerank"]
    score: float
    rank: int
    location: ContentLocation | None = None


class SearchResultResponse(BaseModel):
    results_count: int
    results: list[SearchResultItem] = Field(default_factory=list)


def content_location_from_chunk(
    *,
    page_number: int | None,
    section_index: int | None,
    section: str | None = None,
) -> ContentLocation:
    """Build API location from chunk columns without inventing missing fields."""
    return ContentLocation(
        page_number=page_number,
        section_index=section_index,
        section_title=section,
    )


def content_location_from_mapping(data: dict[str, Any]) -> ContentLocation:
    """Build location from chunk ORM/dict/payload fields."""
    return content_location_from_chunk(
        page_number=data.get("page_number"),
        section_index=data.get("section_index"),
        section=data.get("section") or data.get("section_title"),
    )
