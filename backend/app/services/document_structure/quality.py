# =============================================================================
# File: quality.py
# Module/Service: Contract Comparison Quality Evaluation (FR8 / TASK-CMP-16)
# Layer: Service
# Purpose: Application wrapper that scores a CMP-15 report against labels
#   and records in-process quality metrics. Does not re-run comparison.
# Responsibilities:
#   - evaluate(report, expected) → EvaluationResult
#   - gate(report) → report with quality_status
#   - Log counts only — never contract body / PII
# Dependencies:
#   - evaluation_engine, quality_metrics, optional Settings cost estimate
# Public Exports:
#   - ComparisonQualityEvaluator
# Database/Table: N/A
# Related Modules: ContractComparisonOrchestrator
# Important Notes: Not a second comparison pipeline. 0 LLM. 0 retrieval.
# =============================================================================

from __future__ import annotations

from collections.abc import Sequence

from app.ai.document_structure.evaluation_engine import apply_quality_gate, evaluate_report
from app.ai.document_structure.evaluation_types import EvaluationResult, ExpectedClause
from app.ai.document_structure.quality_metrics import get_contract_comparison_metrics
from app.ai.document_structure.report_types import AuditableComparisonReport
from app.core.logging import get_logger

logger = get_logger(__name__)


class ComparisonQualityEvaluator:
    """Score and gate an existing comparison report."""

    def __init__(self, *, max_llm_calls: int = 8) -> None:
        self._max_llm_calls = max_llm_calls

    def gate(
        self,
        report: AuditableComparisonReport,
        *,
        max_llm_calls: int | None = None,
    ) -> AuditableComparisonReport:
        gated = apply_quality_gate(
            report,
            max_llm_calls=self._max_llm_calls if max_llm_calls is None else max_llm_calls,
        )
        logger.info(
            "contract_comparison_quality_gated",
            comparison_id=str(gated.comparison_id),
            quality_status=gated.quality_status.value,
            quality_reason_count=len(gated.quality_reasons),
            llm_calls=gated.statistics.llm_calls,
        )
        return gated

    def evaluate(
        self,
        report: AuditableComparisonReport,
        expected: Sequence[ExpectedClause],
        *,
        case_id: str = "adhoc",
        estimated_cost_usd: float | None = None,
        max_llm_calls: int | None = None,
    ) -> EvaluationResult:
        result = evaluate_report(
            report,
            expected,
            case_id=case_id,
            max_llm_calls=self._max_llm_calls if max_llm_calls is None else max_llm_calls,
            estimated_cost_usd=estimated_cost_usd,
        )
        added = result.diff.by_class.get("ADDED") if result.diff else None
        removed = result.diff.by_class.get("REMOVED") if result.diff else None
        get_contract_comparison_metrics().record_eval_errors(
            false_positives=(
                (added.false_positives if added else 0)
                + (removed.false_positives if removed else 0)
            ),
            false_negatives=(
                (added.false_negatives if added else 0)
                + (removed.false_negatives if removed else 0)
            ),
        )
        logger.info(
            "contract_comparison_evaluated",
            case_id=case_id,
            quality_status=result.quality_status.value,
            mismatch_count=len(result.mismatches),
            llm_calls=result.llm.calls,
            llm_tokens=result.llm.tokens,
            latency_ms=result.latency_ms,
            added_false_positive_rate=(
                result.diff.added_false_positive_rate if result.diff else None
            ),
            removed_false_positive_rate=(
                result.diff.removed_false_positive_rate if result.diff else None
            ),
        )
        return result
