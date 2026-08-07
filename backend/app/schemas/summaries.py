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
#   - SummaryCreateRequest, SummaryResponse, SummaryTopicSection
# Database/Table: summaries (read mapping only)
# Related Modules: app.api.summaries, Enterprise_notebooklm_openapi.yaml Summary
# Important Notes:
#   - Exposes source_version_id for FE current-vs-old version UX.
#   - sections is set for by_topic; null for other styles.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.enums import SummaryStatus, SummaryStyle


class SummaryCreateRequest(BaseModel):
    style: SummaryStyle


class SummaryTopicSection(BaseModel):
    """Structured topic group for style=by_topic (backend-produced)."""

    topic_id: uuid.UUID | None = None
    title: str
    content: str


class SummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    source_version_id: uuid.UUID
    style: SummaryStyle
    status: SummaryStatus
    content: str | None = None
    sections: list[SummaryTopicSection] | None = None
    created_at: datetime


SummaryStatusLiteral = Literal["processing", "completed", "failed"]
