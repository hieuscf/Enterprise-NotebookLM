# =============================================================================
# File: verification.py
# Module/Service: Citation Verification Layer — Contract Comparison (FR8 / CMP-11)
# Layer: Service
# Purpose: Application wrapper that verifies CMP-10 evidence against source.
# Responsibilities:
#   - verify(EvidenceBindingResult) — in-memory, batched
#   - verify_structures(...) — map + diff + exact + taxonomy + score + bind + verify
#   - Log counts only — never raw clause text, amounts, or PII
# Dependencies:
#   - verification_engine, ClauseEvidenceBinder, citation source_validator
# Public Exports:
#   - ComparisonCitationVerifier
# Database/Table: N/A (runtime ComparisonVerificationResult; not citations)
# Related Modules: Chat CitationVerificationService remains unchanged
# Important Notes:
#   - Does not set citations.verified (chat-message table).
#   - Does not retrieve, OCR, chunk, score, or explain.
# =============================================================================

from __future__ import annotations

from collections.abc import Sequence

from app.ai.document_structure.evidence_types import (
    EvidenceBindingResult,
    EvidenceContext,
    SourceRecord,
)
from app.ai.document_structure.exact_engine import extract_exact_differences
from app.ai.document_structure.exact_types import ExactDiffResult
from app.ai.document_structure.normalization import NormalizedDocumentStructure
from app.ai.document_structure.scoring_engine import score_taxonomy
from app.ai.document_structure.taxonomy_engine import classify_taxonomy
from app.ai.document_structure.verification_engine import (
    catalog_from_structures,
    inventory_from_structures,
    verify_bindings,
)
from app.ai.document_structure.verification_types import (
    ClauseInventory,
    ComparisonVerificationResult,
    SourceSnapshot,
)
from app.core.logging import get_logger
from app.services.document_structure.differ import ClauseDiffEngine
from app.services.document_structure.evidence import ClauseEvidenceBinder

logger = get_logger(__name__)


class ComparisonCitationVerifier:
    """Verify comparison evidence refs. 0 LLM. 0 retrieval."""

    def __init__(
        self,
        *,
        differ: ClauseDiffEngine | None = None,
        binder: ClauseEvidenceBinder | None = None,
    ) -> None:
        self._differ = differ or ClauseDiffEngine()
        self._binder = binder or ClauseEvidenceBinder(differ=self._differ)

    def verify(
        self,
        bindings: EvidenceBindingResult,
        *,
        context: EvidenceContext | None = None,
        catalog: Sequence[SourceSnapshot] | None = None,
        chunks: Sequence[SourceRecord] | None = None,
        inventory: ClauseInventory | None = None,
        exact: ExactDiffResult | None = None,
    ) -> ComparisonVerificationResult:
        logger.info(
            "comparison_citation_verification_started",
            source_document_id=str(bindings.source_document_id),
            target_document_id=str(bindings.target_document_id),
            finding_rows=len(bindings.bindings),
        )
        result = verify_bindings(
            bindings,
            context=context,
            catalog=catalog,
            chunks=chunks,
            inventory=inventory,
            exact=exact,
        )
        logger.info(
            "comparison_citation_verification_completed",
            source_document_id=str(result.source_document_id),
            target_document_id=str(result.target_document_id),
            findings_verified=result.metadata.get("findings_verified"),
            status_counts=result.metadata.get("status_counts"),
            verification_latency_ms=result.metadata.get("verification_latency_ms"),
            citation_llm_calls=result.metadata.get("citation_llm_calls"),
            citation_retrieval_calls=result.metadata.get("citation_retrieval_calls"),
        )
        return result

    def verify_structures(
        self,
        source: NormalizedDocumentStructure,
        target: NormalizedDocumentStructure,
        *,
        context: EvidenceContext | None = None,
        chunks: Sequence[SourceRecord] | None = None,
    ) -> ComparisonVerificationResult:
        diff = self._differ.diff_structures(source, target)
        exact = extract_exact_differences(diff)
        taxonomy = classify_taxonomy(diff, exact)
        scores = score_taxonomy(taxonomy, exact)
        bindings = self._binder.bind(scores, exact, taxonomy, context=context, sources=chunks)
        return self.verify(
            bindings,
            context=context,
            catalog=catalog_from_structures(source, target),
            chunks=chunks,
            inventory=inventory_from_structures(source, target),
            exact=exact,
        )
