# =============================================================================
# File: result_schemas.py
# Module/Service: Comparison Service (FR8)
# Layer: Schema
# Purpose: Pydantic schema + parser for multi-document comparison LLM output.
# Responsibilities:
#   - Validate ``similarities`` / ``differences`` string arrays
#   - Normalize empty / non-string entries; reject inventable free-form blobs
# Dependencies:
#   - pydantic; app.adapters.llm_result.parse_json_object
# Public Exports:
#   - ComparisonResult, parse_comparison_result, comparison_result_to_dict
# Database/Table: comparisons.result (JSONB shape contract)
# Related Modules: comparison_service, prompts, OpenAPI Comparison.result
# Important Notes: Extra keys forbidden — OpenAPI only allows similarities/differences.
# =============================================================================

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.adapters.llm_result import parse_json_object


class ComparisonResult(BaseModel):
    """Structured multi-document comparison output (OpenAPI Comparison.result)."""

    model_config = ConfigDict(extra="forbid")

    similarities: list[str] = Field(default_factory=list)
    differences: list[str] = Field(default_factory=list)

    @field_validator("similarities", "differences", mode="before")
    @classmethod
    def _normalize_string_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("must be a list of strings")
        cleaned: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("each item must be a string")
            text = item.strip()
            if text:
                cleaned.append(text)
        return cleaned


def parse_comparison_result(payload: dict[str, Any] | str) -> ComparisonResult:
    """Parse and validate comparison JSON from a dict or raw LLM text."""
    if isinstance(payload, str):
        data = parse_json_object(payload)
    else:
        data = payload
    if not isinstance(data, dict):
        raise ValueError("comparison result must be a JSON object")
    return ComparisonResult.model_validate(data)


def comparison_result_to_dict(result: ComparisonResult) -> dict[str, list[str]]:
    """Serialize to the OpenAPI ``Comparison.result`` object shape."""
    return {
        "similarities": list(result.similarities),
        "differences": list(result.differences),
    }
