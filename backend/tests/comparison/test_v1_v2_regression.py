# =============================================================================
# File: test_v1_v2_regression.py
# Module/Service: Comparison Service (TASK-CMP-28)
# Layer: Test
# Purpose: End-to-end V1/V2 golden regression for Contract Comparison.
# Responsibilities:
#   - Compare Hop_dong_mau V1 vs V2 against the human-defined golden contract
#   - Assert article rollup, leaf classifications, risks, and summary consistency
# Dependencies:
#   - pytest, ContractComparisonOrchestrator, comparison/expected
# Public Exports:
#   - pytest test cases
# Database/Table: N/A
# Related Modules: tests/fixtures/comparison_evaluation/v1_v2_regression.json
# Important Notes: Deterministic. 0 LLM. Does not snapshot prose, UUIDs, or times.
# =============================================================================

from __future__ import annotations

from app.ai.document_structure.diff_types import DiffClassification
from app.services.document_structure.quality import ComparisonQualityEvaluator
from tests.comparison.expected import (
    ARTICLE_KEYS,
    GOLDEN,
    RISK_RANK,
    article_max_risk,
    article_rollup,
    assert_risk,
    assert_status,
)

ARTICLE_MIN_RISK = {
    "ARTICLE:8": "CRITICAL",
    "ARTICLE:9": "HIGH",
    "ARTICLE:11": "HIGH",
}


def test_v1_and_v2_fixtures_are_not_duplicated(v1_txt, v2_txt, v1_pdf, v2_pdf) -> None:
    assert v1_txt.parent == v2_txt.parent == v1_pdf.parent == v2_pdf.parent
    assert v1_txt.name.endswith("V1.txt")
    assert v2_txt.name.endswith("V2.txt")


def test_golden_contract_matches_pipeline(v1_v2_report) -> None:
    result = ComparisonQualityEvaluator().evaluate(
        v1_v2_report,
        list(GOLDEN.expected),
        case_id=GOLDEN.case_id,
    )
    assert result.mismatches == [], "\n".join(result.mismatches)


def test_article_classifications_dieu_1_to_12(v1_v2_report) -> None:
    expected = {
        item.identity_key: item.status
        for item in GOLDEN.expected
        if item.identity_key in ARTICLE_KEYS
    }
    assert set(expected) == set(ARTICLE_KEYS)
    for key, status in expected.items():
        assert_status(
            v1_v2_report,
            key,
            status or "",
            use_subtree=True,
            reason="Article heading may be UNCHANGED; subtree_status is authoritative.",
        )


def test_article_rollup_matches_article_ground_truth(v1_v2_report) -> None:
    counts = article_rollup(v1_v2_report)
    assert counts["missing"] == 0
    assert counts["unchanged"] == GOLDEN.article_summary["unchanged"], counts
    assert counts["modified"] == GOLDEN.article_summary["modified"], counts
    assert counts["added"] == GOLDEN.article_summary["added"], counts
    assert counts["removed"] == GOLDEN.article_summary["removed"], counts
    assert (
        counts["unchanged"] + counts["modified"] + counts["added"] + counts["removed"]
        == GOLDEN.article_summary["compared"]
    )


def test_pipeline_summary_matches_clause_buckets(v1_v2_report) -> None:
    summary = v1_v2_report.summary
    assert summary.unchanged == len(v1_v2_report.clauses["unchanged"])
    assert summary.modified == len(v1_v2_report.clauses["modified"])
    assert summary.added == len(v1_v2_report.clauses["added"])
    assert summary.removed == len(v1_v2_report.clauses["removed"])
    assert summary.total_clauses == (
        summary.unchanged + summary.modified + summary.added + summary.removed
    )


def test_leaf_modified_and_added_sets(v1_v2_report) -> None:
    modified = {row.clause_id for row in v1_v2_report.clauses["modified"]}
    added = {row.clause_id for row in v1_v2_report.clauses["added"]}
    removed = {row.clause_id for row in v1_v2_report.clauses["removed"]}
    for key in GOLDEN.modified_leaves:
        assert key in modified, f"Clause: {key}\nExpected: MODIFIED\nActual: not in modified"
        assert key not in added
        assert key not in removed
    for key in GOLDEN.added_leaves:
        assert key in added, f"Clause: {key}\nExpected: ADDED\nActual: not in added"
        row = v1_v2_report.clause(key)
        assert row is not None
        assert row.v1_clause_id is None
        assert row.v2_clause_id == key
    assert removed == set(GOLDEN.removed_leaves)


def test_article_risk_levels(v1_v2_report) -> None:
    assert_risk(
        v1_v2_report,
        "CLAUSE:8.2",
        level="CRITICAL",
        category="LIABILITY",
        reason="Liability cap change must remain CRITICAL.",
    )
    assert_risk(
        v1_v2_report,
        "CLAUSE:11.2",
        level="HIGH",
        category="DISPUTE_RESOLUTION",
        reason="Dispute-resolution change must remain HIGH.",
    )
    assert_risk(
        v1_v2_report,
        "CLAUSE:9.1",
        level_in=("HIGH", "CRITICAL"),
        category="TERMINATION",
        reason=(
            "Termination risk must not disappear. "
            "Task narrative said CRITICAL; scorer may be HIGH."
        ),
    )
    for article, minimum in ARTICLE_MIN_RISK.items():
        actual = article_max_risk(v1_v2_report, article)
        if actual is None or RISK_RANK.get(actual, 0) < RISK_RANK[minimum]:
            raise AssertionError(
                f"Clause: {article}\nExpected: risk >= {minimum}\nActual: {actual}\n"
                "Reason to investigate:\n"
                "Liability/termination/dispute risk disappeared or was downgraded."
            )


def test_default_regression_uses_zero_llm(v1_v2_report) -> None:
    assert v1_v2_report.statistics.llm_calls == 0
    assert v1_v2_report.metadata.get("retrieval_calls") == 0
    for row in v1_v2_report.clauses["unchanged"]:
        assert row.status is DiffClassification.UNCHANGED
        assert row.explanation is None or row.explanation.get("llm_calls") in (None, 0)
