# =============================================================================
# File: analysis.py
# Module/Service: Document Analysis
# Layer: Schema
# Purpose: Request/response models for on-demand AI analysis.
# Responsibilities:
#   - Match GET/POST .../versions/{versionId}/analysis
# Dependencies:
#   - Pydantic
# Public Exports:
#   - DocumentAnalysisResponse
# Database/Table: document_versions
# Related Modules: app.services.analysis, app.api.documents
# Important Notes: GET never triggers analysis.
# =============================================================================

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

AiAnalysisStatusLiteral = Literal[
    "not_analyzed",
    "queued",
    "processing",
    "ready",
    "failed",
    "stale",
]


class DocumentAnalysisResponse(BaseModel):
    document_id: UUID
    version_id: UUID
    status: AiAnalysisStatusLiteral
    analyzed_at: datetime | None = None
    error: str | None = None
    pipeline_run_id: UUID | None = None
