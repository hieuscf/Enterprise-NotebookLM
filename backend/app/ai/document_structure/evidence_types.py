# =============================================================================
# File: evidence_types.py
# Module/Service: Clause Evidence Binding (FR8 / TASK-CMP-10)
# Layer: Service
# Purpose: Domain types that bind a comparison finding to immutable source refs.
# Responsibilities:
#   - OLD/NEW evidence refs; binding status; completeness (not citation verify)
#   - Deterministic evidence_id / finding_id from structured identities
# Dependencies:
#   - mapping_types.ClauseRef; taxonomy_types.RiskCategory; diff_types
# Public Exports:
#   - EvidenceSide, EvidenceSourceType, BindingStatus, EvidenceCompleteness,
#     EvidenceRole, EvidenceRef, FindingEvidence, EvidenceBindingResult,
#     EvidenceContext, SourceRecord
# Database/Table: N/A (runtime domain; not persisted)
# Related Modules: evidence_engine; CMP-11 verifies these refs later
# Important Notes:
#   - Offsets are character offsets into original_text (CMP-06). Never invented.
#   - Not a citation. Not legal advice. 0 LLM.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.ai.document_structure.diff_types import DiffClassification
from app.ai.document_structure.taxonomy_types import RiskCategory


class EvidenceSide(StrEnum):
    OLD = "OLD"
    NEW = "NEW"


class EvidenceSourceType(StrEnum):
    TEXT_SPAN = "TEXT_SPAN"
    CHUNK = "CHUNK"
    CLAUSE = "CLAUSE"
    PAGE = "PAGE"


class BindingStatus(StrEnum):
    BOUND = "BOUND"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID = "INVALID"


class EvidenceCompleteness(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"


class EvidenceRole(StrEnum):
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"


BINDING_VERSION = "v1"


@dataclass(frozen=True, slots=True)
class SourceRecord:
    """Optional hydrated chunk row. Used only to validate — never invented."""

    chunk_id: UUID
    document_id: UUID
    document_version_id: UUID
    workspace_id: UUID | None = None
    page_number: int | None = None


@dataclass(frozen=True, slots=True)
class EvidenceContext:
    """Expected ownership for a comparison run. Missing fields skip that check."""

    workspace_id: UUID | None = None
    source_document_id: UUID | None = None
    target_document_id: UUID | None = None
    source_version_id: UUID | None = None
    target_version_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    """One immutable source locator. Offsets are character offsets or None."""

    evidence_id: str
    side: EvidenceSide
    document_id: UUID | None
    document_version_id: UUID | None
    clause_id: str | None
    identity_key: str | None
    chunk_id: UUID | None
    page_number: int | None
    start_offset: int | None
    end_offset: int | None
    source_type: EvidenceSourceType
    role: EvidenceRole = EvidenceRole.PRIMARY
    display_text: str | None = None
    source_change_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "side": self.side.value,
            "document_id": str(self.document_id) if self.document_id else None,
            "document_version_id": (
                str(self.document_version_id) if self.document_version_id else None
            ),
            "clause_id": self.clause_id,
            "identity_key": self.identity_key,
            "chunk_id": str(self.chunk_id) if self.chunk_id else None,
            "page_number": self.page_number,
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
            "source_type": self.source_type.value,
            "role": self.role.value,
            "display_text": self.display_text,
            "source_change_id": self.source_change_id,
        }


@dataclass
class FindingEvidence:
    """Evidence set for one scored finding. Status is binding, not citation validity."""

    finding_id: str
    identity_key: str | None
    category: RiskCategory | None
    rule_id: str | None
    diff_classification: DiffClassification | None
    source_change_ids: tuple[str, ...]
    evidence: list[EvidenceRef]
    status: BindingStatus
    completeness: EvidenceCompleteness
    binding_version: str = BINDING_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "identity_key": self.identity_key,
            "category": self.category.value if self.category else None,
            "rule_id": self.rule_id,
            "diff_classification": (
                self.diff_classification.value if self.diff_classification else None
            ),
            "source_change_ids": list(self.source_change_ids),
            "evidence": [item.as_dict() for item in self.evidence],
            "status": self.status.value,
            "completeness": self.completeness.value,
            "binding_version": self.binding_version,
        }


@dataclass
class EvidenceBindingResult:
    """Batch bindings for a comparison. Independent of RAG / LLM / CMP-11."""

    source_document_id: UUID
    target_document_id: UUID
    source_version_id: UUID | None
    target_version_id: UUID | None
    bindings: list[FindingEvidence] = field(default_factory=list)
    binding_version: str = BINDING_VERSION
    metadata: dict[str, Any] = field(default_factory=dict)

    def for_source(self, identity_key: str) -> FindingEvidence | None:
        for row in self.bindings:
            if row.identity_key == identity_key:
                return row
        return None

    def by_status(self, status: BindingStatus) -> list[FindingEvidence]:
        return [row for row in self.bindings if row.status is status]

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
            "binding_version": self.binding_version,
            "bindings": [row.as_dict() for row in self.bindings],
            "metadata": dict(self.metadata),
        }
