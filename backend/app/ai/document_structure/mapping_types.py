# =============================================================================
# File: mapping_types.py
# Module/Service: Clause Identity & Mapping (FR8 / TASK-CMP-03)
# Layer: Service
# Purpose: Domain types for clause-to-clause mapping between two documents.
# Responsibilities:
#   - Mapping status / type enums, scoring signals, mapping rows, result
#   - Traceability refs (document/version/page/chunks) without raw contract text
# Dependencies:
#   - app.ai.document_structure.normalization.NormalizedUnit
# Public Exports:
#   - MappingStatus, MappingType, MappingSignals, MappingCandidate,
#     ClauseMapping, MappingResult, ClauseRef
# Database/Table: N/A (runtime domain; not persisted)
# Related Modules: mapping_engine, ClauseMappingEngine
# Important Notes:
#   - UNMATCHED is not ADDED/REMOVED (those belong to TASK-CMP-04).
#   - as_dict() omits original_text to avoid accidental logging of contracts.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.ai.document_structure.normalization import NormalizedUnit


class MappingStatus(StrEnum):
    """Outcome of one source (or target) mapping attempt."""

    EXACT = "EXACT"
    HIGH_CONFIDENCE = "HIGH_CONFIDENCE"
    MEDIUM_CONFIDENCE = "MEDIUM_CONFIDENCE"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    AMBIGUOUS = "AMBIGUOUS"
    UNMATCHED = "UNMATCHED"


class MappingType(StrEnum):
    """How the pair was primarily justified."""

    EXACT = "EXACT"
    STRUCTURAL = "STRUCTURAL"
    TITLE = "TITLE"
    LEXICAL = "LEXICAL"
    SEMANTIC = "SEMANTIC"
    ONE_TO_ONE = "ONE_TO_ONE"
    ONE_TO_MANY_CANDIDATE = "ONE_TO_MANY_CANDIDATE"
    MANY_TO_ONE_CANDIDATE = "MANY_TO_ONE_CANDIDATE"


_ACCEPTED = frozenset(
    {
        MappingStatus.EXACT,
        MappingStatus.HIGH_CONFIDENCE,
        MappingStatus.MEDIUM_CONFIDENCE,
    }
)


@dataclass(frozen=True, slots=True)
class MappingSignals:
    """Explainable evidence for a candidate pair. No raw contract text."""

    number_match: bool
    type_match: bool
    parent_match: bool
    title_similarity: float
    lexical_similarity: float
    semantic_similarity: float | None = None
    reranker_score: float | None = None
    structural_position: float = 0.0
    candidate_margin: float | None = None
    relative_number_match: bool = False
    method: str = "unscored"

    def as_dict(self) -> dict[str, Any]:
        return {
            "number_match": self.number_match,
            "type_match": self.type_match,
            "parent_match": self.parent_match,
            "title_similarity": round(self.title_similarity, 4),
            "lexical_similarity": round(self.lexical_similarity, 4),
            "semantic_similarity": (
                None
                if self.semantic_similarity is None
                else round(self.semantic_similarity, 4)
            ),
            "reranker_score": (
                None if self.reranker_score is None else round(self.reranker_score, 4)
            ),
            "structural_position": round(self.structural_position, 4),
            "candidate_margin": (
                None
                if self.candidate_margin is None
                else round(self.candidate_margin, 4)
            ),
            "relative_number_match": self.relative_number_match,
            "method": self.method,
        }


@dataclass(frozen=True, slots=True)
class ClauseRef:
    """Traceability locator. Chunk ids are evidence, not clause identity."""

    document_id: UUID
    version_id: UUID | None
    source_id: str
    identity_key: str | None
    unit_type: str
    canonical_number: str | None
    page_start: int | None
    page_end: int | None
    chunk_ids: tuple[UUID, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "document_id": str(self.document_id),
            "version_id": str(self.version_id) if self.version_id else None,
            "source_id": self.source_id,
            "identity_key": self.identity_key,
            "type": self.unit_type,
            "canonical_number": self.canonical_number,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "chunk_ids": [str(cid) for cid in self.chunk_ids],
        }


def clause_ref(unit: NormalizedUnit, *, version_id: UUID | None) -> ClauseRef:
    return ClauseRef(
        document_id=unit.document_id,
        version_id=version_id,
        source_id=unit.source_id,
        identity_key=unit.identity_key,
        unit_type=unit.type.value,
        canonical_number=unit.canonical_number,
        page_start=unit.page_start,
        page_end=unit.page_end,
        chunk_ids=tuple(unit.chunk_ids),
    )


@dataclass(frozen=True, slots=True)
class MappingCandidate:
    """A scored target considered for one source clause."""

    target_source_id: str
    target_identity_key: str | None
    confidence: float
    signals: MappingSignals

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_source_id": self.target_source_id,
            "target_identity_key": self.target_identity_key,
            "confidence": round(self.confidence, 4),
            "signals": self.signals.as_dict(),
        }


@dataclass
class ClauseMapping:
    """One mapping decision. LOW/AMBIGUOUS/UNMATCHED are not final diffs."""

    source_unit: NormalizedUnit | None
    target_unit: NormalizedUnit | None
    mapping_type: MappingType
    confidence: float
    confidence_level: MappingStatus
    signals: MappingSignals
    source_ref: ClauseRef | None
    target_ref: ClauseRef | None
    candidates: list[MappingCandidate] = field(default_factory=list)

    @property
    def accepted(self) -> bool:
        return (
            self.confidence_level in _ACCEPTED
            and self.source_unit is not None
            and self.target_unit is not None
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_clause_id": self.source_ref.source_id if self.source_ref else None,
            "target_clause_id": self.target_ref.source_id if self.target_ref else None,
            "source_identity_key": (
                self.source_unit.identity_key if self.source_unit else None
            ),
            "target_identity_key": (
                self.target_unit.identity_key if self.target_unit else None
            ),
            "mapping_type": self.mapping_type.value,
            "confidence": round(self.confidence, 4),
            "confidence_level": self.confidence_level.value,
            "signals": self.signals.as_dict(),
            "source_ref": self.source_ref.as_dict() if self.source_ref else None,
            "target_ref": self.target_ref.as_dict() if self.target_ref else None,
            "candidates": [c.as_dict() for c in self.candidates],
        }


@dataclass
class MappingResult:
    """Full bidirectional mapping state for two normalized documents."""

    source_document_id: UUID
    target_document_id: UUID
    source_version_id: UUID | None
    target_version_id: UUID | None
    mappings: list[ClauseMapping] = field(default_factory=list)
    unmatched_targets: list[ClauseMapping] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def accepted(self) -> list[ClauseMapping]:
        return [row for row in self.mappings if row.accepted]

    def paired_identity_keys(self) -> dict[str, str]:
        pairs: dict[str, str] = {}
        for row in self.accepted():
            src = row.source_unit.identity_key if row.source_unit else None
            tgt = row.target_unit.identity_key if row.target_unit else None
            if src and tgt:
                pairs[src] = tgt
        return pairs

    def find_source(self, identity_key: str) -> ClauseMapping | None:
        for row in self.mappings:
            if row.source_unit and row.source_unit.identity_key == identity_key:
                return row
        return None

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
            "mappings": [row.as_dict() for row in self.mappings],
            "unmatched_targets": [row.as_dict() for row in self.unmatched_targets],
            "metadata": dict(self.metadata),
        }
