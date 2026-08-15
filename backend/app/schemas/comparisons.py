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
#   - review / comments are optional CMP-20/22 metadata on the comparison row,
#     never inside result. Analysis fields stay immutable.
#   - audit is served on a dedicated GET; it is not part of ComparisonResponse.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import ComparisonStatus

ComparisonReviewStatus = Literal[
    "OPEN",
    "REVIEWED",
    "NEEDS_ATTENTION",
    "ACKNOWLEDGED",
]

ComparisonCommentTarget = Literal[
    "CLAUSE",
    "FINDING",
    "EXACT_DIFFERENCE",
    "EVIDENCE",
]


class ComparisonCreateRequest(BaseModel):
    document_ids: list[uuid.UUID] = Field(min_length=2)
    focus: str | None = None

    @field_validator("document_ids")
    @classmethod
    def _at_least_two(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(value) < 2:
            raise ValueError("document_ids must contain at least 2 items")
        return value


class ComparisonReviewDecision(BaseModel):
    status: ComparisonReviewStatus
    reviewer_id: uuid.UUID | None = None
    reviewer_name: str | None = None
    reviewed_at: datetime | None = None


class ComparisonReviewUpdateRequest(BaseModel):
    clause_id: str = Field(min_length=1, max_length=128)
    status: ComparisonReviewStatus

    @field_validator("clause_id")
    @classmethod
    def _clause_id_not_blank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("clause_id is required")
        return text


class ComparisonCommentCreateRequest(BaseModel):
    clause_id: str = Field(min_length=1, max_length=128)
    body: str = Field(min_length=1, max_length=4000)
    target_type: ComparisonCommentTarget = "CLAUSE"
    target_id: str | None = Field(default=None, max_length=128)

    @field_validator("clause_id")
    @classmethod
    def _clause_id_not_blank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("clause_id is required")
        return text

    @field_validator("body")
    @classmethod
    def _body_not_blank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("body is required")
        return text

    @field_validator("target_id")
    @classmethod
    def _target_id_trim(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None


class ComparisonCommentUpdateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)

    @field_validator("body")
    @classmethod
    def _body_not_blank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("body is required")
        return text


class ComparisonComment(BaseModel):
    id: str
    clause_id: str
    target_type: Literal["CLAUSE", "EXACT_DIFFERENCE", "EVIDENCE"]
    target_id: str | None = None
    body: str
    author_id: uuid.UUID | None = None
    author_name: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


ComparisonAuditActionName = Literal[
    "CLAUSE_OPENED",
    "REVIEW_STATUS_CHANGED",
    "COMMENT_ADDED",
    "COMMENT_EDITED",
    "COMMENT_DELETED",
]


class ComparisonAuditCreateRequest(BaseModel):
    action: Literal["CLAUSE_OPENED"]
    clause_id: str = Field(min_length=1, max_length=128)

    @field_validator("clause_id")
    @classmethod
    def _clause_id_not_blank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("clause_id is required")
        return text


class ComparisonAuditEvent(BaseModel):
    id: str
    action: ComparisonAuditActionName
    clause_id: str | None = None
    actor_id: uuid.UUID | None = None
    actor_name: str | None = None
    occurred_at: datetime
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    target_type: str | None = None
    target_id: str | None = None
    comment_id: str | None = None


class ComparisonAuditTrailResponse(BaseModel):
    events: list[ComparisonAuditEvent] = Field(default_factory=list)


class ComparisonResultPayload(BaseModel):
    similarities: list[str] = Field(default_factory=list)
    differences: list[str] = Field(default_factory=list)
    contract_comparison: dict[str, Any] | None = None


class ComparisonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    document_ids: list[uuid.UUID]
    status: ComparisonStatus
    result: ComparisonResultPayload | None = None
    review: dict[str, ComparisonReviewDecision] = Field(default_factory=dict)
    comments: list[ComparisonComment] = Field(default_factory=list)
    created_at: datetime
