# =============================================================================
# File: test_llm_determinism.py
# Module/Service: Comparison Service (TASK-CMP-28)
# Layer: Test
# Purpose: LLM-call budget and deterministic repeatability for V1/V2.
# Responsibilities:
#   - Default comparison uses 0 LLM calls
#   - UNCHANGED / exact diffs do not invoke a mock LLM
#   - Repeat runs keep mapping, classification, risk, and verification
# Dependencies:
#   - pytest, ContractComparisonOrchestrator, LLMTask
# Public Exports:
#   - pytest test cases
# Database/Table: N/A
# Related Modules: comparison/expected
# Important Notes: Mock LLM only. No API keys. No network.
# =============================================================================

from __future__ import annotations

from app.ai.document_structure.llm_boundary_types import LLMTask
from app.ai.document_structure.normalization import normalize_structure
from app.ai.document_structure.pipeline import extract_from_text
from app.services.document_structure.orchestrator import ContractComparisonOrchestrator
from tests.comparison.expected import classification_snapshot


def test_three_runs_are_deterministically_equal(compare_v1_v2) -> None:
    first = compare_v1_v2()
    second = compare_v1_v2()
    third = compare_v1_v2()
    snap = classification_snapshot(first)
    assert classification_snapshot(second) == snap
    assert classification_snapshot(third) == snap
    for report in (first, second, third):
        assert report.summary.as_dict() == first.summary.as_dict()
        assert report.statistics.llm_calls == 0
        assert report.statistics.risk_counts == first.statistics.risk_counts
        assert (
            report.statistics.citation_verification_rate
            == first.statistics.citation_verification_rate
        )


def test_unchanged_pair_does_not_call_llm() -> None:
    calls: list[int] = []

    def generate(_system: str, _user: str) -> str:
        calls.append(1)
        raise AssertionError("UNCHANGED must not invoke LLM")

    v1 = normalize_structure(
        extract_from_text(
            "ĐIỀU 1. Phạm vi\n1.1. Bên A cung cấp dịch vụ.\n",
            title="A",
        )
    )
    v2 = normalize_structure(
        extract_from_text(
            "ĐIỀU 1. Phạm vi\n1.1. Bên A cung cấp dịch vụ.\n",
            title="B",
        )
    )
    report = ContractComparisonOrchestrator().compare_structures(
        v1,
        v2,
        llm_task=LLMTask.EXPLAIN,
        generate=generate,
    )
    assert report.summary.modified == 0
    assert report.statistics.llm_calls == 0
    assert calls == []


def test_invalid_llm_json_does_not_change_diff(v1_structure, v2_structure) -> None:
    def generate(_system: str, _user: str) -> str:
        return "{not-json"

    baseline = ContractComparisonOrchestrator().compare_structures(
        v1_structure,
        v2_structure,
    )
    explained = ContractComparisonOrchestrator().compare_structures(
        v1_structure,
        v2_structure,
        llm_task=LLMTask.EXPLAIN,
        generate=generate,
    )
    assert classification_snapshot(explained) == classification_snapshot(baseline)
    assert explained.explanation_incomplete is True
    assert explained.statistics.llm_calls >= 0
