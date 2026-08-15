# =============================================================================
# File: evidence.py
# Module/Service: Clause Evidence Binding (FR8 / TASK-CMP-10)
# Layer: Service
# Purpose: Application wrapper that binds scored findings to source evidence.
# Responsibilities:
#   - bind(RiskScoringResult, ExactDiffResult) — in-memory, batched
#   - bind_structures(...) — map + diff + exact + taxonomy + score + bind
#   - Log counts only — never raw clause text, amounts, or PII
# Dependencies:
#   - evidence_engine, RiskScoringEngine
# Public Exports:
#   - ClauseEvidenceBinder
# Database/Table: N/A (runtime EvidenceBindingResult; no new tables)
# Related Modules: Comparison Service remains unchanged
# Important Notes:
#   - Does not verify citations (CMP-11). Does not score or classify.
#   - Optional SourceRecord list is preloaded by the caller (no N+1).
# =============================================================================

from __future__ import annotations

from collections.abc import Sequence

from app.ai.document_structure.evidence_engine import bind_evidence
from app.ai.document_structure.evidence_types import (
    EvidenceBindingResult,
    EvidenceContext,
    SourceRecord,
)
from app.ai.document_structure.exact_engine import extract_exact_differences
from app.ai.document_structure.exact_types import ExactDiffResult
from app.ai.document_structure.normalization import NormalizedDocumentStructure
from app.ai.document_structure.scoring_engine import score_taxonomy
from app.ai.document_structure.scoring_types import RiskScoringResult
from app.ai.document_structure.taxonomy_engine import classify_taxonomy
from app.ai.document_structure.taxonomy_types import TaxonomyResult
from app.core.logging import get_logger
from app.services.document_structure.differ import ClauseDiffEngine

logger = get_logger(__name__)


class ClauseEvidenceBinder:
    """Bind findings to V1/V2 source refs. 0 LLM. 0 retrieval."""

    def __init__(self, *, differ: ClauseDiffEngine | None = None) -> None:
        self._differ = differ or ClauseDiffEngine()

    def bind(
        self,
        scores: RiskScoringResult,
        exact: ExactDiffResult | None = None,
        taxonomy: TaxonomyResult | None = None,
        *,
        context: EvidenceContext | None = None,
        sources: Sequence[SourceRecord] | None = None,
    ) -> EvidenceBindingResult:
        logger.info(
            "evidence_binding_started",
            source_document_id=str(scores.source_document_id),
            target_document_id=str(scores.target_document_id),
            finding_rows=len(scores.scores),
        )
        result = bind_evidence(
            scores,
            exact,
            taxonomy,
            context=context,
            sources=sources,
        )
        logger.info(
            "evidence_binding_completed",
            source_document_id=str(result.source_document_id),
            target_document_id=str(result.target_document_id),
            findings_bound=result.metadata.get("findings_bound"),
            evidence_refs=result.metadata.get("evidence_refs"),
            unique_evidence_ids=result.metadata.get("unique_evidence_ids"),
            binding_latency_ms=result.metadata.get("binding_latency_ms"),
            evidence_llm_calls=result.metadata.get("evidence_llm_calls"),
            evidence_retrieval_calls=result.metadata.get("evidence_retrieval_calls"),
        )
        return result

    def bind_structures(
        self,
        source: NormalizedDocumentStructure,
        target: NormalizedDocumentStructure,
        *,
        context: EvidenceContext | None = None,
        sources: Sequence[SourceRecord] | None = None,
    ) -> EvidenceBindingResult:
        diff = self._differ.diff_structures(source, target)
        exact = extract_exact_differences(diff)
        taxonomy = classify_taxonomy(diff, exact)
        scores = score_taxonomy(taxonomy, exact)
        return self.bind(
            scores,
            exact,
            taxonomy,
            context=context,
            sources=sources,
        )
