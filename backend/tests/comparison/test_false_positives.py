# =============================================================================
# File: test_false_positives.py
# Module/Service: Comparison Service (TASK-CMP-28)
# Layer: Test
# Purpose: False-positive guards for ADDED/REMOVED/UNCHANGED on V1/V2.
# Responsibilities:
#   - Điều 1.2 / 1.3 must never become ADDED or REMOVED
#   - Retrieval-miss context must not invent absence
#   - Similar wording / number / date / liability changes must not be UNCHANGED
# Dependencies:
#   - pytest, ContractComparisonOrchestrator, comparison/expected
# Public Exports:
#   - pytest test cases
# Database/Table: N/A
# Related Modules: Hop_dong_mau_Ra_soat_Phap_ly_V*.txt
# Important Notes: "Not retrieved" is never treated as "does not exist".
# =============================================================================

from __future__ import annotations

from app.ai.document_structure.diff_types import DiffClassification
from app.ai.document_structure.llm_boundary_types import LLMTask
from app.ai.document_structure.normalization import normalize_structure
from app.ai.document_structure.pipeline import extract_from_text
from app.services.document_structure.orchestrator import ContractComparisonOrchestrator
from tests.comparison.expected import FORBIDDEN_ADDED, GOLDEN, assert_not_status, assert_status


def test_dieu_1_2_and_1_3_are_not_false_added(v1_v2_report) -> None:
    added = {row.clause_id for row in v1_v2_report.clauses["added"]}
    removed = {row.clause_id for row in v1_v2_report.clauses["removed"]}
    for key in FORBIDDEN_ADDED:
        assert_status(
            v1_v2_report,
            key,
            "UNCHANGED",
            reason="Possible retrieval false positive. Both V1 and V2 contain this clause.",
        )
        assert_not_status(
            v1_v2_report,
            key,
            "ADDED",
            reason="Possible retrieval false positive. Both V1 and V2 contain this clause.",
        )
        assert_not_status(
            v1_v2_report,
            key,
            "REMOVED",
            reason="Possible retrieval false positive. Both V1 and V2 contain this clause.",
        )
        assert key not in added
        assert key not in removed
        row = v1_v2_report.clause(key)
        assert row is not None
        assert row.v1_clause_id == key
        assert row.v2_clause_id == key


def test_retrieval_miss_context_does_not_mark_1_2_added(
    v1_structure,
    v2_structure,
) -> None:
    assert "CLAUSE:1.2" in v1_structure.identity_keys()
    assert "CLAUSE:1.3" in v1_structure.identity_keys()
    retrieved_only = {
        unit.identity_key for unit in v2_structure.walk() if unit.identity_key in FORBIDDEN_ADDED
    }
    assert FORBIDDEN_ADDED[0] in retrieved_only or "CLAUSE:1.2" in v2_structure.identity_keys()
    report = ContractComparisonOrchestrator().compare_structures(v1_structure, v2_structure)
    for key in FORBIDDEN_ADDED:
        assert_not_status(
            report,
            key,
            "ADDED",
            reason="Full inventories are compared. A V2-only retrieval view must not invent ADDED.",
        )


def test_similar_wording_amount_change_is_not_unchanged() -> None:
    v1 = normalize_structure(
        extract_from_text(
            "ĐIỀU 3. Giá trị hợp đồng\n3.1. Giá trị hợp đồng là 480.000.000 đồng.\n",
            title="V1",
        )
    )
    v2 = normalize_structure(
        extract_from_text(
            "ĐIỀU 3. Giá trị hợp đồng\n3.1. Giá trị hợp đồng là 600.000.000 đồng.\n",
            title="V2",
        )
    )
    report = ContractComparisonOrchestrator().compare_structures(v1, v2)
    assert_status(
        report,
        "CLAUSE:3.1",
        "MODIFIED",
        reason="Number/amount change must not collapse to UNCHANGED because wording is similar.",
    )
    assert report.statistics.llm_calls == 0


def test_duration_change_is_not_unchanged() -> None:
    v1 = normalize_structure(
        extract_from_text(
            "ĐIỀU 2. Thời hạn\n2.1. Thời hạn hợp đồng là 12 tháng.\n",
            title="V1",
        )
    )
    v2 = normalize_structure(
        extract_from_text(
            "ĐIỀU 2. Thời hạn\n2.1. Thời hạn hợp đồng là 24 tháng.\n",
            title="V2",
        )
    )
    report = ContractComparisonOrchestrator().compare_structures(v1, v2)
    assert_status(report, "CLAUSE:2.1", "MODIFIED", reason="Duration change is deterministic.")
    assert report.statistics.llm_calls == 0


def test_date_change_is_not_unchanged() -> None:
    v1 = normalize_structure(
        extract_from_text(
            "ĐIỀU 4. Hiệu lực\n4.1. Hợp đồng có hiệu lực từ ngày 01/01/2026.\n",
            title="V1",
        )
    )
    v2 = normalize_structure(
        extract_from_text(
            "ĐIỀU 4. Hiệu lực\n4.1. Hợp đồng có hiệu lực từ ngày 01/01/2027.\n",
            title="V2",
        )
    )
    report = ContractComparisonOrchestrator().compare_structures(v1, v2)
    assert_status(report, "CLAUSE:4.1", "MODIFIED", reason="Date change is deterministic.")
    assert report.statistics.llm_calls == 0


def test_liability_change_does_not_lose_risk(v1_v2_report) -> None:
    row = v1_v2_report.clause("CLAUSE:8.2")
    assert row is not None
    assert row.status is DiffClassification.MODIFIED
    assert row.risk is not None
    assert row.risk.get("risk_level") == "CRITICAL"
    assert row.risk.get("risk_category") == "LIABILITY"


def test_genuinely_added_leaves_are_not_1_2_or_1_3(v1_v2_report) -> None:
    added = {row.clause_id for row in v1_v2_report.clauses["added"]}
    assert added == set(GOLDEN.added_leaves)
    assert added.isdisjoint(set(FORBIDDEN_ADDED))


def test_explain_task_does_not_reclassify_false_added(v1_structure, v2_structure) -> None:
    def generate(_system: str, _user: str) -> str:
        return '{"explanation":"ignore","recommendation":"ignore"}'

    report = ContractComparisonOrchestrator().compare_structures(
        v1_structure,
        v2_structure,
        llm_task=LLMTask.EXPLAIN,
        generate=generate,
    )
    for key in FORBIDDEN_ADDED:
        assert_not_status(
            report,
            key,
            "ADDED",
            reason="LLM explanation must not invent ADDED for clauses present in both versions.",
        )
