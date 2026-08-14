# =============================================================================
# File: results.py
# Module/Service: Citation Verification Layer (FR5)
# Layer: Domain
# Purpose: Domain results for citation-level deterministic verification.
# Responsibilities:
#   - RetrievalEvidence (retrieved-context source row)
#   - CitationVerificationResult / CitationVerificationReport
# Dependencies:
#   - citation_verification.reasons
# Public Exports:
#   - RetrievalEvidence, CitationVerificationResult, CitationVerificationReport
# Database/Table: retrievals, document_chunks, document_versions, documents
# Related Modules: citation_verification.service
# Important Notes:
#   - Deterministic verification. No LLM call.
#   - Must validate workspace/message/retrieval membership.
#   - Do not expose internal exceptions on these objects.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from app.services.citation_verification.reasons import VerificationReason


@dataclass(frozen=True, slots=True)
class RetrievalEvidence:
    """One retrieval row plus the source text that was retrieved (not the whole doc)."""

    retrieval_id: UUID
    message_id: UUID
    source_text: str
    workspace_id: UUID | None = None
    chunk_id: UUID | None = None
    entity_id: UUID | None = None
    document_id: UUID | None = None
    document_version_id: UUID | None = None
    page_number: int | None = None
    retrieval_pass: int = 1
    # False when chunk/version/document joins failed (persisted evidence only).
    source_integrity_ok: bool = True


@dataclass(frozen=True, slots=True)
class CitationVerificationResult:
    """Outcome of verifying a single LLM citation_id."""

    citation_id: str
    verified: bool
    reason: VerificationReason
    retrieval_id: UUID | None = None
    document_id: UUID | None = None
    chunk_id: UUID | None = None
    page_number: int | None = None
    text_snippet: str | None = None
    document_version_id: UUID | None = None


@dataclass(slots=True)
class CitationVerificationReport:
    """Batch result: verified citations to persist/expose, plus rejects to log."""

    results: list[CitationVerificationResult] = field(default_factory=list)
    latency_ms: int = 0

    @property
    def verified_results(self) -> list[CitationVerificationResult]:
        return [row for row in self.results if row.verified]

    @property
    def rejected_results(self) -> list[CitationVerificationResult]:
        return [row for row in self.results if not row.verified]

    @property
    def has_verified(self) -> bool:
        return bool(self.verified_results)

    @property
    def total_count(self) -> int:
        return len(self.results)

    @property
    def valid_count(self) -> int:
        return len(self.verified_results)

    @property
    def invalid_count(self) -> int:
        return len(self.rejected_results)
