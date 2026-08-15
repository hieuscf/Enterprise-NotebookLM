# =============================================================================
# File: scoring_types.py
# Module/Service: Risk Scoring Engine (FR8 / TASK-CMP-08)
# Layer: Service
# Purpose: Domain types for deterministic risk score / level after CMP-07.
# Responsibilities:
#   - Canonical LOW/MEDIUM/HIGH/CRITICAL; impact ≠ level; status ≠ level
#   - Auditable factor breakdown; CMP-09 RiskAdjustment hook (unused here)
# Dependencies:
#   - taxonomy_types.RiskCategory; mapping_types.ClauseRef
# Public Exports:
#   - RiskLevel, RiskImpact, RiskStatus, RiskPerspective, ScoreFactor,
#     RiskAdjustment, RiskScoreResult, RiskScoringResult
# Database/Table: N/A (runtime domain; not persisted)
# Related Modules: scoring_engine; CMP-09 consumes RiskScoreResult
# Important Notes:
#   - Score is a system decision-support signal, not legal advice.
#   - risk_level is never inferred from category alone. 0 LLM.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.ai.document_structure.diff_types import DiffClassification
from app.ai.document_structure.mapping_types import ClauseRef
from app.ai.document_structure.taxonomy_types import (
    ClassificationConfidence,
    RiskCategory,
)


class RiskLevel(StrEnum):
    """Canonical severity bands. Mapped only from score + thresholds."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskImpact(StrEnum):
    """Direction of exposure change. Not a severity label."""

    RISK_INCREASING = "RISK_INCREASING"
    RISK_DECREASING = "RISK_DECREASING"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"


class RiskStatus(StrEnum):
    """Operational scoring status. Not a risk level."""

    SCORED = "SCORED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"


class RiskPerspective(StrEnum):
    """Who the score is computed for. Default UNKNOWN — never invent Buyer/Seller."""

    UNKNOWN = "UNKNOWN"
    NEUTRAL = "NEUTRAL"


class ScoringConfidence(StrEnum):
    """How complete the scoring inputs were — not classification_confidence."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


SCORING_VERSION = "v1"


@dataclass(frozen=True, slots=True)
class ScoreFactor:
    """One auditable contribution. Deltas must sum to final_score after clamp."""

    factor: str
    delta: float
    source: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "factor": self.factor,
            "delta": _score_str(self.delta),
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class RiskAdjustment:
    """Placeholder for CMP-09. CMP-08 does not emit contract-specific rules."""

    rule_id: str
    delta: float
    reason_code: str
    source: str = "CMP-09"

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "delta": _score_str(self.delta),
            "reason_code": self.reason_code,
            "source": self.source,
        }


@dataclass
class RiskScoreResult:
    """One clause scored. Facts only — no recommendation or narrative."""

    risk_score: float
    risk_level: RiskLevel
    risk_impact: RiskImpact
    base_score: float
    score_breakdown: tuple[ScoreFactor, ...]
    scoring_confidence: ScoringConfidence
    scoring_version: str
    status: RiskStatus
    category: RiskCategory
    classification_confidence: ClassificationConfidence
    perspective: RiskPerspective
    identity_key: str | None
    diff_classification: DiffClassification | None
    source_ref: ClauseRef | None
    target_ref: ClauseRef | None
    pending_adjustments: tuple[RiskAdjustment, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "risk_score": _score_str(self.risk_score),
            "risk_level": self.risk_level.value,
            "risk_impact": self.risk_impact.value,
            "base_score": _score_str(self.base_score),
            "score_breakdown": [item.as_dict() for item in self.score_breakdown],
            "scoring_confidence": self.scoring_confidence.value,
            "scoring_version": self.scoring_version,
            "status": self.status.value,
            "category": self.category.value,
            "classification_confidence": self.classification_confidence.value,
            "perspective": self.perspective.value,
            "identity_key": self.identity_key,
            "diff_classification": (
                self.diff_classification.value if self.diff_classification else None
            ),
            "pending_adjustments": [item.as_dict() for item in self.pending_adjustments],
            "source_ref": self.source_ref.as_dict() if self.source_ref else None,
            "target_ref": self.target_ref.as_dict() if self.target_ref else None,
        }


@dataclass
class RiskScoringResult:
    """Batch scores for a TaxonomyResult. Independent of RAG / LLM."""

    source_document_id: UUID
    target_document_id: UUID
    source_version_id: UUID | None
    target_version_id: UUID | None
    scores: list[RiskScoreResult] = field(default_factory=list)
    scoring_version: str = SCORING_VERSION
    metadata: dict[str, Any] = field(default_factory=dict)

    def for_source(self, identity_key: str) -> RiskScoreResult | None:
        for row in self.scores:
            if row.identity_key == identity_key or (
                row.source_ref and row.source_ref.identity_key == identity_key
            ):
                return row
        return None

    def for_target(self, identity_key: str) -> RiskScoreResult | None:
        for row in self.scores:
            if row.target_ref and row.target_ref.identity_key == identity_key:
                return row
        return None

    def by_level(self, level: RiskLevel) -> list[RiskScoreResult]:
        return [row for row in self.scores if row.risk_level is level]

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_document_id": str(self.source_document_id),
            "target_document_id": str(self.target_document_id),
            "source_version_id": (
                str(self.source_version_id) if self.source_version_id else None
            ),
            "target_version_id": (
                str(self.target_version_id) if self.target_version_id else None
            ),
            "scoring_version": self.scoring_version,
            "scores": [row.as_dict() for row in self.scores],
            "metadata": dict(self.metadata),
        }


def _score_str(value: float) -> float:
    return round(float(value), 1)
