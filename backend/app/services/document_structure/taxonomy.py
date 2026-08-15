# =============================================================================
# File: taxonomy.py
# Module/Service: Legal Risk Taxonomy (FR8 / TASK-CMP-07)
# Layer: Service
# Purpose: Application wrapper for deterministic legal-domain classification.
# Responsibilities:
#   - classify(DiffResult, ExactDiffResult) — CMP-04/06 → TaxonomyResult
#   - classify_structures(...) — map + diff + exact + taxonomy
#   - Log counts only — never raw clause text, amounts, or PII
# Dependencies:
#   - taxonomy_engine, ClauseExactDiffEngine
# Public Exports:
#   - LegalRiskTaxonomyEngine
# Database/Table: N/A (runtime TaxonomyResult; no new comparison tables)
# Related Modules: Comparison Service remains unchanged
# Important Notes:
#   - Does not score risk (CMP-08) or fire contract rules (CMP-09).
#   - Does not call retrieval / embeddings / LLM.
# =============================================================================

from __future__ import annotations

from app.ai.document_structure.diff_types import DiffResult
from app.ai.document_structure.exact_engine import extract_exact_differences
from app.ai.document_structure.exact_types import ExactDiffResult
from app.ai.document_structure.normalization import NormalizedDocumentStructure
from app.ai.document_structure.taxonomy_config import TaxonomyConfig
from app.ai.document_structure.taxonomy_engine import classify_taxonomy
from app.ai.document_structure.taxonomy_types import TaxonomyResult
from app.core.logging import get_logger
from app.services.document_structure.differ import ClauseDiffEngine

logger = get_logger(__name__)


class LegalRiskTaxonomyEngine:
    """Legal-domain taxonomy after exact difference. 0 LLM. No risk score."""

    def __init__(
        self,
        *,
        differ: ClauseDiffEngine | None = None,
        config: TaxonomyConfig | None = None,
    ) -> None:
        self._differ = differ or ClauseDiffEngine()
        self._config = config or TaxonomyConfig()

    def classify(
        self,
        diff: DiffResult,
        exact: ExactDiffResult | None = None,
        *,
        config: TaxonomyConfig | None = None,
    ) -> TaxonomyResult:
        logger.info(
            "taxonomy_started",
            source_document_id=str(diff.source_document_id),
            target_document_id=str(diff.target_document_id),
            clause_rows=len(diff.diffs),
        )
        payload = exact if exact is not None else extract_exact_differences(diff)
        result = classify_taxonomy(diff, payload, config=config or self._config)
        logger.info(
            "taxonomy_completed",
            source_document_id=str(result.source_document_id),
            target_document_id=str(result.target_document_id),
            clauses_processed=result.metadata.get("clauses_processed"),
            classification_count=result.metadata.get("classification_count"),
            other_count=result.metadata.get("other_count"),
            low_confidence_count=result.metadata.get("low_confidence_count"),
            rule_match_count=result.metadata.get("rule_match_count"),
            fallback_count=result.metadata.get("fallback_count"),
            multi_category_count=result.metadata.get("multi_category_count"),
            taxonomy_latency_ms=result.metadata.get("taxonomy_latency_ms"),
            taxonomy_llm_calls=result.metadata.get("taxonomy_llm_calls"),
            taxonomy_version=result.taxonomy_version,
        )
        return result

    def classify_structures(
        self,
        source: NormalizedDocumentStructure,
        target: NormalizedDocumentStructure,
        *,
        config: TaxonomyConfig | None = None,
    ) -> TaxonomyResult:
        diff = self._differ.diff_structures(source, target)
        return self.classify(diff, config=config)
