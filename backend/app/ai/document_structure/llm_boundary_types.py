# =============================================================================
# File: llm_boundary_types.py
# Module/Service: Deterministic / LLM Separation (FR8 / TASK-CMP-12)
# Layer: Service
# Purpose: Frozen DTOs that separate comparison facts from LLM interpretation.
# Responsibilities:
#   - Immutable deterministic facts; controlled evidence payload
#   - LLM output / validation status (never authoritative)
# Dependencies:
#   - verification_types; evidence_types
# Public Exports:
#   - LLMTask, ValidationStatus, ClaimSupport, DeterministicFacts,
#     LLMEvidenceItem, ComparisonLLMContext, LLMClaim, ComparisonLLMOutput,
#     ValidatedLLMResult
# Database/Table: N/A (runtime; not persisted as comparison truth)
# Related Modules: llm_boundary_engine; FR8 ComparisonService unchanged
# Important Notes:
#   - LLM output cannot mutate facts. Missing evidence ≠ absence.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID


class LLMTask(StrEnum):
    NONE = "NONE"
    EXPLAIN = "EXPLAIN"
    RECOMMEND = "RECOMMEND"


class ValidationStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    FLAGGED = "FLAGGED"
    REJECTED = "REJECTED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


class ClaimSupport(StrEnum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"


class LLMValidationReason(StrEnum):
    VALID = "VALID"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    UNKNOWN_EVIDENCE_ID = "UNKNOWN_EVIDENCE_ID"
    FORBIDDEN_FACT_OVERRIDE = "FORBIDDEN_FACT_OVERRIDE"
    UNSUPPORTED_ABSENCE_CLAIM = "UNSUPPORTED_ABSENCE_CLAIM"
    UNSUPPORTED_NUMERIC = "UNSUPPORTED_NUMERIC"
    UNSUPPORTED_PAGE = "UNSUPPORTED_PAGE"
    UNSUPPORTED_CLAUSE = "UNSUPPORTED_CLAUSE"
    UNSUPPORTED_VERSION = "UNSUPPORTED_VERSION"
    GENERATION_FAILED = "GENERATION_FAILED"
    TASK_DISABLED = "TASK_DISABLED"
    INVALID_DETERMINISTIC_FACT_OVERRIDE = "INVALID_DETERMINISTIC_FACT_OVERRIDE"
    INVALID_ENUM = "INVALID_ENUM"
    INVALID_CLAUSE_REFERENCE = "INVALID_CLAUSE_REFERENCE"
    INVALID_FINDING_REFERENCE = "INVALID_FINDING_REFERENCE"


PROMPT_VERSION = "cmp13-v1"

INSUFFICIENT_OLD_ABSENCE_PHRASE = (
    "Chưa đủ bằng chứng để xác định điều khoản tương ứng không tồn tại trong V1."
)
INSUFFICIENT_NEW_ABSENCE_PHRASE = (
    "Chưa đủ bằng chứng để xác định điều khoản tương ứng không tồn tại trong V2."
)


@dataclass(frozen=True, slots=True)
class DeterministicFacts:
    """Authoritative comparison facts. LLM cannot override these fields."""

    finding_id: str
    identity_key: str | None
    change_type: str | None
    risk_category: str | None
    risk_score: float | None
    risk_level: str | None
    rule_id: str | None
    old_document_id: UUID | None
    new_document_id: UUID | None
    old_document_version_id: UUID | None
    new_document_version_id: UUID | None
    old_value: str | None
    new_value: str | None
    verification_status: str
    absence_status: str
    absence_message: str | None
    evidence_state: str
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "identity_key": self.identity_key,
            "change_type": self.change_type,
            "risk_category": self.risk_category,
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
            "rule_id": self.rule_id,
            "old_document_id": str(self.old_document_id) if self.old_document_id else None,
            "new_document_id": str(self.new_document_id) if self.new_document_id else None,
            "old_document_version_id": (
                str(self.old_document_version_id) if self.old_document_version_id else None
            ),
            "new_document_version_id": (
                str(self.new_document_version_id) if self.new_document_version_id else None
            ),
            "old_value": self.old_value,
            "new_value": self.new_value,
            "verification_status": self.verification_status,
            "absence_status": self.absence_status,
            "absence_message": self.absence_message,
            "evidence_state": self.evidence_state,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True, slots=True)
class LLMEvidenceItem:
    """One evidence payload for the LLM. Text is untrusted source data."""

    evidence_id: str
    side: str
    verification_status: str
    document_id: UUID | None
    document_version_id: UUID | None
    clause_id: str | None
    identity_key: str | None
    chunk_id: UUID | None
    page_number: int | None
    start_offset: int | None
    end_offset: int | None
    text: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "side": self.side,
            "verification_status": self.verification_status,
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
            "text": self.text,
        }


@dataclass(frozen=True, slots=True)
class LLMClaim:
    text: str
    evidence_ids: tuple[str, ...]
    support_status: ClaimSupport

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "evidence_ids": list(self.evidence_ids),
            "support_status": self.support_status.value,
        }


@dataclass(frozen=True, slots=True)
class ComparisonLLMOutput:
    """Derived presentation only. Echo fields are copied from deterministic facts."""

    finding_id: str | None = None
    identity_key: str | None = None
    change_type: str | None = None
    risk_level: str | None = None
    risk_category: str | None = None
    explanation: str | None = None
    legal_significance: str | None = None
    business_impact: str | None = None
    recommendation: str | None = None
    uncertainty: str | None = None
    evidence_ids: tuple[str, ...] = ()
    claims: tuple[LLMClaim, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "identity_key": self.identity_key,
            "change_type": self.change_type,
            "risk_level": self.risk_level,
            "risk_category": self.risk_category,
            "explanation": self.explanation,
            "legal_significance": self.legal_significance,
            "business_impact": self.business_impact,
            "recommendation": self.recommendation,
            "uncertainty": self.uncertainty,
            "evidence_ids": list(self.evidence_ids),
            "claims": [item.as_dict() for item in self.claims],
        }


@dataclass(frozen=True, slots=True)
class ComparisonLLMContext:
    """Readonly LLM input. Facts are frozen; evidence text is untrusted."""

    facts: DeterministicFacts
    verified_evidence: tuple[LLMEvidenceItem, ...]
    uncertain_evidence: tuple[LLMEvidenceItem, ...]
    allowed_task: LLMTask
    prompt_version: str = PROMPT_VERSION
    context_hash: str = ""

    @property
    def allowed_evidence_ids(self) -> frozenset[str]:
        return frozenset(
            item.evidence_id
            for item in (*self.verified_evidence, *self.uncertain_evidence)
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "facts": self.facts.as_dict(),
            "verified_evidence": [item.as_dict() for item in self.verified_evidence],
            "uncertain_evidence": [item.as_dict() for item in self.uncertain_evidence],
            "allowed_task": self.allowed_task.value,
            "prompt_version": self.prompt_version,
            "context_hash": self.context_hash,
        }


@dataclass
class ValidatedLLMResult:
    """Validator outcome. ``facts`` are always the pre-LLM deterministic values."""

    facts: DeterministicFacts
    status: ValidationStatus
    output: ComparisonLLMOutput | None = None
    reasons: tuple[LLMValidationReason, ...] = ()
    prompt_version: str = PROMPT_VERSION
    context_hash: str = ""
    llm_calls: int = 0
    retrieval_calls: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "facts": self.facts.as_dict(),
            "status": self.status.value,
            "output": self.output.as_dict() if self.output else None,
            "reasons": [item.value for item in self.reasons],
            "prompt_version": self.prompt_version,
            "context_hash": self.context_hash,
            "llm_calls": self.llm_calls,
            "retrieval_calls": self.retrieval_calls,
            "metadata": dict(self.metadata),
        }
