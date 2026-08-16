# =============================================================================
# File: test_false_negatives.py
# Module/Service: Comparison Service (TASK-CMP-28)
# Layer: Test
# Purpose: False-negative guards for business-critical V1/V2 changes.
# Responsibilities:
#   - Điều 2, 3, 8, 9, 11 must remain MODIFIED
#   - Liability / termination / dispute risks must not disappear
# Dependencies:
#   - pytest, comparison/expected
# Public Exports:
#   - pytest test cases
# Database/Table: N/A
# Related Modules: Hop_dong_mau_Ra_soat_Phap_ly_V*.txt
# Important Notes: High wording similarity must not hide a real change.
# =============================================================================

from __future__ import annotations

from tests.comparison.expected import FALSE_NEGATIVE_KEYS, GOLDEN, assert_risk, assert_status

CHANGE_REASONS = {
    "CLAUSE:2.1": "Contract term / duration change must not become UNCHANGED.",
    "CLAUSE:3.1": "Contract value / payment change must not become UNCHANGED.",
    "CLAUSE:8.2": "Liability cap change must not become UNCHANGED.",
    "CLAUSE:9.1": "Termination change must not become UNCHANGED.",
    "CLAUSE:11.2": "Dispute-resolution / negotiation-period change must not become UNCHANGED.",
}


def test_critical_modified_clauses_are_not_unchanged(v1_v2_report) -> None:
    for key in FALSE_NEGATIVE_KEYS:
        assert_status(
            v1_v2_report,
            key,
            "MODIFIED",
            reason=CHANGE_REASONS[key],
        )
        assert_status(
            v1_v2_report,
            key,
            "MODIFIED",
            reason="Must not be classified ADDED when the counterpart exists in V1.",
        )
        row = v1_v2_report.clause(key)
        assert row is not None
        assert row.v1_clause_id == key
        assert row.v2_clause_id == key


def test_all_golden_modified_leaves_are_present(v1_v2_report) -> None:
    for key in GOLDEN.modified_leaves:
        assert_status(
            v1_v2_report,
            key,
            "MODIFIED",
            reason="Leaf change from the golden contract is missing.",
        )


def test_article_parents_of_critical_changes_are_modified(v1_v2_report) -> None:
    for key in ("ARTICLE:2", "ARTICLE:3", "ARTICLE:8", "ARTICLE:9", "ARTICLE:11"):
        assert_status(
            v1_v2_report,
            key,
            "MODIFIED",
            use_subtree=True,
            reason="Parent article subtree must reflect child modifications.",
        )


def test_business_critical_risks_remain(v1_v2_report) -> None:
    assert_risk(
        v1_v2_report,
        "CLAUSE:8.2",
        level="CRITICAL",
        category="LIABILITY",
        reason="Liability risk must not disappear.",
    )
    assert_risk(
        v1_v2_report,
        "CLAUSE:9.1",
        category="TERMINATION",
        level_in=("HIGH", "CRITICAL"),
        reason="Termination risk must not disappear.",
    )
    assert_risk(
        v1_v2_report,
        "CLAUSE:11.2",
        level="HIGH",
        category="DISPUTE_RESOLUTION",
        reason="Dispute-resolution risk must not disappear.",
    )
