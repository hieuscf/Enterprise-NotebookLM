# =============================================================================
# File: reports.py
# Module/Service: Report Service (FR9)
# Layer: Schema
# Purpose: Pydantic request/response models for Reports API (OpenAPI).
# Responsibilities:
#   - ReportCreateRequest (title, export_format, items)
#   - ReportResponse (maps ORM format → export_format, file_path → file_url)
# Dependencies:
#   - Pydantic, app.models.enums
# Public Exports:
#   - ReportItemInput, ReportCreateRequest, ReportResponse
# Database/Table: reports, report_items (read mapping only)
# Related Modules: app.api.reports, Enterprise_notebooklm_openapi.yaml
# Important Notes:
#   - OpenAPI uses export_format / file_url; DB columns are format / file_path.
#   - No error field in OpenAPI or schema v1 reports table.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import ReportFormat, ReportSourceType, ReportStatus


class ReportItemInput(BaseModel):
    source_type: ReportSourceType
    source_id: uuid.UUID
    order_index: int = Field(ge=0)


class ReportCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    export_format: ReportFormat
    items: list[ReportItemInput] = Field(min_length=1)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("title must not be empty")
        return cleaned


class ReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    export_format: ReportFormat
    status: ReportStatus
    file_url: str | None = None
    created_at: datetime
