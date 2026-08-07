# =============================================================================
# File: extractions.py
# Module/Service: Extraction Service (FR7)
# Layer: Schema
# Purpose: Pydantic request/response models for Extractions API (OpenAPI).
# Responsibilities:
#   - ExtractionCreateRequest
#   - ExtractionResponse (maps ORM result_json → result; includes status)
# Dependencies:
#   - Pydantic, app.models.enums
# Public Exports:
#   - ExtractionCreateRequest, ExtractionResponse
# Database/Table: extractions (read mapping only)
# Related Modules: app.api.extractions, Enterprise_notebooklm_openapi.yaml
# Important Notes:
#   - Exposes source_version_id + status for async FE polling (Summary convention).
#   - result is null while processing/failed; structured object when completed.
#   - Cost/token fields are internal (not in public OpenAPI response).
# =============================================================================

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import ExtractionOutputFormat, ExtractionStatus, ExtractionType


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
    status: ExtractionStatus
    result: dict[str, Any] | None = None
    created_at: datetime
