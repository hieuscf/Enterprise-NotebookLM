# =============================================================================
# File: canonical.py
# Module/Service: Document Intelligence
# Layer: Schema
# Purpose: Canonical Knowledge Document API + citation locator schemas.
# Responsibilities:
#   - CanonicalDocumentResponse for Knowledge View body
#   - CanonicalBlock / CitationLocator for deterministic navigation
# Dependencies:
#   - pydantic
# Public Exports:
#   - CanonicalBlock, CanonicalDocumentResponse, CitationLocator, BlockTextRange
# Database/Table: document_versions.markdown_storage_path, layout artifact
# Related Modules: OpenAPI CanonicalDocument; ContentLocation (provenance)
# Important Notes: Markdown is semantic SoT; page/bbox are optional provenance.
# =============================================================================

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class BlockTextRange(BaseModel):
    """Character range inside one canonical block's text."""

    block_id: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class CitationLocator(BaseModel):
    """Deterministic locator for Knowledge View (primary) + Original provenance."""

    type: Literal["canonical"] = "canonical"
    view: Literal["knowledge"] = "knowledge"
    confidence: Literal["exact", "normalized", "none"] = "none"
    markdown_start: int | None = None
    markdown_end: int | None = None
    ranges: list[BlockTextRange] = Field(default_factory=list)
    page_number: int | None = Field(
        default=None,
        description="Provenance page for Original View (PDF/PPTX/XLSX only).",
    )
    section_index: int | None = Field(
        default=None,
        description="Provenance logical section (DOCX/TXT).",
    )
    bbox: list[float] | None = Field(
        default=None,
        description="Optional [x,y,w,h] for Original View highlight when reliable.",
    )


class CanonicalBlock(BaseModel):
    """One structured block in the Canonical Knowledge Document."""

    id: str
    order_index: int
    block_type: Literal["heading", "paragraph", "table", "list", "figure"]
    content: str
    heading_path: str | None = None
    heading_level: int | None = None
    depth: int = 0
    markdown_start: int | None = None
    markdown_end: int | None = None
    page_number: int | None = None
    section_index: int | None = None
    bbox: list[float] | None = None


class CanonicalDocumentResponse(BaseModel):
    """Knowledge View payload — Canonical Markdown + structured blocks."""

    document_id: UUID
    document_version_id: UUID
    document_title: str
    file_type: Literal["pdf", "docx", "xlsx", "pptx", "txt"]
    markdown: str
    blocks: list[CanonicalBlock] = Field(default_factory=list)
    heading_tree: list[dict[str, Any]] = Field(default_factory=list)
    has_original: bool = True
    preview_status: Literal["pending", "processing", "completed", "failed"] = "pending"
