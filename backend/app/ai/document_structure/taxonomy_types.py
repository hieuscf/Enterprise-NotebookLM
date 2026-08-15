# =============================================================================
# File: taxonomy_types.py
# Module/Service: Legal Risk Taxonomy (FR8 / TASK-CMP-07)
# Layer: Service
# Purpose: Domain types for deterministic legal-domain classification after CMP-06.
# Responsibilities:
#   - Canonical 14-category taxonomy; assignment + result containers
#   - Classification confidence is NOT a risk level (CMP-08 owns scoring)
# Dependencies:
#   - mapping_types.ClauseRef; exact_types.ValueType; diff_types.DiffClassification
# Public Exports:
#   - RiskCategory, ClassificationConfidence, ClassificationMethod,
#     ClassificationStatus, TaxonomyAssignment, TaxonomyResult
# Database/Table: N/A (runtime domain; not persisted)
# Related Modules: taxonomy_engine; CMP-08 consumes assignments only
# Important Notes:
#   - risk_level is always NOT_ASSIGNED. No LLM. No legal advice text.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.ai.document_structure.diff_types import DiffClassification
from app.ai.document_structure.exact_types import ValueType
from app.ai.document_structure.mapping_types import ClauseRef


class RiskCategory(StrEnum):
    """Canonical CMP-07 taxonomy. Do not rename. Do not treat as severity."""

    FINANCIAL = "FINANCIAL"
    LIABILITY = "LIABILITY"
    TERMINATION = "TERMINATION"
    PAYMENT = "PAYMENT"
    CONTRACT_TERM = "CONTRACT_TERM"
    CONFIDENTIALITY = "CONFIDENTIALITY"
    DATA_PROTECTION = "DATA_PROTECTION"
    INTELLECTUAL_PROPERTY = "INTELLECTUAL_PROPERTY"
    WARRANTY = "WARRANTY"
    DISPUTE_RESOLUTION = "DISPUTE_RESOLUTION"
    PENALTY = "PENALTY"
    SLA = "SLA"
    GOVERNING_LAW = "GOVERNING_LAW"
    OTHER = "OTHER"


class ClassificationConfidence(StrEnum):
    """How sure the taxonomy rule is — not LOW/MEDIUM/HIGH legal risk."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ClassificationMethod(StrEnum):
    RULE = "RULE"
    FALLBACK = "FALLBACK"


class ClassificationStatus(StrEnum):
    CLASSIFIED = "CLASSIFIED"
    OTHER = "OTHER"
    NEEDS_REVIEW = "NEEDS_REVIEW"


RISK_LEVEL_UNSET = "NOT_ASSIGNED"
TAXONOMY_VERSION = "v1"

# More-specific legal domains win equal-score ties (never article numbers).
TIE_BREAK: tuple[RiskCategory, ...] = (
    RiskCategory.LIABILITY,
    RiskCategory.TERMINATION,
    RiskCategory.PAYMENT,
    RiskCategory.PENALTY,
    RiskCategory.SLA,
    RiskCategory.DATA_PROTECTION,
    RiskCategory.CONFIDENTIALITY,
    RiskCategory.INTELLECTUAL_PROPERTY,
    RiskCategory.WARRANTY,
    RiskCategory.DISPUTE_RESOLUTION,
    RiskCategory.GOVERNING_LAW,
    RiskCategory.CONTRACT_TERM,
    RiskCategory.FINANCIAL,
    RiskCategory.OTHER,
)


@dataclass
class TaxonomyAssignment:
    """One clause (or change) classified into a legal domain. Facts only."""

    primary_category: RiskCategory
    secondary_categories: tuple[RiskCategory, ...]
    classification_confidence: ClassificationConfidence
    confidence_score: float
    classification_method: ClassificationMethod
    classification_status: ClassificationStatus
    taxonomy_version: str
    rule_id: str
    matched_signals: tuple[str, ...]
    source_ref: ClauseRef | None
    target_ref: ClauseRef | None
    identity_key: str | None
    diff_classification: DiffClassification | None
    value_types: tuple[ValueType, ...] = ()
    risk_level: str = RISK_LEVEL_UNSET

    def as_dict(self) -> dict[str, Any]:
        return {
            "primary_category": self.primary_category.value,
            "secondary_categories": [item.value for item in self.secondary_categories],
            "classification_confidence": self.classification_confidence.value,
            "confidence_score": round(self.confidence_score, 4),
            "classification_method": self.classification_method.value,
            "classification_status": self.classification_status.value,
            "taxonomy_version": self.taxonomy_version,
            "rule_id": self.rule_id,
            "matched_signals": list(self.matched_signals),
            "identity_key": self.identity_key,
            "diff_classification": (
                self.diff_classification.value if self.diff_classification else None
            ),
            "value_types": [item.value for item in self.value_types],
            "risk_level": self.risk_level,
            "source_ref": self.source_ref.as_dict() if self.source_ref else None,
            "target_ref": self.target_ref.as_dict() if self.target_ref else None,
        }


@dataclass
class TaxonomyResult:
    """Taxonomy for a full DiffResult / ExactDiffResult. Independent of RAG / LLM."""

    source_document_id: UUID
    target_document_id: UUID
    source_version_id: UUID | None
    target_version_id: UUID | None
    assignments: list[TaxonomyAssignment] = field(default_factory=list)
    taxonomy_version: str = TAXONOMY_VERSION
    metadata: dict[str, Any] = field(default_factory=dict)

    def for_source(self, identity_key: str) -> TaxonomyAssignment | None:
        for row in self.assignments:
            if row.identity_key == identity_key or (
                row.source_ref and row.source_ref.identity_key == identity_key
            ):
                return row
        return None

    def for_target(self, identity_key: str) -> TaxonomyAssignment | None:
        for row in self.assignments:
            if row.target_ref and row.target_ref.identity_key == identity_key:
                return row
        return None

    def by_category(self, category: RiskCategory) -> list[TaxonomyAssignment]:
        return [row for row in self.assignments if row.primary_category is category]

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
            "taxonomy_version": self.taxonomy_version,
            "assignments": [row.as_dict() for row in self.assignments],
            "metadata": dict(self.metadata),
        }
