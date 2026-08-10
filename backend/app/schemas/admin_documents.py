# =============================================================================
# File: admin_documents.py
# Module/Service: Document Ingestion Service / Admin Console (FR2, FR12)
# Layer: Schema
# Purpose: Pydantic models for Platform Manage global document operations
#          (GET /admin/documents*).
# Responsibilities:
#   - AdminDocumentListItem / ListResponse with summary metrics
#   - AdminDocumentDetailResponse (workspace + current version + pipeline)
# Dependencies:
#   - Pydantic, app.schemas.documents (DocumentVersion, PipelineRun)
# Public Exports:
#   - AdminDocumentSummary, AdminDocumentListItem, AdminDocumentListResponse
#   - AdminDocumentDetailResponse
# Database/Table: documents, document_versions, workspaces, pipeline_runs
# Related Modules: app.api.admin_documents, docs/Enterprise_notebooklm_openapi.yaml
# Important Notes:
#   - Status is DocumentVersion.status (processing|ready|failed), not pipeline.
#   - Never expose storage_path, credentials, or document binary content.
# =============================================================================

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.documents import DocumentVersionResponse, PipelineRunResponse


class AdminDocumentSummary(BaseModel):
    """Enterprise (or filter-scoped) counts by current version status."""

    total: int
    processing: int
    ready: int
    failed: int


class AdminDocumentListItem(BaseModel):
    id: UUID
    title: str
    filename: str | None = Field(
        default=None,
        description="Original upload filename derived from version storage key basename.",
    )
    workspace_id: UUID
    workspace_name: str
    file_type: Literal["pdf", "docx", "xlsx", "pptx", "txt"]
    current_version_id: UUID | None = None
    version_number: int | None = None
    file_size_bytes: int | None = None
    page_count: int | None = None
    status: Literal["processing", "ready", "failed"] | None = Field(
        default=None,
        description="Current DocumentVersion.status; null when no current version.",
    )
    created_at: datetime
    updated_at: datetime


class AdminDocumentListResponse(BaseModel):
    items: list[AdminDocumentListItem]
    page: int
    page_size: int
    total: int
    summary: AdminDocumentSummary


class AdminDocumentDetailResponse(BaseModel):
    id: UUID
    title: str
    filename: str | None = None
    workspace_id: UUID
    workspace_name: str
    file_type: Literal["pdf", "docx", "xlsx", "pptx", "txt"]
    current_version_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    current_version: DocumentVersionResponse | None = None
    latest_pipeline_run: PipelineRunResponse | None = None
