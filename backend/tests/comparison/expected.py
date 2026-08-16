# =============================================================================
# File: expected.py
# Module/Service: Comparison Service (TASK-CMP-28)
# Layer: Test
# Purpose: Human-defined V1/V2 golden contract and assertion helpers.
# Responsibilities:
#   - Load structured labels from comparison_evaluation/v1_v2_regression.json
#   - Assert classification/risk/citation with expected-vs-actual messages
#   - Expose article/leaf rollups without inventing pipeline summary counts
# Dependencies:
#   - tests.fixtures.comparison_evaluation.ground_truth
#   - app.ai.document_structure report/diff/scoring types
# Public Exports:
#   - GOLDEN, assert_status, assert_not_status, assert_risk, classification_snapshot
# Database/Table: N/A
# Related Modules: tests/comparison, Hop_dong_mau_Ra_soat_Phap_ly_V*.txt
# Important Notes: Ground truth is the JSON contract, not current pipeline output.
# =============================================================================

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.ai.document_structure.diff_types import DiffClassification
from app.ai.document_structure.evaluation_types import ExpectedClause
from app.ai.document_structure.report_types import AuditableComparisonReport
from app.ai.document_structure.scoring_types import RiskLevel
from tests.fixtures.comparison_evaluation.ground_truth import v1_v2_expected_clauses

_GOLDEN_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "comparison_evaluation"
    / "v1_v2_regression.json"
)
RISK_RANK = {
    RiskLevel.LOW.value: 1,
    RiskLevel.MEDIUM.value: 2,
    RiskLevel.HIGH.value: 3,
    RiskLevel.CRITICAL.value: 4,
}
ARTICLE_KEYS = tuple(f"ARTICLE:{index}" for index in range(1, 13))
FORBIDDEN_ADDED = ("CLAUSE:1.2", "CLAUSE:1.3")
FALSE_NEGATIVE_KEYS = (
    "CLAUSE:2.1",
    "CLAUSE:3.1",
    "CLAUSE:8.2",
    "CLAUSE:9.1",
    "CLAUSE:11.2",
)


@dataclass(frozen=True, slots=True)
class GoldenContract:
    case_id: str
    expected: tuple[ExpectedClause, ...]
    article_summary: dict[str, int]
    modified_leaves: tuple[str, ...]
    added_leaves: tuple[str, ...]
    removed_leaves: tuple[str, ...]
    forbidden_added: tuple[str, ...]
    notes: tuple[str, ...]


def load_golden(path: Path | None = None) -> GoldenContract:
    target = path or _GOLDEN_PATH
    payload = json.loads(target.read_text(encoding="utf-8"))
    case_id, rows = v1_v2_expected_clauses()
    leaf = payload.get("leaf_summary") or {}
    return GoldenContract(
        case_id=case_id,
        expected=tuple(rows),
        article_summary=dict(payload.get("article_summary") or {}),
        modified_leaves=tuple(leaf.get("modified") or ()),
        added_leaves=tuple(leaf.get("added") or ()),
        removed_leaves=tuple(leaf.get("removed") or ()),
        forbidden_added=tuple(leaf.get("forbidden_added") or FORBIDDEN_ADDED),
        notes=tuple(payload.get("notes") or ()),
    )


GOLDEN = load_golden()


def row_status(row: Any, *, use_subtree: bool = False) -> str:
    if row is None:
        return "MISSING"
    if use_subtree and getattr(row, "subtree_status", None) is not None:
        return row.subtree_status.value
    status = getattr(row, "status", None)
    if hasattr(status, "value"):
        return str(status.value)
    return str(status or "MISSING")


def fail_clause(
    key: str,
    expected: str,
    actual: str,
    *,
    reason: str = "",
) -> None:
    detail = f"Clause: {key}\nExpected: {expected}\nActual: {actual}"
    if reason:
        detail = f"{detail}\nReason to investigate:\n{reason}"
    raise AssertionError(detail)


def assert_status(
    report: AuditableComparisonReport,
    key: str,
    expected: str,
    *,
    use_subtree: bool = False,
    reason: str = "",
) -> None:
    row = report.clause(key)
    actual = row_status(row, use_subtree=use_subtree)
    if actual != expected:
        fail_clause(key, expected, actual, reason=reason)


def assert_not_status(
    report: AuditableComparisonReport,
    key: str,
    forbidden: str,
    *,
    reason: str = "",
) -> None:
    row = report.clause(key)
    actual = row_status(row)
    if row is None:
        fail_clause(key, f"not {forbidden}", "MISSING", reason=reason)
    if actual == forbidden or row.status is DiffClassification[forbidden]:
        fail_clause(key, f"not {forbidden}", actual, reason=reason)


def assert_risk(
    report: AuditableComparisonReport,
    key: str,
    *,
    level: str | None = None,
    level_in: tuple[str, ...] = (),
    category: str | None = None,
    reason: str = "",
) -> None:
    row = report.clause(key)
    if row is None:
        fail_clause(key, f"risk {level or level_in or category}", "MISSING", reason=reason)
    risk = row.risk or {}
    actual_level = risk.get("risk_level")
    actual_category = risk.get("risk_category")
    if level and actual_level != level:
        fail_clause(key, f"risk_level {level}", str(actual_level), reason=reason)
    if level_in and actual_level not in level_in:
        fail_clause(
            key,
            f"risk_level in {level_in}",
            str(actual_level),
            reason=reason,
        )
    if category and actual_category != category:
        fail_clause(
            key,
            f"risk_category {category}",
            str(actual_category),
            reason=reason,
        )


def article_max_risk(report: AuditableComparisonReport, article_key: str) -> str | None:
    prefix = article_key.split(":", 1)[-1]
    levels: list[str] = []
    row = report.clause(article_key)
    if row and row.risk:
        level = row.risk.get("risk_level")
        if isinstance(level, str):
            levels.append(level)
    for bucket in report.clauses.values():
        for item in bucket:
            clause_id = str(item.clause_id or "")
            if clause_id.startswith(f"CLAUSE:{prefix}."):
                level = (item.risk or {}).get("risk_level")
                if isinstance(level, str):
                    levels.append(level)
    if not levels:
        return None
    return max(levels, key=lambda name: RISK_RANK.get(name, 0))


def classification_snapshot(report: AuditableComparisonReport) -> dict[str, str]:
    out: dict[str, str] = {}
    for bucket in report.clauses.values():
        for item in bucket:
            out[item.clause_id] = item.status.value
    return out


def article_rollup(report: AuditableComparisonReport) -> dict[str, int]:
    counts = {"unchanged": 0, "modified": 0, "added": 0, "removed": 0, "missing": 0}
    for key in ARTICLE_KEYS:
        row = report.clause(key)
        if row is None:
            counts["missing"] += 1
            continue
        status = row_status(row, use_subtree=True).lower()
        if status in counts:
            counts[status] += 1
    return counts
