# =============================================================================
# File: documents.py
# Module/Service: Document Ingestion Service
# Layer: Schema
# Purpose: Pydantic models for Documents / Versions / Pipeline status (FR2).
# Responsibilities:
#   - Match OpenAPI Document, DocumentVersion, DocumentListResponse, PipelineRun
# Dependencies:
#   - Pydantic, app.models.enums
# Public Exports:
#   - DocumentResponse, DocumentListResponse, DocumentVersionResponse
#   - PipelineStageLogResponse, PipelineRunResponse
# Database/Table: documents, document_versions, pipeline_runs, pipeline_stage_logs
# Related Modules: app.api.documents, docs/Enterprise_notebooklm_openapi.yaml
# Important Notes: storage_path is internal — not exposed in DocumentVersion schema.
# =============================================================================

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocumentResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    title: str
    file_type: Literal["pdf", "docx", "xlsx", "pptx", "txt"]
    current_version_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    page: int
    page_size: int
    total: int


class DocumentVersionResponse(BaseModel):
    id: UUID
    document_id: UUID
    uploaded_by: UUID
    version_number: int
    file_size_bytes: int
    checksum_sha256: str
    page_count: int | None = Field(
        default=None,
        description=(
            "Physical page/slide/sheet count for PDF/PPTX/XLSX. "
            "For DOCX: logical section count (by heading), not printed Word pages."
        ),
    )
    status: Literal["processing", "ready", "failed"]
    is_current: bool
    created_at: datetime
    preview_status: Literal["pending", "processing", "completed", "failed"] = "pending"
    preview_type: Literal["pdf", "html", "image"] | None = None
    preview_generated_at: datetime | None = None


class PipelineStageLogResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID
    stage: Literal[
        "ocr_cleaning",
        "chunking",
        "preview_generation",
        "document_understanding",
        "cleaning_normalize",
        "hierarchical_chunking",
        "embedding",
        "graph_extraction",
        "indexing",
    ]
    status: Literal["pending", "running", "completed", "failed"]
    duration_ms: int | None = None
    metadata: dict[str, Any] | None = Field(default=None, alias="metadata")
    error_message: str | None = None


class PipelineRunResponse(BaseModel):
    id: UUID
    document_version_id: UUID
    status: Literal["pending", "running", "completed", "failed"]
    retry_count: int
    error_message: str | None = None
    stages: list[PipelineStageLogResponse] = Field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    # Optional document context — populated on admin list (JOIN already required
    # for workspace scope). Null on endpoints that only load the run row.
    document_id: UUID | None = None
    document_title: str | None = None
    file_type: Literal["pdf", "docx", "xlsx", "pptx", "txt"] | None = None
    version_number: int | None = None


class DocumentChunkResponse(BaseModel):
    """Viewer / AI-metadata chunk row (deep-link by chunk_id)."""

    id: UUID
    document_id: UUID
    document_version_id: UUID
    chunk_index: int
    content: str
    page_number: int | None = None
    section_index: int | None = None
    section: str | None = None
    heading_path: str | None = None
    section_path: str | None = Field(
        default=None,
        description="Alias of heading_path for viewer TOC / AI panel.",
    )
    bounding_box: list[float] | None = Field(
        default=None,
        description="Optional [x, y, w, h] from layout_metadata when available.",
    )
    start_offset: int | None = None
    end_offset: int | None = None


class DocumentChunkListResponse(BaseModel):
    document_id: UUID
    document_version_id: UUID | None = None
    document_title: str
    file_type: Literal["pdf", "docx", "xlsx", "pptx", "txt"]
    viewer_kind: Literal["pdf", "original_download"] = "original_download"
    preview_status: Literal["pending", "processing", "completed", "failed"] = "pending"
    preview_type: Literal["pdf", "html", "image"] | None = None
    preview_generated_at: datetime | None = None
    heading_tree: list[dict[str, Any]] = Field(default_factory=list)
    items: list[DocumentChunkResponse] = Field(default_factory=list)
