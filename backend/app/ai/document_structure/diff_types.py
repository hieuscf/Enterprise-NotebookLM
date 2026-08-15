# =============================================================================
# File: diff_types.py
# Module/Service: Clause Diff Engine (FR8 / TASK-CMP-04)
# Layer: Service
# Purpose: Domain types for deterministic clause-level diff after CMP-03 mapping.
# Responsibilities:
#   - Classification / verification enums, text-change records, diff rows
#   - Traceability via ClauseRef; original legal text is referenced, not rewritten
# Dependencies:
#   - mapping_types (ClauseRef, MappingStatus, MappingCandidate)
#   - normalization.NormalizedUnit
# Public Exports:
#   - DiffClassification, DiffVerificationStatus, ChangeType, TextChange,
#     DiffSignals, ClauseDiff, DiffResult
# Database/Table: N/A (runtime domain; not persisted)
# Related Modules: diff_engine, ClauseDiffEngine; TASK-CMP-06 consumes changes[]
# Important Notes:
#   - AMBIGUOUS_MAPPING / UNKNOWN are not ADDED/REMOVED/MODIFIED.
#   - as_dict() omits full original_text unless include_text=True.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.ai.document_structure.mapping_types import (
    ClauseRef,
    MappingCandidate,
    MappingStatus,
    MappingType,
)
from app.ai.document_structure.normalization import NormalizedUnit


class DiffClassification(StrEnum):
    """What changed at clause level. Not a legal-risk label."""

    UNCHANGED = "UNCHANGED"
    MODIFIED = "MODIFIED"
    ADDED = "ADDED"
    REMOVED = "REMOVED"
    AMBIGUOUS_MAPPING = "AMBIGUOUS_MAPPING"
    UNKNOWN = "UNKNOWN"


class DiffVerificationStatus(StrEnum):
    """Whether the classification is definitive."""

    VERIFIED = "VERIFIED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class ChangeType(StrEnum):
    """Generic token/sentence edit. CMP-06 will type amounts/dates/etc."""

    INSERTED = "INSERTED"
    DELETED = "DELETED"
    REPLACED = "REPLACED"
    MOVED = "MOVED"


_CONTENT_CLASSES = frozenset(
    {
        DiffClassification.UNCHANGED,
        DiffClassification.MODIFIED,
        DiffClassification.ADDED,
        DiffClassification.REMOVED,
    }
)


@dataclass(frozen=True, slots=True)
class TextChange:
    """One machine-readable edit. Snippets only — not a full clause dump."""

    change_type: ChangeType
    old: str
    new: str
    level: str = "token"
    old_index: int | None = None
    new_index: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": self.change_type.value,
            "old": self.old,
            "new": self.new,
            "level": self.level,
            "old_index": self.old_index,
            "new_index": self.new_index,
        }


@dataclass(frozen=True, slots=True)
class DiffSignals:
    """Structural vs legal-content flags. Metadata-only change ≠ MODIFIED."""

    content_changed: bool
    number_changed: bool
    title_changed: bool
    parent_changed: bool
    position_changed: bool
    content_hash_match: bool | None = None
    comparison_field: str = "folded_body"

    def as_dict(self) -> dict[str, Any]:
        return {
            "content_changed": self.content_changed,
            "number_changed": self.number_changed,
            "title_changed": self.title_changed,
            "parent_changed": self.parent_changed,
            "position_changed": self.position_changed,
            "content_hash_match": self.content_hash_match,
            "comparison_field": self.comparison_field,
        }


def _empty_signals() -> DiffSignals:
    return DiffSignals(
        content_changed=False,
        number_changed=False,
        title_changed=False,
        parent_changed=False,
        position_changed=False,
    )


@dataclass
class ClauseDiff:
    """One mapped or unmatched unit after deterministic classification."""

    classification: DiffClassification
    verification_status: DiffVerificationStatus
    mapping_status: MappingStatus | None
    source_unit: NormalizedUnit | None
    target_unit: NormalizedUnit | None
    source_ref: ClauseRef | None
    target_ref: ClauseRef | None
    signals: DiffSignals = field(default_factory=_empty_signals)
    mapping_type: MappingType | None = None
    mapping_confidence: float | None = None
    changes: list[TextChange] = field(default_factory=list)
    sentence_changes: list[TextChange] = field(default_factory=list)
    candidates: list[MappingCandidate] = field(default_factory=list)
    subtree_classification: DiffClassification | None = None
    content_hash_source: str | None = None
    content_hash_target: str | None = None

    @property
    def definitive(self) -> bool:
        return (
            self.verification_status is DiffVerificationStatus.VERIFIED
            and self.classification in _CONTENT_CLASSES
        )

    def as_dict(self, *, include_text: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source_clause_id": self.source_ref.source_id if self.source_ref else None,
            "target_clause_id": self.target_ref.source_id if self.target_ref else None,
            "source_identity_key": (
                self.source_unit.identity_key if self.source_unit else None
            ),
            "target_identity_key": (
                self.target_unit.identity_key if self.target_unit else None
            ),
            "classification": self.classification.value,
            "verification_status": self.verification_status.value,
            "mapping_status": (
                self.mapping_status.value if self.mapping_status else None
            ),
            "mapping_type": self.mapping_type.value if self.mapping_type else None,
            "mapping_confidence": (
                None
                if self.mapping_confidence is None
                else round(self.mapping_confidence, 4)
            ),
            "content_changed": self.signals.content_changed,
            "number_changed": self.signals.number_changed,
            "title_changed": self.signals.title_changed,
            "parent_changed": self.signals.parent_changed,
            "position_changed": self.signals.position_changed,
            "signals": self.signals.as_dict(),
            "changes": [item.as_dict() for item in self.changes],
            "sentence_changes": [item.as_dict() for item in self.sentence_changes],
            "candidates": [item.as_dict() for item in self.candidates],
            "subtree_classification": (
                self.subtree_classification.value
                if self.subtree_classification
                else None
            ),
            "source_ref": self.source_ref.as_dict() if self.source_ref else None,
            "target_ref": self.target_ref.as_dict() if self.target_ref else None,
            "content_hash_source": self.content_hash_source,
            "content_hash_target": self.content_hash_target,
        }
        if include_text:
            payload["old_text"] = (
                self.source_unit.original_text if self.source_unit else None
            )
            payload["new_text"] = (
                self.target_unit.original_text if self.target_unit else None
            )
        return payload


@dataclass
class DiffResult:
    """Full clause-set diff for two documents. Independent of RAG retrieval."""

    source_document_id: UUID
    target_document_id: UUID
    source_version_id: UUID | None
    target_version_id: UUID | None
    diffs: list[ClauseDiff] = field(default_factory=list)
    mapping_metadata: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def find_source(self, identity_key: str) -> ClauseDiff | None:
        for row in self.diffs:
            if row.source_unit and row.source_unit.identity_key == identity_key:
                return row
        return None

    def find_target(self, identity_key: str) -> ClauseDiff | None:
        for row in self.diffs:
            if row.target_unit and row.target_unit.identity_key == identity_key:
                return row
        return None

    def by_classification(
        self, classification: DiffClassification
    ) -> list[ClauseDiff]:
        return [row for row in self.diffs if row.classification is classification]

    def definitive(self) -> list[ClauseDiff]:
        return [row for row in self.diffs if row.definitive]

    def as_dict(self, *, include_text: bool = False) -> dict[str, Any]:
        return {
            "source_document_id": str(self.source_document_id),
            "target_document_id": str(self.target_document_id),
            "source_version_id": (
                str(self.source_version_id) if self.source_version_id else None
            ),
            "target_version_id": (
                str(self.target_version_id) if self.target_version_id else None
            ),
            "diffs": [row.as_dict(include_text=include_text) for row in self.diffs],
            "mapping_metadata": dict(self.mapping_metadata),
            "metadata": dict(self.metadata),
        }
