# =============================================================================
# File: llm_output_schema.py
# Module/Service: Structured LLM Output (FR8 / TASK-CMP-13)
# Layer: Schema
# Purpose: Pydantic contract for comparison explanation JSON from the LLM.
# Responsibilities:
#   - Parse fenced or raw JSON; coerce empty strings to null
#   - Validate project enums (RiskLevel, RiskCategory, DiffClassification)
#   - Reject unknown keys (page, chunk_id, citations, invented enums)
# Dependencies:
#   - pydantic; parse_json_object; scoring/taxonomy/diff enums
# Public Exports:
#   - UncertaintyCode, StructuredClaim, StructuredComparisonExplanation,
#     parse_structured_llm_output
# Database/Table: N/A (not OpenAPI Comparison.result)
# Related Modules: llm_boundary_engine; FR8 ComparisonResult is a different schema
# Important Notes:
#   - Echo fields are optional; if present they must match deterministic facts.
#   - extra=forbid — LLM cannot invent source locators.
# =============================================================================

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.adapters.llm_result import parse_json_object
from app.ai.document_structure.diff_types import DiffClassification
from app.ai.document_structure.scoring_types import RiskLevel
from app.ai.document_structure.taxonomy_types import RiskCategory


class UncertaintyCode(StrEnum):
    NONE = "NONE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    INVALID = "INVALID"


def _blank_to_none(value: Any) -> Any:
    if isinstance(value, str) and not value.strip():
        return None
    return value


class StructuredClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = ""
    evidence_ids: list[str] = Field(default_factory=list)

    @field_validator("text", mode="before")
    @classmethod
    def _text(cls, value: Any) -> str:
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ValueError("claim text must be a string")
        return value.strip()

    @field_validator("evidence_ids", mode="before")
    @classmethod
    def _ids(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("evidence_ids must be a list")
        return [str(item).strip() for item in value if str(item).strip()]


class StructuredComparisonExplanation(BaseModel):
    """Machine-validatable comparison explanation. Not comparison truth."""

    model_config = ConfigDict(extra="forbid")

    finding_id: str | None = None
    identity_key: str | None = None
    clause_id: str | None = None
    change_type: DiffClassification | None = None
    risk_level: RiskLevel | None = None
    risk_category: RiskCategory | None = None
    rule_id: str | None = None
    risk_score: float | None = None
    explanation: str | None = None
    legal_significance: str | None = None
    business_impact: str | None = None
    recommendation: str | None = None
    uncertainty: UncertaintyCode | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    claims: list[StructuredClaim] = Field(default_factory=list)

    @field_validator(
        "finding_id",
        "identity_key",
        "clause_id",
        "rule_id",
        "explanation",
        "legal_significance",
        "business_impact",
        "recommendation",
        mode="before",
    )
    @classmethod
    def _optional_text(cls, value: Any) -> Any:
        return _blank_to_none(value)

    @field_validator("evidence_ids", mode="before")
    @classmethod
    def _evidence_ids(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("evidence_ids must be a list")
        return [str(item).strip() for item in value if str(item).strip()]

    @field_validator("uncertainty", mode="before")
    @classmethod
    def _uncertainty(cls, value: Any) -> Any:
        value = _blank_to_none(value)
        if value is None:
            return None
        if isinstance(value, str):
            folded = value.strip().upper()
            if folded in UncertaintyCode.__members__:
                return folded
        return value


def parse_structured_llm_output(
    payload: Mapping[str, Any] | str,
) -> StructuredComparisonExplanation:
    """Parse raw LLM text or a dict into the CMP-13 schema."""
    if isinstance(payload, Mapping):
        data = dict(payload)
    else:
        data = parse_json_object(str(payload))
    return StructuredComparisonExplanation.model_validate(data)
