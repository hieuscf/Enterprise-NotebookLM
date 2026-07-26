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
    page_count: int | None = None
    status: Literal["processing", "ready", "failed"]
    is_current: bool
    created_at: datetime


class PipelineStageLogResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID
    stage: Literal[
        "ocr_cleaning",
        "chunking",
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
