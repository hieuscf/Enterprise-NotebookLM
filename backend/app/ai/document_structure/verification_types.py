# =============================================================================
# File: verification_types.py
# Module/Service: Comparison Citation Verification (FR8 / TASK-CMP-11)
# Layer: Service
# Purpose: Domain types for deterministic comparison evidence verification.
# Responsibilities:
#   - Finding/evidence verification status; reason codes; absence vs missing
#   - Canonical source snapshots and clause inventory for absence proof
# Dependencies:
#   - evidence_types; diff_types
# Public Exports:
#   - VerificationStatus, EvidenceCheckStatus, AbsenceStatus,
#     VerificationReasonCode, EvidenceChecks, EvidenceVerification,
#     FindingVerification, ComparisonVerificationResult,
#     SourceSnapshot, ClauseInventory
# Database/Table: N/A (runtime domain; not persisted; not chat citations)
# Related Modules: verification_engine; CMP-10 FindingEvidence
# Important Notes:
#   - Missing evidence is not document absence.
#   - Offsets are character offsets into original_text. 0 LLM.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.ai.document_structure.diff_types import DiffClassification
from app.ai.document_structure.evidence_types import EvidenceSide


class VerificationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    INVALID = "INVALID"


class EvidenceCheckStatus(StrEnum):
    VALID = "VALID"
    INVALID = "INVALID"
    MISSING = "MISSING"
    MISMATCH = "MISMATCH"
    UNAVAILABLE = "UNAVAILABLE"


class AbsenceStatus(StrEnum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    ABSENCE_CONFIRMED = "ABSENCE_CONFIRMED"


class VerificationReasonCode(StrEnum):
    VALID = "VALID"
    EVIDENCE_NOT_FOUND = "EVIDENCE_NOT_FOUND"
    DOCUMENT_NOT_FOUND = "DOCUMENT_NOT_FOUND"
    VERSION_MISMATCH = "VERSION_MISMATCH"
    DOCUMENT_MISMATCH = "DOCUMENT_MISMATCH"
    CLAUSE_MISMATCH = "CLAUSE_MISMATCH"
    CHUNK_MISMATCH = "CHUNK_MISMATCH"
    PAGE_MISMATCH = "PAGE_MISMATCH"
    SPAN_INVALID = "SPAN_INVALID"
    SPAN_OUT_OF_RANGE = "SPAN_OUT_OF_RANGE"
    SOURCE_TEXT_MISMATCH = "SOURCE_TEXT_MISMATCH"
    SOURCE_TEXT_MISSING = "SOURCE_TEXT_MISSING"
    WORKSPACE_MISMATCH = "WORKSPACE_MISMATCH"
    OLD_EVIDENCE_MISSING = "OLD_EVIDENCE_MISSING"
    NEW_EVIDENCE_MISSING = "NEW_EVIDENCE_MISSING"
    INSUFFICIENT_ABSENCE_PROOF = "INSUFFICIENT_ABSENCE_PROOF"
    SOURCE_TYPE_INCONSISTENT = "SOURCE_TYPE_INCONSISTENT"
    VALUE_NOT_IN_SOURCE = "VALUE_NOT_IN_SOURCE"
    BINDING_INVALID = "BINDING_INVALID"
    BINDING_UNAVAILABLE = "BINDING_UNAVAILABLE"


VERIFICATION_VERSION = "v1"

INSUFFICIENT_OLD_ABSENCE_MESSAGE = (
    "Chưa đủ bằng chứng để xác định điều khoản tương ứng không tồn tại trong V1."
)
INSUFFICIENT_NEW_ABSENCE_MESSAGE = (
    "Chưa đủ bằng chứng để xác định điều khoản tương ứng không tồn tại trong V2."
)


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    """Canonical clause/chunk metadata used to verify a bound evidence ref."""

    document_id: UUID
    document_version_id: UUID | None = None
    workspace_id: UUID | None = None
    identity_key: str | None = None
    clause_id: str | None = None
    chunk_ids: tuple[UUID, ...] = ()
    page_number: int | None = None
    original_text: str | None = None


@dataclass(frozen=True, slots=True)
class ClauseInventory:
    """Full-document identity keys from CMP-01/02. Enables absence proof."""

    source_identity_keys: frozenset[str]
    target_identity_keys: frozenset[str]


@dataclass(frozen=True, slots=True)
class EvidenceChecks:
    source_exists: bool = False
    version_matches: bool = False
    document_matches: bool = False
    clause_matches: bool = False
    chunk_matches: bool = False
    page_matches: bool = False
    span_valid: bool = False
    source_text_matches: bool = False
    workspace_matches: bool = False
    source_type_consistent: bool = False
    value_in_source: bool | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_exists": self.source_exists,
            "version_matches": self.version_matches,
            "document_matches": self.document_matches,
            "clause_matches": self.clause_matches,
            "chunk_matches": self.chunk_matches,
            "page_matches": self.page_matches,
            "span_valid": self.span_valid,
            "source_text_matches": self.source_text_matches,
            "workspace_matches": self.workspace_matches,
            "source_type_consistent": self.source_type_consistent,
            "value_in_source": self.value_in_source,
        }


@dataclass(frozen=True, slots=True)
class EvidenceVerification:
    evidence_id: str
    side: EvidenceSide
    status: EvidenceCheckStatus
    checks: EvidenceChecks
    reasons: tuple[VerificationReasonCode, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "side": self.side.value,
            "status": self.status.value,
            "checks": self.checks.as_dict(),
            "reasons": [item.value for item in self.reasons],
        }


@dataclass
class FindingVerification:
    finding_id: str
    identity_key: str | None
    status: VerificationStatus
    absence_status: AbsenceStatus
    evidence_results: list[EvidenceVerification]
    verified_evidence_ids: tuple[str, ...]
    invalid_evidence_ids: tuple[str, ...]
    missing_sides: tuple[str, ...]
    reasons: tuple[VerificationReasonCode, ...]
    human_message: str | None = None
    diff_classification: DiffClassification | None = None
    rule_id: str | None = None
    verification_version: str = VERIFICATION_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "identity_key": self.identity_key,
            "status": self.status.value,
            "absence_status": self.absence_status.value,
            "evidence_results": [row.as_dict() for row in self.evidence_results],
            "verified_evidence_ids": list(self.verified_evidence_ids),
            "invalid_evidence_ids": list(self.invalid_evidence_ids),
            "missing_sides": list(self.missing_sides),
            "reasons": [item.value for item in self.reasons],
            "human_message": self.human_message,
            "diff_classification": (
                self.diff_classification.value if self.diff_classification else None
            ),
            "rule_id": self.rule_id,
            "verification_version": self.verification_version,
        }


@dataclass
class ComparisonVerificationResult:
    source_document_id: UUID
    target_document_id: UUID
    source_version_id: UUID | None
    target_version_id: UUID | None
    findings: list[FindingVerification] = field(default_factory=list)
    verification_version: str = VERIFICATION_VERSION
    metadata: dict[str, Any] = field(default_factory=dict)

    def for_source(self, identity_key: str) -> FindingVerification | None:
        for row in self.findings:
            if row.identity_key == identity_key:
                return row
        return None

    def by_status(self, status: VerificationStatus) -> list[FindingVerification]:
        return [row for row in self.findings if row.status is status]

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
            "verification_version": self.verification_version,
            "findings": [row.as_dict() for row in self.findings],
            "metadata": dict(self.metadata),
        }
