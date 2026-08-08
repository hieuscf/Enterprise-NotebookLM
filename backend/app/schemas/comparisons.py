# =============================================================================
# File: comparisons.py
# Module/Service: Comparison Service (FR8)
# Layer: Schema
# Purpose: Pydantic request/response models for Comparisons API (OpenAPI).
# Responsibilities:
#   - ComparisonCreateRequest (document_ids ≥2, optional focus)
#   - ComparisonResponse (public contract including async status)
# Dependencies:
#   - Pydantic, app.models.enums
# Public Exports:
#   - ComparisonCreateRequest, ComparisonResultPayload, ComparisonResponse
# Database/Table: comparisons (read mapping only)
# Related Modules: app.api.comparisons, Enterprise_notebooklm_openapi.yaml
# Important Notes:
#   - status enables FE polling (Summary/Extraction convention); result=null
#     while processing/failed.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import ComparisonStatus


class ComparisonCreateRequest(BaseModel):
    document_ids: list[uuid.UUID] = Field(min_length=2)
    focus: str | None = None

    @field_validator("document_ids")
    @classmethod
    def _at_least_two(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(value) < 2:
            raise ValueError("document_ids must contain at least 2 items")
        return value


class ComparisonResultPayload(BaseModel):
    similarities: list[str] = Field(default_factory=list)
    differences: list[str] = Field(default_factory=list)


class ComparisonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    document_ids: list[uuid.UUID]
    status: ComparisonStatus
    result: ComparisonResultPayload | None = None
    created_at: datetime
