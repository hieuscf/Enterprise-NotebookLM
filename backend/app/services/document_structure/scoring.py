# =============================================================================
# File: scoring.py
# Module/Service: Risk Scoring Engine (FR8 / TASK-CMP-08)
# Layer: Service
# Purpose: Application wrapper for deterministic risk score / level.
# Responsibilities:
#   - score(TaxonomyResult, ExactDiffResult) — CMP-07/06 → RiskScoringResult
#   - score_structures(...) — map + diff + exact + taxonomy + score
#   - Log counts only — never raw amounts, clause text, or PII
# Dependencies:
#   - scoring_engine, LegalRiskTaxonomyEngine
# Public Exports:
#   - RiskScoringEngine
# Database/Table: N/A (runtime RiskScoringResult; no new comparison tables)
# Related Modules: Comparison Service remains unchanged
# Important Notes:
#   - Does not fire CMP-09 contract rules or bind evidence (CMP-10).
#   - Does not call retrieval / embeddings / LLM.
# =============================================================================

from __future__ import annotations

from app.ai.document_structure.diff_types import DiffResult
from app.ai.document_structure.exact_engine import extract_exact_differences
from app.ai.document_structure.exact_types import ExactDiffResult
from app.ai.document_structure.normalization import NormalizedDocumentStructure
from app.ai.document_structure.scoring_config import RiskScoreConfig
from app.ai.document_structure.scoring_engine import score_taxonomy
from app.ai.document_structure.scoring_types import RiskPerspective, RiskScoringResult
from app.ai.document_structure.taxonomy_engine import classify_taxonomy
from app.ai.document_structure.taxonomy_types import TaxonomyResult
from app.core.logging import get_logger
from app.services.document_structure.differ import ClauseDiffEngine

logger = get_logger(__name__)


class RiskScoringEngine:
    """0–100 risk score after taxonomy. 0 LLM. No contract-specific rules."""

    def __init__(
        self,
        *,
        differ: ClauseDiffEngine | None = None,
        config: RiskScoreConfig | None = None,
    ) -> None:
        self._differ = differ or ClauseDiffEngine()
        self._config = config or RiskScoreConfig()

    def score(
        self,
        taxonomy: TaxonomyResult,
        exact: ExactDiffResult | None = None,
        *,
        config: RiskScoreConfig | None = None,
        perspective: RiskPerspective = RiskPerspective.UNKNOWN,
    ) -> RiskScoringResult:
        logger.info(
            "risk_scoring_started",
            source_document_id=str(taxonomy.source_document_id),
            target_document_id=str(taxonomy.target_document_id),
            assignment_rows=len(taxonomy.assignments),
            scoring_version=(config or self._config).scoring_version,
        )
        result = score_taxonomy(
            taxonomy,
            exact,
            config=config or self._config,
            perspective=perspective,
        )
        logger.info(
            "risk_scoring_completed",
            source_document_id=str(result.source_document_id),
            target_document_id=str(result.target_document_id),
            findings_scored=result.metadata.get("findings_scored"),
            average_score=result.metadata.get("average_score"),
            fallback_count=result.metadata.get("fallback_count"),
            needs_review_count=result.metadata.get("needs_review_count"),
            unknown_perspective_count=result.metadata.get("unknown_perspective_count"),
            scoring_latency_ms=result.metadata.get("scoring_latency_ms"),
            scoring_llm_calls=result.metadata.get("scoring_llm_calls"),
            scoring_version=result.scoring_version,
        )
        return result

    def score_structures(
        self,
        source: NormalizedDocumentStructure,
        target: NormalizedDocumentStructure,
        *,
        config: RiskScoreConfig | None = None,
        perspective: RiskPerspective = RiskPerspective.UNKNOWN,
    ) -> RiskScoringResult:
        diff = self._differ.diff_structures(source, target)
        exact = extract_exact_differences(diff)
        taxonomy = classify_taxonomy(diff, exact)
        return self.score(taxonomy, exact, config=config, perspective=perspective)

    def score_diff(
        self,
        diff: DiffResult,
        *,
        config: RiskScoreConfig | None = None,
        perspective: RiskPerspective = RiskPerspective.UNKNOWN,
    ) -> RiskScoringResult:
        exact = extract_exact_differences(diff)
        taxonomy = classify_taxonomy(diff, exact)
        return self.score(taxonomy, exact, config=config, perspective=perspective)
