# =============================================================================
# File: test_comparison_report_builder.py
# Module/Service: Report Service (TASK-CMP-24)
# Layer: Service
# Purpose: Unit tests for the comparison report builder (presentation only).
# Responsibilities:
#   - Project stored comparison results into the report model
#   - Statistics, risk grouping, evidence verification, empty sections
# Dependencies:
#   - pytest, app.services.report.comparison_report_builder
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: report_aggregation, markdown/docx renderers
# Important Notes: Does not remap clauses, rescore risk, or call an LLM.
# =============================================================================

from __future__ import annotations

from uuid import uuid4

from app.services.report.comparison_report_builder import (
    CONSERVATIVE_ABSENCE_MESSAGE,
    build_comparison_report_content,
    display_clause_id,
)

RESULT = {
    "similarities": ["Both cap liability."],
    "differences": ["Cap increased."],
    "contract_comparison": {
        "metadata": {
            "comparison_id": "cmp-1",
            "workspace_id": "ws-1",
            "document_v1": {"title": "Contract V1", "document_id": "doc-1"},
            "document_v2": {"title": "Contract V2", "document_id": "doc-2"},
            "quality_status": "PASS",
        },
        "summary": {
            "total_clauses": 4,
            "unchanged": 1,
            "modified": 1,
            "added": 1,
            "removed": 1,
        },
        "statistics": {
            "risk_counts": {"critical": 1, "high": 0, "medium": 0, "low": 0},
            "llm_calls": 0,
            "unresolved": 0,
        },
        "clauses": {
            "modified": [
                {
                    "clause_id": "CLAUSE:8.2",
                    "status": "MODIFIED",
                    "v1_text": "Cap 480,000,000",
                    "v2_text": "Cap 600,000,000",
                    "exact_differences": [
                        {
                            "value_type": "MONEY",
                            "old": {"raw": "480,000,000"},
                            "new": {"raw": "600,000,000"},
                            "delta": "+120,000,000",
                            "relative_change_percent": "25",
                        }
                    ],
                    "risk": {
                        "risk_level": "CRITICAL",
                        "risk_category": "LIABILITY",
                        "reason": "Liability cap increased",
                    },
                    "explanation": {
                        "output": {
                            "explanation": "The cap rose.",
                            "recommendation": "Review insurance.",
                        }
                    },
                    "evidence": [
                        {
                            "evidence_id": "ev-1",
                            "side": "OLD",
                            "page_number": 12,
                            "display_text": "Cap 480,000,000",
                        },
                        {
                            "evidence_id": "ev-2",
                            "side": "NEW",
                            "page_number": 13,
                            "display_text": "Cap 600,000,000",
                        },
                    ],
                    "verification": {
                        "status": "PARTIALLY_VERIFIED",
                        "verified_evidence_ids": ["ev-1"],
                        "evidence_results": [
                            {"evidence_id": "ev-1", "status": "VALID"},
                            {"evidence_id": "ev-2", "status": "MISMATCH"},
                        ],
                    },
                }
            ],
            "added": [
                {
                    "clause_id": "CLAUSE:8.3",
                    "status": "ADDED",
                    "v2_text": "Limitation of damages.",
                    "verification": {"status": "INSUFFICIENT_EVIDENCE"},
                }
            ],
            "removed": [
                {
                    "clause_id": "CLAUSE:4.9",
                    "status": "REMOVED",
                    "v1_text": "Old warranty.",
                    "verification": {
                        "absence_status": "ABSENCE_CONFIRMED",
                        "human_message": "Counterpart confirmed absent.",
                    },
                }
            ],
            "unchanged": [{"clause_id": "CLAUSE:1.1", "status": "UNCHANGED"}],
            "unresolved": [],
        },
        "risks": [],
    },
}


def _report() -> dict:
    return build_comparison_report_content(
        result=RESULT,
        comparison_id=uuid4(),
        workspace_id=uuid4(),
        title="Legal review",
        status="completed",
    )


def test_legacy_result_keeps_bullets_without_contract_report() -> None:
    content = build_comparison_report_content(
        result={"similarities": ["a"], "differences": ["b"]}
    )
    assert content["similarities"] == ["a"]
    assert content["differences"] == ["b"]
    assert content["has_contract_report"] is False
    assert content["comparison_report"] is None


def test_executive_summary_uses_stored_counts() -> None:
    report = _report()["comparison_report"]
    summary = report["executive_summary"]
    assert summary["total_clauses"] == 4
    assert summary["modified"] == 1
    assert summary["added"] == 1
    assert summary["removed"] == 1
    assert summary["unchanged"] == 1
    assert summary["critical_risks"] == 1
    assert summary["verified_evidence_count"] == 1


def test_clause_buckets_preserve_upstream_status() -> None:
    report = _report()["comparison_report"]
    assert [row["clause_id"] for row in report["changed_clauses"]] == ["CLAUSE:8.2"]
    assert [row["clause_id"] for row in report["added_clauses"]] == ["CLAUSE:8.3"]
    assert [row["clause_id"] for row in report["removed_clauses"]] == ["CLAUSE:4.9"]
    assert report["unchanged_clauses"]["count"] == 1
    assert "CLAUSE:1.1" in report["unchanged_clauses"]["clause_ids"]


def test_exact_difference_is_consumed_not_recalculated() -> None:
    detail = _report()["comparison_report"]["detailed_clause_comparisons"][0]
    assert detail["v1_text"] == "Cap 480,000,000"
    assert detail["exact_differences"][0]["delta"] == "+120,000,000"
    assert detail["exact_differences"][0]["percent"] == "25%"
    assert detail["explanation"] == "The cap rose."
    assert detail["recommendation"] == "Review insurance."


def test_unverified_evidence_is_never_labelled_verified() -> None:
    evidence = _report()["comparison_report"]["detailed_clause_comparisons"][0]["evidence"]
    by_side = {item["side"]: item for item in evidence}
    assert by_side["OLD"]["verification_state"] == "verified"
    assert by_side["NEW"]["verification_state"] == "unverified"
    assert by_side["NEW"]["page_number"] == 13


def test_added_clause_uses_conservative_absence_message() -> None:
    added = next(
        item
        for item in _report()["comparison_report"]["detailed_clause_comparisons"]
        if item["clause_id"] == "CLAUSE:8.3"
    )
    assert added["absence_note"] == CONSERVATIVE_ABSENCE_MESSAGE
    assert "không có điều khoản" not in added["absence_note"].lower()


def test_confirmed_absence_uses_upstream_message() -> None:
    removed = next(
        item
        for item in _report()["comparison_report"]["detailed_clause_comparisons"]
        if item["clause_id"] == "CLAUSE:4.9"
    )
    assert removed["absence_note"] == "Counterpart confirmed absent."


def test_empty_optional_fields_are_omitted() -> None:
    content = build_comparison_report_content(
        result={
            "similarities": [],
            "differences": [],
            "contract_comparison": {
                "summary": {
                    "total_clauses": 1,
                    "unchanged": 1,
                    "modified": 0,
                    "added": 0,
                    "removed": 0,
                },
                "clauses": {
                    "unchanged": [{"clause_id": "CLAUSE:1", "status": "UNCHANGED"}],
                    "modified": [],
                    "added": [],
                    "removed": [],
                    "unresolved": [],
                },
            },
        }
    )
    report = content["comparison_report"]
    assert report["changed_clauses"] == []
    assert report["added_clauses"] == []
    assert report["removed_clauses"] == []
    assert report["detailed_clause_comparisons"] == []
    assert report["generation_metadata"]["llm_calls_report"] == 0


def test_display_clause_id_strips_prefix_only() -> None:
    assert display_clause_id("CLAUSE:8.2") == "8.2"
    assert display_clause_id("ARTICLE:2") == "2"
