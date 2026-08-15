# =============================================================================
# File: evaluation_types.py
# Module/Service: Contract Comparison Quality Evaluation (FR8 / TASK-CMP-16)
# Layer: Schema
# Purpose: Ground-truth and metric DTOs for measuring comparison quality.
# Responsibilities:
#   - Quality gate status; precision/recall/F1 containers
#   - Structured expected-clause labels (never LLM-judged)
# Dependencies:
#   - stdlib dataclasses / enum
# Public Exports:
#   - QualityStatus, ClassificationScore, DiffQualityMetrics,
#     MappingQualityMetrics, CitationQualityMetrics, LlmUsageMetrics,
#     ExpectedClause, EvaluationResult
# Database/Table: N/A (runtime / tests; not persisted)
# Related Modules: evaluation_engine; FR8 ComparisonResult unchanged
# Important Notes:
#   - Ground truth lives in tests/fixtures, not in production engines.
#   - Do not use an LLM to decide numeric or existence assertions.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class QualityStatus(StrEnum):
    """Production gate for a completed comparison report."""

    PASS = "PASS"
    PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"
    FAIL = "FAIL"


class QualityReasonCode(StrEnum):
    SUMMARY_MISMATCH = "SUMMARY_MISMATCH"
    DETERMINISTIC_LLM_USED = "DETERMINISTIC_LLM_USED"
    RETRIEVAL_USED_FOR_EXISTENCE = "RETRIEVAL_USED_FOR_EXISTENCE"
    CRITICAL_EVIDENCE_INVALID = "CRITICAL_EVIDENCE_INVALID"
    EVIDENCE_WORKSPACE_LEAK = "EVIDENCE_WORKSPACE_LEAK"
    LLM_BUDGET_EXCEEDED = "LLM_BUDGET_EXCEEDED"
    EXPLANATION_INCOMPLETE = "EXPLANATION_INCOMPLETE"
    INSUFFICIENT_ABSENCE_EVIDENCE = "INSUFFICIENT_ABSENCE_EVIDENCE"
    UNRESOLVED_CLAUSES = "UNRESOLVED_CLAUSES"
    UNCHANGED_LLM_USED = "UNCHANGED_LLM_USED"


@dataclass(frozen=True, slots=True)
class ClassificationScore:
    """Precision / recall / F1 for one diff class."""

    label: str
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int
    precision: float
    recall: float
    f1: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "true_negatives": self.true_negatives,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
        }


@dataclass(frozen=True, slots=True)
class DiffQualityMetrics:
    accuracy: float
    macro_precision: float
    macro_recall: float
    macro_f1: float
    added_false_positive_rate: float
    removed_false_positive_rate: float
    by_class: dict[str, ClassificationScore]

    def as_dict(self) -> dict[str, Any]:
        return {
            "accuracy": self.accuracy,
            "macro_precision": self.macro_precision,
            "macro_recall": self.macro_recall,
            "macro_f1": self.macro_f1,
            "added_false_positive_rate": self.added_false_positive_rate,
            "removed_false_positive_rate": self.removed_false_positive_rate,
            "by_class": {key: value.as_dict() for key, value in self.by_class.items()},
        }


@dataclass(frozen=True, slots=True)
class MappingQualityMetrics:
    expected_pairs: int
    correct_pairs: int
    accuracy: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "expected_pairs": self.expected_pairs,
            "correct_pairs": self.correct_pairs,
            "accuracy": self.accuracy,
        }


@dataclass(frozen=True, slots=True)
class CitationQualityMetrics:
    findings: int
    verified: int
    partially_verified: int
    invalid: int
    insufficient: int
    missing: int
    verification_rate: float
    valid_evidence_rate: float
    invalid_evidence_rate: float
    missing_evidence_rate: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "findings": self.findings,
            "verified": self.verified,
            "partially_verified": self.partially_verified,
            "invalid": self.invalid,
            "insufficient": self.insufficient,
            "missing": self.missing,
            "verification_rate": self.verification_rate,
            "valid_evidence_rate": self.valid_evidence_rate,
            "invalid_evidence_rate": self.invalid_evidence_rate,
            "missing_evidence_rate": self.missing_evidence_rate,
        }


@dataclass(frozen=True, slots=True)
class LlmUsageMetrics:
    calls: int
    tokens: int
    estimated_cost_usd: float | None
    calls_per_modified_clause: float
    unchanged_llm_calls: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "tokens": self.tokens,
            "estimated_cost_usd": self.estimated_cost_usd,
            "calls_per_modified_clause": self.calls_per_modified_clause,
            "unchanged_llm_calls": self.unchanged_llm_calls,
        }


@dataclass(frozen=True, slots=True)
class ExpectedClause:
    """Structured label for one identity key. Not a snapshot of LLM prose."""

    identity_key: str
    status: str | None = None
    forbidden_statuses: tuple[str, ...] = ()
    mapped_v2_key: str | None = None
    risk_category: str | None = None
    risk_level_in: tuple[str, ...] = ()
    exact_value_types: tuple[str, ...] = ()
    require_citations: bool = False
    v1_clause_id: str | None = None
    v2_clause_id: str | None = None
    require_null_v1: bool = False
    require_null_v2: bool = False
    use_subtree: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "identity_key": self.identity_key,
            "status": self.status,
            "forbidden_statuses": list(self.forbidden_statuses),
            "mapped_v2_key": self.mapped_v2_key,
            "risk_category": self.risk_category,
            "risk_level_in": list(self.risk_level_in),
            "exact_value_types": list(self.exact_value_types),
            "require_citations": self.require_citations,
            "v1_clause_id": self.v1_clause_id,
            "v2_clause_id": self.v2_clause_id,
        }


@dataclass
class EvaluationResult:
    """Scored comparison against structured ground truth."""

    case_id: str
    quality_status: QualityStatus
    reasons: tuple[str, ...]
    mismatches: list[str]
    diff: DiffQualityMetrics | None
    mapping: MappingQualityMetrics | None
    citation: CitationQualityMetrics
    llm: LlmUsageMetrics
    latency_ms: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "quality_status": self.quality_status.value,
            "reasons": list(self.reasons),
            "mismatches": list(self.mismatches),
            "diff": self.diff.as_dict() if self.diff else None,
            "mapping": self.mapping.as_dict() if self.mapping else None,
            "citation": self.citation.as_dict(),
            "llm": self.llm.as_dict(),
            "latency_ms": self.latency_ms,
            "metadata": dict(self.metadata),
        }
