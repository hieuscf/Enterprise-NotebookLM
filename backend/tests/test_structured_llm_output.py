# =============================================================================
# File: test_structured_llm_output.py
# Module/Service: Structured LLM Output (FR8 / TASK-CMP-13)
# Layer: Service
# Purpose: Schema, enum, echo-fact, markdown-parse, and evidence-id tests.
# Responsibilities:
#   - Strict JSON contract; mismatch rejects; facts remain authoritative
# Dependencies:
#   - pytest, parse_structured_llm_output, validate_llm_output
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: FR8 ComparisonResult (similarities/differences) is separate
# Important Notes: Does not call a live LLM. Does not persist output.
# =============================================================================

from __future__ import annotations

from app.ai.document_structure.llm_boundary_engine import validate_llm_output
from app.ai.document_structure.llm_boundary_types import (
    LLMValidationReason,
    ValidationStatus,
)
from app.ai.document_structure.llm_output_schema import (
    StructuredComparisonExplanation,
    parse_structured_llm_output,
)
from app.ai.document_structure.scoring_types import RiskLevel
from app.ai.document_structure.taxonomy_types import RiskCategory
from tests.test_comparison_llm_boundary import _clean_output, _verified_context


def test_parse_markdown_fenced_json() -> None:
    raw = """```json
    {"explanation": "Cap reduced.", "recommendation": null, "claims": []}
    ```"""
    parsed = parse_structured_llm_output(raw)
    assert parsed.explanation == "Cap reduced."
    assert parsed.recommendation is None


def test_empty_string_becomes_null() -> None:
    parsed = parse_structured_llm_output(
        {"explanation": "ok", "recommendation": "", "legal_significance": "   "}
    )
    assert parsed.recommendation is None
    assert parsed.legal_significance is None


def test_invalid_risk_enum_is_rejected() -> None:
    context, _, _ = _verified_context()
    payload = _clean_output(context, extra={"risk_level": "VERY_HIGH"})
    result = validate_llm_output(context, payload)
    assert result.status is ValidationStatus.REJECTED
    assert LLMValidationReason.INVALID_ENUM in result.reasons
    assert result.facts.risk_level == "CRITICAL"


def test_invalid_category_enum_is_rejected() -> None:
    context, _, _ = _verified_context()
    result = validate_llm_output(context, _clean_output(context, extra={"risk_category": "SEVERE"}))
    assert result.status is ValidationStatus.REJECTED
    assert LLMValidationReason.INVALID_ENUM in result.reasons
    assert result.facts.risk_category == "LIABILITY"


def test_matching_echo_fields_are_accepted() -> None:
    context, _, _ = _verified_context()
    payload = _clean_output(
        context,
        extra={
            "finding_id": context.facts.finding_id,
            "identity_key": "CLAUSE:8.2",
            "clause_id": "8.2",
            "change_type": "MODIFIED",
            "risk_level": "CRITICAL",
            "risk_category": "LIABILITY",
            "risk_score": 82,
        },
    )
    result = validate_llm_output(context, payload)
    assert result.status is ValidationStatus.ACCEPTED
    assert result.output is not None
    assert result.output.risk_level == "CRITICAL"
    assert result.output.risk_category == "LIABILITY"
    assert result.output.finding_id == context.facts.finding_id
    assert result.facts.risk_score == 82.0


def test_clause_id_mismatch_is_rejected() -> None:
    context, _, _ = _verified_context()
    result = validate_llm_output(context, _clean_output(context, extra={"clause_id": "9.1"}))
    assert result.status is ValidationStatus.REJECTED
    assert LLMValidationReason.INVALID_CLAUSE_REFERENCE in result.reasons
    assert result.output is None


def test_finding_id_mismatch_is_rejected() -> None:
    context, _, _ = _verified_context()
    result = validate_llm_output(context, _clean_output(context, extra={"finding_id": "other"}))
    assert result.status is ValidationStatus.REJECTED
    assert LLMValidationReason.INVALID_FINDING_REFERENCE in result.reasons


def test_category_override_is_rejected() -> None:
    context, _, _ = _verified_context()
    result = validate_llm_output(context, _clean_output(context, extra={"risk_category": "PAYMENT"}))
    assert result.status is ValidationStatus.REJECTED
    assert LLMValidationReason.INVALID_DETERMINISTIC_FACT_OVERRIDE in result.reasons
    assert result.facts.risk_category == "LIABILITY"


def test_unknown_top_level_evidence_id_rejected() -> None:
    context, _, _ = _verified_context()
    result = validate_llm_output(context, _clean_output(context, extra={"evidence_ids": ["v2-9.1"]}))
    assert result.status is ValidationStatus.REJECTED
    assert LLMValidationReason.UNKNOWN_EVIDENCE_ID in result.reasons


def test_invented_source_locator_rejected() -> None:
    context, _, _ = _verified_context()
    payload = _clean_output(context, extra={"page": 10, "chunk_id": "chunk-x"})
    result = validate_llm_output(context, payload)
    assert result.status is ValidationStatus.REJECTED
    assert LLMValidationReason.SCHEMA_INVALID in result.reasons


def test_recommendation_does_not_change_contract_value() -> None:
    context, _, _ = _verified_context()
    payload = _clean_output(context)
    payload["recommendation"] = "Đề nghị tăng lên 1,000,000 USD."
    result = validate_llm_output(context, payload)
    assert result.facts.new_value == "500,000"
    assert result.facts.old_value == "1,000,000"
    assert result.output is not None
    assert "1,000,000" in (result.output.recommendation or "")


def test_schema_types_use_project_enums() -> None:
    parsed = parse_structured_llm_output(
        {
            "risk_level": "CRITICAL",
            "risk_category": "LIABILITY",
            "change_type": "MODIFIED",
            "explanation": "x",
        }
    )
    assert parsed.risk_level is RiskLevel.CRITICAL
    assert parsed.risk_category is RiskCategory.LIABILITY
    assert isinstance(parsed, StructuredComparisonExplanation)
