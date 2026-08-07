# =============================================================================
# File: summaries.py
# Module/Service: Summary Service (FR6)
# Layer: Schema
# Purpose: Pydantic request/response models for Summaries API (OpenAPI).
# Responsibilities:
#   - SummaryCreateRequest (style)
#   - SummaryResponse (public contract; maps ORM type → style)
# Dependencies:
#   - Pydantic, app.models.enums
# Public Exports:
#   - SummaryCreateRequest, SummaryResponse
# Database/Table: summaries (read mapping only)
# Related Modules: app.api.summaries, Enterprise_notebooklm_openapi.yaml Summary
# Important Notes: Does not expose Celery IDs, token costs, or provider errors.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import SummaryStatus, SummaryStyle


class SummaryCreateRequest(BaseModel):
    style: SummaryStyle


class SummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    style: SummaryStyle
    status: SummaryStatus
    content: str | None = None
    created_at: datetime


SummaryStatusLiteral = Literal["processing", "completed", "failed"]
