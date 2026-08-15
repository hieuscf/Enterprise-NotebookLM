# =============================================================================
# File: quality_metrics.py
# Module/Service: Contract Comparison Quality Evaluation (FR8 / TASK-CMP-16)
# Layer: Adapter
# Purpose: In-process counters for clause-comparison observability.
# Responsibilities:
#   - Track totals, outcomes, clause buckets, LLM usage, citation, latency
# Dependencies:
#   - threading (same pattern as FR5 / FR14; no Prometheus exporter yet)
# Public Exports:
#   - ContractComparisonMetrics, get_contract_comparison_metrics,
#     reset_contract_comparison_metrics_for_tests
# Database/Table: N/A
# Related Modules: orchestrator, evaluation_engine
# Important Notes: Project has no Prometheus exporter — in-process only.
# =============================================================================

from __future__ import annotations

import threading
from collections import defaultdict

from app.ai.document_structure.evaluation_types import QualityStatus
from app.ai.document_structure.report_types import AuditableComparisonReport

METRIC_COMPARISON_TOTAL = "comparison.total"
METRIC_COMPARISON_SUCCESS = "comparison.success"
METRIC_COMPARISON_FAILURE = "comparison.failure"
METRIC_COMPARISON_QUALITY_FAIL = "comparison.quality_fail"
METRIC_CLAUSES_TOTAL = "comparison.clauses.total"
METRIC_CLAUSES_UNCHANGED = "comparison.clauses.unchanged"
METRIC_CLAUSES_MODIFIED = "comparison.clauses.modified"
METRIC_CLAUSES_ADDED = "comparison.clauses.added"
METRIC_CLAUSES_REMOVED = "comparison.clauses.removed"
METRIC_LLM_CALLS = "comparison.llm.calls"
METRIC_LLM_TOKENS = "comparison.llm.tokens"
METRIC_CITATION_VERIFIED = "comparison.citation.verified"
METRIC_CITATION_FAILED = "comparison.citation.failed"
METRIC_DURATION_MS = "comparison.duration"
METRIC_FALSE_POSITIVE = "comparison.false_positive"
METRIC_FALSE_NEGATIVE = "comparison.false_negative"


class ContractComparisonMetrics:
    """Thread-safe CMP-16 counters (in-process until a metrics backend lands)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, float] = defaultdict(float)

    def record_success(self, report: AuditableComparisonReport) -> None:
        citations = report.statistics.citation_verification_rate
        verified = int(round(citations * max(0, report.summary.modified + report.summary.added + report.summary.removed)))
        failed = max(0, (report.summary.modified + report.summary.added + report.summary.removed) - verified)
        with self._lock:
            self._counters[METRIC_COMPARISON_TOTAL] += 1
            self._counters[METRIC_COMPARISON_SUCCESS] += 1
            if report.quality_status is QualityStatus.FAIL:
                self._counters[METRIC_COMPARISON_QUALITY_FAIL] += 1
            self._counters[METRIC_CLAUSES_TOTAL] += float(report.summary.total_clauses)
            self._counters[METRIC_CLAUSES_UNCHANGED] += float(report.summary.unchanged)
            self._counters[METRIC_CLAUSES_MODIFIED] += float(report.summary.modified)
            self._counters[METRIC_CLAUSES_ADDED] += float(report.summary.added)
            self._counters[METRIC_CLAUSES_REMOVED] += float(report.summary.removed)
            self._counters[METRIC_LLM_CALLS] += float(report.statistics.llm_calls)
            self._counters[METRIC_LLM_TOKENS] += float(report.statistics.llm_tokens)
            self._counters[METRIC_CITATION_VERIFIED] += float(verified)
            self._counters[METRIC_CITATION_FAILED] += float(failed)
            self._counters[METRIC_DURATION_MS] += float(max(0, report.statistics.processing_time_ms))

    def record_failure(self) -> None:
        with self._lock:
            self._counters[METRIC_COMPARISON_TOTAL] += 1
            self._counters[METRIC_COMPARISON_FAILURE] += 1

    def record_eval_errors(self, *, false_positives: int, false_negatives: int) -> None:
        with self._lock:
            self._counters[METRIC_FALSE_POSITIVE] += float(max(0, false_positives))
            self._counters[METRIC_FALSE_NEGATIVE] += float(max(0, false_negatives))

    def snapshot(self) -> dict[str, float]:
        with self._lock:
            return dict(self._counters)


_metrics: ContractComparisonMetrics | None = None
_lock = threading.Lock()


def get_contract_comparison_metrics() -> ContractComparisonMetrics:
    global _metrics
    with _lock:
        if _metrics is None:
            _metrics = ContractComparisonMetrics()
        return _metrics


def reset_contract_comparison_metrics_for_tests() -> None:
    """Clear CMP-16 counters (tests only)."""
    global _metrics
    with _lock:
        _metrics = ContractComparisonMetrics()
