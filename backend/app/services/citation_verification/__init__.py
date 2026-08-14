# =============================================================================
# File: __init__.py
# Module/Service: Citation Verification Layer (FR5)
# Layer: Service
# Purpose: Package marker for the independent Citation Verification component.
# Responsibilities:
#   - Export the verification service, reasons, and domain results
# Dependencies:
#   - citation_verification.service, reasons, results, text
# Public Exports:
#   - CitationVerificationService, VerificationReason, CitationVerificationResult,
#     CitationVerificationReport, RetrievalEvidence, INSUFFICIENT_EVIDENCE_ANSWER
# Database/Table: citations, retrievals
# Related Modules: Query Orchestration (ComplexQueryPipeline), Chat Service
# Important Notes:
#   - Deterministic verification. No LLM call.
#   - Must validate workspace/message/retrieval membership.
# =============================================================================

from app.services.citation_verification.reasons import VerificationReason
from app.services.citation_verification.results import (
    CitationVerificationReport,
    CitationVerificationResult,
    RetrievalEvidence,
)
from app.services.citation_verification.service import (
    INSUFFICIENT_EVIDENCE_ANSWER,
    CitationVerificationService,
    evidence_from_candidates,
    merge_retrieved_and_persisted_evidence,
)
from app.services.citation_verification.text import normalize_evidence_text, snippet_in_source

__all__ = [
    "INSUFFICIENT_EVIDENCE_ANSWER",
    "CitationVerificationReport",
    "CitationVerificationResult",
    "CitationVerificationService",
    "RetrievalEvidence",
    "VerificationReason",
    "evidence_from_candidates",
    "merge_retrieved_and_persisted_evidence",
    "normalize_evidence_text",
    "snippet_in_source",
]
