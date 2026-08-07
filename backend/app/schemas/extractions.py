# =============================================================================
# File: extractions.py
# Module/Service: Extraction Service (FR7)
# Layer: Schema
# Purpose: Pydantic request/response models for Extractions API (OpenAPI).
# Responsibilities:
#   - ExtractionCreateRequest
#   - ExtractionResponse (maps ORM result_json → result)
# Dependencies:
#   - Pydantic, app.models.enums
# Public Exports:
#   - ExtractionCreateRequest, ExtractionResponse
# Database/Table: extractions (read mapping only)
# Related Modules: OpenAPI Extraction schema (API wired in Part 5)
# Important Notes:
#   - Exposes source_version_id for FE current-vs-old version UX.
#   - Cost/token fields are internal (not in public OpenAPI response).
# =============================================================================

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ExtractionOutputFormat, ExtractionType


class ExtractionCreateRequest(BaseModel):
    extraction_type: ExtractionType
    output_format: ExtractionOutputFormat = ExtractionOutputFormat.json


class ExtractionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    source_version_id: uuid.UUID
    extraction_type: ExtractionType
    output_format: ExtractionOutputFormat
    result: dict[str, Any] = Field(validation_alias="result_json")
    created_at: datetime
