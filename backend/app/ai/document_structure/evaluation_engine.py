# =============================================================================
# File: evaluation_engine.py
# Module/Service: Contract Comparison Quality Evaluation (FR8 / TASK-CMP-16)
# Layer: Adapter
# Purpose: Deterministic metrics and quality gate over a CMP-15 report.
# Responsibilities:
#   - Precision/recall/F1 vs structured ground truth
#   - Citation / LLM / ADDED-REMOVED false-positive rates
#   - Production quality gate (PASS / PASS_WITH_WARNINGS / FAIL)
# Dependencies:
#   - evaluation_types; report_types; diff_types
# Public Exports:
#   - score_classification, citation_metrics, llm_usage_metrics,
#     evaluate_report, apply_quality_gate, deterministic_fingerprint
# Database/Table: N/A
# Related Modules: ContractComparisonOrchestrator; ComparisonQualityEvaluator
# Important Notes:
#   - Does not call LLM, retrieval, or comparison engines.
#   - Ground truth is supplied by the caller (tests / eval fixtures).
# =============================================================================

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from app.ai.document_structure.diff_types import DiffClassification
from app.ai.document_structure.evaluation_types import (
    CitationQualityMetrics,
    ClassificationScore,
    DiffQualityMetrics,
    EvaluationResult,
    ExpectedClause,
    LlmUsageMetrics,
    MappingQualityMetrics,
    QualityReasonCode,
    QualityStatus,
)
from app.ai.document_structure.report_types import (
    AuditableComparisonReport,
    ClauseComparisonResult,
)
from app.ai.document_structure.scoring_types import RiskLevel
from app.ai.document_structure.verification_types import VerificationStatus

_DIFF_LABELS = (
    DiffClassification.UNCHANGED.value,
    DiffClassification.MODIFIED.value,
    DiffClassification.ADDED.value,
    DiffClassification.REMOVED.value,
)
_MEANINGFUL = frozenset(
    {
        DiffClassification.MODIFIED.value,
        DiffClassification.ADDED.value,
        DiffClassification.REMOVED.value,
    }
)
_VERIFIED = frozenset(
    {
        VerificationStatus.VERIFIED.value,
        VerificationStatus.PARTIALLY_VERIFIED.value,
    }
)


def score_classification(
    *,
    label: str,
    expected: Sequence[str],
    predicted: Sequence[str],
) -> ClassificationScore:
    """Binary one-vs-rest scores for a single diff class."""
    tp = fp = fn = tn = 0
    for exp, pred in zip(expected, predicted, strict=True):
        exp_pos = exp == label
        pred_pos = pred == label
        if pred_pos and exp_pos:
            tp += 1
        elif pred_pos and not exp_pos:
            fp += 1
        elif (not pred_pos) and exp_pos:
            fn += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return ClassificationScore(
        label=label,
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        true_negatives=tn,
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
    )


def diff_metrics(expected: Sequence[str], predicted: Sequence[str]) -> DiffQualityMetrics:
    by_class = {
        label: score_classification(label=label, expected=expected, predicted=predicted)
        for label in _DIFF_LABELS
    }
    total = len(expected)
    correct = sum(1 for exp, pred in zip(expected, predicted, strict=True) if exp == pred)
    accuracy = correct / total if total else 1.0
    scores = list(by_class.values())
    macro_p = sum(item.precision for item in scores) / len(scores)
    macro_r = sum(item.recall for item in scores) / len(scores)
    macro_f = sum(item.f1 for item in scores) / len(scores)
    added = by_class[DiffClassification.ADDED.value]
    removed = by_class[DiffClassification.REMOVED.value]
    added_fpr = (
        added.false_positives / (added.false_positives + added.true_negatives)
        if (added.false_positives + added.true_negatives)
        else 0.0
    )
    removed_fpr = (
        removed.false_positives / (removed.false_positives + removed.true_negatives)
        if (removed.false_positives + removed.true_negatives)
        else 0.0
    )
    return DiffQualityMetrics(
        accuracy=round(accuracy, 4),
        macro_precision=round(macro_p, 4),
        macro_recall=round(macro_r, 4),
        macro_f1=round(macro_f, 4),
        added_false_positive_rate=round(added_fpr, 4),
        removed_false_positive_rate=round(removed_fpr, 4),
        by_class=by_class,
    )


def citation_metrics(report: AuditableComparisonReport) -> CitationQualityMetrics:
    verified = partial = invalid = insufficient = missing = findings = 0
    for row in iter_clauses(report):
        if row.status.value not in _MEANINGFUL:
            continue
        findings += 1
        status = (row.verification or {}).get("status")
        if status == VerificationStatus.VERIFIED.value:
            verified += 1
        elif status == VerificationStatus.PARTIALLY_VERIFIED.value:
            partial += 1
        elif status == VerificationStatus.INVALID.value:
            invalid += 1
        elif status == VerificationStatus.INSUFFICIENT_EVIDENCE.value:
            insufficient += 1
        else:
            missing += 1
    denom = findings or 1
    valid = verified + partial
    return CitationQualityMetrics(
        findings=findings,
        verified=verified,
        partially_verified=partial,
        invalid=invalid,
        insufficient=insufficient,
        missing=missing,
        verification_rate=round(valid / denom, 4) if findings else 1.0,
        valid_evidence_rate=round(valid / denom, 4) if findings else 1.0,
        invalid_evidence_rate=round(invalid / denom, 4) if findings else 0.0,
        missing_evidence_rate=round(missing / denom, 4) if findings else 0.0,
    )


def llm_usage_metrics(
    report: AuditableComparisonReport,
    *,
    estimated_cost_usd: float | None = None,
) -> LlmUsageMetrics:
    unchanged_calls = 0
    for row in report.clauses.get("unchanged", []):
        payload = row.explanation or {}
        unchanged_calls += int(payload.get("llm_calls") or 0)
    modified = max(1, report.summary.modified)
    return LlmUsageMetrics(
        calls=report.statistics.llm_calls,
        tokens=report.statistics.llm_tokens,
        estimated_cost_usd=estimated_cost_usd,
        calls_per_modified_clause=round(report.statistics.llm_calls / modified, 4),
        unchanged_llm_calls=unchanged_calls,
    )


def evaluate_report(
    report: AuditableComparisonReport,
    expected: Sequence[ExpectedClause],
    *,
    case_id: str = "adhoc",
    max_llm_calls: int = 8,
    estimated_cost_usd: float | None = None,
) -> EvaluationResult:
    """Score a report against structured labels. Does not call engines."""
    mismatches: list[str] = []
    expected_status: list[str] = []
    predicted_status: list[str] = []
    mapping_expected = 0
    mapping_correct = 0
    for item in expected:
        row = report.clause(item.identity_key)
        if row is None:
            mismatches.append(f"{item.identity_key}: missing from report")
            if item.status:
                expected_status.append(item.status)
                predicted_status.append("MISSING")
            continue
        actual_status = row.status.value
        if item.use_subtree and row.subtree_status is not None:
            actual_status = row.subtree_status.value
        if item.status:
            expected_status.append(item.status)
            predicted_status.append(actual_status)
            if actual_status != item.status:
                mismatches.append(
                    f"{item.identity_key}: expected {item.status} got {actual_status}"
                )
        for forbidden in item.forbidden_statuses:
            if actual_status == forbidden or row.status.value == forbidden:
                mismatches.append(f"{item.identity_key}: forbidden status {forbidden}")
        if item.mapped_v2_key:
            mapping_expected += 1
            if row.v2_clause_id == item.mapped_v2_key:
                mapping_correct += 1
            else:
                mismatches.append(
                    f"{item.identity_key}: mapped {row.v2_clause_id} "
                    f"expected {item.mapped_v2_key}"
                )
        if item.require_null_v1 and row.v1_clause_id is not None:
            mismatches.append(f"{item.identity_key}: v1_clause_id must be null")
        if item.require_null_v2 and row.v2_clause_id is not None:
            mismatches.append(f"{item.identity_key}: v2_clause_id must be null")
        if item.v1_clause_id is not None and row.v1_clause_id != item.v1_clause_id:
            mismatches.append(f"{item.identity_key}: v1_clause_id mismatch")
        if item.v2_clause_id is not None and row.v2_clause_id != item.v2_clause_id:
            mismatches.append(f"{item.identity_key}: v2_clause_id mismatch")
        if item.risk_category:
            category = (row.risk or {}).get("risk_category")
            if category != item.risk_category:
                mismatches.append(
                    f"{item.identity_key}: risk_category {category} "
                    f"expected {item.risk_category}"
                )
        if item.risk_level_in:
            level = (row.risk or {}).get("risk_level")
            if level not in item.risk_level_in:
                mismatches.append(
                    f"{item.identity_key}: risk_level {level} not in {item.risk_level_in}"
                )
        if item.exact_value_types:
            types = {change.get("value_type") for change in row.exact_differences}
            missing_types = [name for name in item.exact_value_types if name not in types]
            if missing_types:
                mismatches.append(
                    f"{item.identity_key}: missing exact types {missing_types}"
                )
        if item.require_citations and not row.citations:
            status = (row.verification or {}).get("status")
            if status in _VERIFIED:
                mismatches.append(f"{item.identity_key}: verified but no citations")

    diff = diff_metrics(expected_status, predicted_status) if expected_status else None
    mapping = MappingQualityMetrics(
        expected_pairs=mapping_expected,
        correct_pairs=mapping_correct,
        accuracy=(
            round(mapping_correct / mapping_expected, 4) if mapping_expected else 1.0
        ),
    )
    citations = citation_metrics(report)
    llm = llm_usage_metrics(report, estimated_cost_usd=estimated_cost_usd)
    gated = apply_quality_gate(report, max_llm_calls=max_llm_calls)
    reasons = list(gated.quality_reasons)
    if mismatches:
        reasons.append("GROUND_TRUTH_MISMATCH")
    if llm.unchanged_llm_calls:
        reasons.append(QualityReasonCode.UNCHANGED_LLM_USED.value)
    status = gated.quality_status
    if mismatches or llm.unchanged_llm_calls:
        status = QualityStatus.FAIL
    return EvaluationResult(
        case_id=case_id,
        quality_status=status,
        reasons=tuple(dict.fromkeys(reasons)),
        mismatches=mismatches,
        diff=diff,
        mapping=mapping,
        citation=citations,
        llm=llm,
        latency_ms=report.statistics.processing_time_ms,
        metadata={"comparison_id": str(report.comparison_id)},
    )


def apply_quality_gate(
    report: AuditableComparisonReport,
    *,
    max_llm_calls: int = 8,
) -> AuditableComparisonReport:
    """Attach quality_status. Failures are architectural; warnings are optional."""
    failures: list[str] = []
    warnings: list[str] = []

    if (
        report.summary.unchanged != len(report.clauses.get("unchanged", []))
        or report.summary.modified != len(report.clauses.get("modified", []))
        or report.summary.added != len(report.clauses.get("added", []))
        or report.summary.removed != len(report.clauses.get("removed", []))
        or report.summary.total_clauses
        != (
            report.summary.unchanged
            + report.summary.modified
            + report.summary.added
            + report.summary.removed
        )
    ):
        failures.append(QualityReasonCode.SUMMARY_MISMATCH.value)

    meta = report.metadata or {}
    deterministic_llm = int(meta.get("mapping_llm_calls") or 0) + int(
        meta.get("diff_llm_calls") or 0
    ) + int(meta.get("exact_diff_llm_calls") or 0)
    if deterministic_llm > 0:
        failures.append(QualityReasonCode.DETERMINISTIC_LLM_USED.value)
    if int(meta.get("retrieval_calls") or 0) > 0:
        failures.append(QualityReasonCode.RETRIEVAL_USED_FOR_EXISTENCE.value)

    allowed_docs = {
        report.document_v1.document_id,
        report.document_v2.document_id,
    }
    allowed_ws = {
        item
        for item in (report.workspace_id, report.document_v1.workspace_id, report.document_v2.workspace_id)
        if item is not None
    }
    for row in iter_clauses(report):
        level = (row.risk or {}).get("risk_level")
        status = (row.verification or {}).get("status")
        if (
            level == RiskLevel.CRITICAL.value
            and status == VerificationStatus.INVALID.value
        ):
            failures.append(QualityReasonCode.CRITICAL_EVIDENCE_INVALID.value)
        if (
            row.status.value in {DiffClassification.ADDED.value, DiffClassification.REMOVED.value}
            and status == VerificationStatus.INSUFFICIENT_EVIDENCE.value
        ):
            warnings.append(QualityReasonCode.INSUFFICIENT_ABSENCE_EVIDENCE.value)
        for item in (*row.evidence, *row.citations):
            doc = item.get("document_id")
            if doc:
                try:
                    doc_id = UUID(str(doc))
                except ValueError:
                    failures.append(QualityReasonCode.EVIDENCE_WORKSPACE_LEAK.value)
                    continue
                if doc_id not in allowed_docs:
                    failures.append(QualityReasonCode.EVIDENCE_WORKSPACE_LEAK.value)
            ws = item.get("workspace_id")
            if ws and allowed_ws:
                try:
                    ws_id = UUID(str(ws))
                except ValueError:
                    failures.append(QualityReasonCode.EVIDENCE_WORKSPACE_LEAK.value)
                    continue
                if ws_id not in allowed_ws:
                    failures.append(QualityReasonCode.EVIDENCE_WORKSPACE_LEAK.value)

    if report.statistics.llm_calls > max_llm_calls:
        warnings.append(QualityReasonCode.LLM_BUDGET_EXCEEDED.value)
    if report.explanation_incomplete:
        warnings.append(QualityReasonCode.EXPLANATION_INCOMPLETE.value)
    if report.statistics.unresolved:
        warnings.append(QualityReasonCode.UNRESOLVED_CLAUSES.value)
    for row in report.clauses.get("unchanged", []):
        if int((row.explanation or {}).get("llm_calls") or 0) > 0:
            failures.append(QualityReasonCode.UNCHANGED_LLM_USED.value)

    unique_fail = tuple(dict.fromkeys(failures))
    unique_warn = tuple(dict.fromkeys(warnings))
    if unique_fail:
        report.quality_status = QualityStatus.FAIL
        report.quality_reasons = unique_fail + unique_warn
    elif unique_warn:
        report.quality_status = QualityStatus.PASS_WITH_WARNINGS
        report.quality_reasons = unique_warn
    else:
        report.quality_status = QualityStatus.PASS
        report.quality_reasons = ()
    return report


def deterministic_fingerprint(report: AuditableComparisonReport) -> dict[str, Any]:
    """Stable payload for repeatability tests (excludes ids / clocks / latency)."""
    clauses = []
    for row in iter_clauses(report):
        clauses.append(
            (
                row.clause_id,
                row.v1_clause_id,
                row.v2_clause_id,
                row.status.value,
                row.subtree_status.value if row.subtree_status else None,
                tuple(
                    (
                        item.get("value_type"),
                        item.get("change_type"),
                        item.get("delta"),
                        item.get("relative_change_percent"),
                    )
                    for item in row.exact_differences
                ),
                (row.risk or {}).get("risk_category"),
                (row.risk or {}).get("risk_level"),
            )
        )
    clauses.sort()
    return {
        "summary": report.summary.as_dict(),
        "clauses": clauses,
        "risks": sorted(
            (
                item.get("identity_key"),
                item.get("risk_category"),
                item.get("risk_level"),
            )
            for item in report.risks
        ),
        "added": sorted(row.clause_id for row in report.clauses.get("added", [])),
        "removed": sorted(row.clause_id for row in report.clauses.get("removed", [])),
        "llm_calls": report.statistics.llm_calls,
        "retrieval_calls": (report.metadata or {}).get("retrieval_calls", 0),
    }


def iter_clauses(
    report: AuditableComparisonReport,
) -> list[ClauseComparisonResult]:
    rows: list[ClauseComparisonResult] = []
    for bucket in (
        "unchanged",
        "modified",
        "added",
        "removed",
        "unresolved",
    ):
        rows.extend(report.clauses.get(bucket, []))
    return rows
