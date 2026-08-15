# =============================================================================
# File: report_types.py
# Module/Service: Contract Comparison Orchestration (FR8 / TASK-CMP-15)
# Layer: Schema
# Purpose: Runtime DTOs for an auditable clause-comparison report.
# Responsibilities:
#   - Clause-level aggregation of mapping/diff/exact/risk/evidence/LLM
#   - Deterministic summary statistics (never LLM-computed)
# Dependencies:
#   - diff_types, scoring_types, verification_types, llm_boundary_types
# Public Exports:
#   - ReportStatus, ClauseComparisonResult, ComparisonSummary,
#     ComparisonStatistics, DocumentRef, AuditableComparisonReport
# Database/Table: N/A (runtime; not comparisons.result OpenAPI shape)
# Related Modules: report_engine; FR8 ComparisonResult remains similarities/differences
# Important Notes:
#   - Source of truth is CMP-01..11. LLM fields are optional explanation only.
#   - as_dict() may include original clause text for authorized consumers;
#     services must never log that payload.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.ai.document_structure.diff_types import DiffClassification
from app.ai.document_structure.evaluation_types import QualityStatus
from app.ai.document_structure.scoring_types import RiskLevel


class ReportStatus(StrEnum):
    """Orchestrator outcome. Failed runs raise; this is for completed reports."""

    COMPLETED = "COMPLETED"
    PARTIAL_EXPLANATION = "PARTIAL_EXPLANATION"


@dataclass(frozen=True, slots=True)
class DocumentRef:
    """Identity of one compared version. No document body."""

    document_id: UUID
    document_version_id: UUID | None
    title: str | None = None
    workspace_id: UUID | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "document_id": str(self.document_id),
            "document_version_id": (
                str(self.document_version_id) if self.document_version_id else None
            ),
            "title": self.title,
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
        }


@dataclass
class ClauseComparisonResult:
    """One structural unit after the full deterministic pipeline."""

    clause_id: str
    v1_clause_id: str | None
    v2_clause_id: str | None
    status: DiffClassification
    mapping_confidence: float | None = None
    subtree_status: DiffClassification | None = None
    exact_differences: list[dict[str, Any]] = field(default_factory=list)
    risk: dict[str, Any] | None = None
    explanation: dict[str, Any] | None = None
    evidence: list[dict[str, Any]] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    verification: dict[str, Any] | None = None
    v1_text: str | None = None
    v2_text: str | None = None
    v1_normalized: str | None = None
    v2_normalized: str | None = None
    finding_id: str | None = None

    def as_dict(self, *, include_text: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "clause_id": self.clause_id,
            "v1_clause_id": self.v1_clause_id,
            "v2_clause_id": self.v2_clause_id,
            "status": self.status.value,
            "mapping_confidence": self.mapping_confidence,
            "subtree_status": (
                self.subtree_status.value if self.subtree_status else None
            ),
            "exact_differences": list(self.exact_differences),
            "risk": dict(self.risk) if self.risk else None,
            "explanation": dict(self.explanation) if self.explanation else None,
            "evidence": list(self.evidence),
            "citations": list(self.citations),
            "verification": dict(self.verification) if self.verification else None,
            "finding_id": self.finding_id,
        }
        if include_text:
            payload["v1_text"] = self.v1_text
            payload["v2_text"] = self.v2_text
            payload["v1_normalized"] = self.v1_normalized
            payload["v2_normalized"] = self.v2_normalized
        return payload


@dataclass(frozen=True, slots=True)
class ComparisonSummary:
    total_clauses: int
    unchanged: int
    modified: int
    added: int
    removed: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_clauses": self.total_clauses,
            "unchanged": self.unchanged,
            "modified": self.modified,
            "added": self.added,
            "removed": self.removed,
        }


@dataclass(frozen=True, slots=True)
class ComparisonStatistics:
    total_clauses_compared: int
    unchanged: int
    modified: int
    added: int
    removed: int
    unresolved: int
    mapped_clauses: int
    risk_counts: dict[str, int]
    llm_calls: int
    llm_tokens: int
    processing_time_ms: int
    verification_rate: float
    citation_verification_rate: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_clauses_compared": self.total_clauses_compared,
            "unchanged": self.unchanged,
            "modified": self.modified,
            "added": self.added,
            "removed": self.removed,
            "unresolved": self.unresolved,
            "mapped_clauses": self.mapped_clauses,
            "risk_counts": dict(self.risk_counts),
            "llm_calls": self.llm_calls,
            "llm_tokens": self.llm_tokens,
            "processing_time_ms": self.processing_time_ms,
            "verification_rate": self.verification_rate,
            "citation_verification_rate": self.citation_verification_rate,
        }


@dataclass
class AuditableComparisonReport:
    """End-to-end comparison report. Deterministic facts own classification."""

    comparison_id: UUID
    workspace_id: UUID | None
    document_v1: DocumentRef
    document_v2: DocumentRef
    created_at: datetime
    status: ReportStatus
    summary: ComparisonSummary
    statistics: ComparisonStatistics
    clauses: dict[str, list[ClauseComparisonResult]]
    risks: list[dict[str, Any]] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    explanation_incomplete: bool = False
    quality_status: QualityStatus = QualityStatus.PASS
    quality_reasons: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def clause(self, identity_key: str) -> ClauseComparisonResult | None:
        for bucket in self.clauses.values():
            for row in bucket:
                if row.clause_id == identity_key:
                    return row
                if row.v1_clause_id == identity_key or row.v2_clause_id == identity_key:
                    return row
        return None

    def as_dict(self, *, include_text: bool = True) -> dict[str, Any]:
        return {
            "comparison": {
                "metadata": {
                    "comparison_id": str(self.comparison_id),
                    "workspace_id": (
                        str(self.workspace_id) if self.workspace_id else None
                    ),
                    "document_v1": self.document_v1.as_dict(),
                    "document_v2": self.document_v2.as_dict(),
                    "created_at": self.created_at.isoformat(),
                    "status": self.status.value,
                    "quality_status": self.quality_status.value,
                    "quality_reasons": list(self.quality_reasons),
                    "explanation_incomplete": self.explanation_incomplete,
                },
                "summary": self.summary.as_dict(),
                "statistics": self.statistics.as_dict(),
                "clauses": {
                    name: [row.as_dict(include_text=include_text) for row in rows]
                    for name, rows in self.clauses.items()
                },
                "risks": list(self.risks),
                "citations": list(self.citations),
            },
            "metadata": dict(self.metadata),
        }


def empty_clause_buckets() -> dict[str, list[ClauseComparisonResult]]:
    return {
        "unchanged": [],
        "modified": [],
        "added": [],
        "removed": [],
        "unresolved": [],
    }


def bucket_name(status: DiffClassification) -> str:
    if status is DiffClassification.UNCHANGED:
        return "unchanged"
    if status is DiffClassification.MODIFIED:
        return "modified"
    if status is DiffClassification.ADDED:
        return "added"
    if status is DiffClassification.REMOVED:
        return "removed"
    return "unresolved"


def empty_risk_counts() -> dict[str, int]:
    return {
        RiskLevel.CRITICAL.value.lower(): 0,
        RiskLevel.HIGH.value.lower(): 0,
        RiskLevel.MEDIUM.value.lower(): 0,
        RiskLevel.LOW.value.lower(): 0,
    }
