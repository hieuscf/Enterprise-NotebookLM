# =============================================================================
# File: exact.py
# Module/Service: Exact Difference Detection (FR8 / TASK-CMP-06)
# Layer: Service
# Purpose: Application wrapper for deterministic typed value diffs (0 LLM).
# Responsibilities:
#   - extract(DiffResult) — CMP-04 → ExactDiffResult
#   - extract_structures(...) — map + semantic refine + diff + exact
#   - Log counts only — never raw amounts, clause text, or PII
# Dependencies:
#   - exact_engine, ClauseDiffEngine
# Public Exports:
#   - ClauseExactDiffEngine
# Database/Table: N/A (runtime ExactDiffResult; no new comparison tables)
# Related Modules: Comparison Service remains unchanged
# Important Notes:
#   - Does not classify legal risk (CMP-07+).
#   - Does not call retrieval / embeddings / LLM.
# =============================================================================

from __future__ import annotations

from app.ai.document_structure.diff_engine import (
    diff_normalized_structures,
)
from app.ai.document_structure.diff_types import DiffResult
from app.ai.document_structure.exact_config import ExactDiffConfig
from app.ai.document_structure.exact_engine import extract_exact_differences
from app.ai.document_structure.exact_types import ExactDiffResult
from app.ai.document_structure.normalization import NormalizedDocumentStructure
from app.core.logging import get_logger
from app.services.document_structure.differ import ClauseDiffEngine

logger = get_logger(__name__)


class ClauseExactDiffEngine:
    """Typed exact differences after mapping + clause diff. 0 LLM."""

    def __init__(
        self,
        *,
        differ: ClauseDiffEngine | None = None,
        config: ExactDiffConfig | None = None,
    ) -> None:
        self._differ = differ or ClauseDiffEngine()
        self._config = config or ExactDiffConfig()

    def extract(
        self,
        diff: DiffResult,
        *,
        config: ExactDiffConfig | None = None,
    ) -> ExactDiffResult:
        logger.info(
            "exact_diff_started",
            source_document_id=str(diff.source_document_id),
            target_document_id=str(diff.target_document_id),
            clause_rows=len(diff.diffs),
        )
        result = extract_exact_differences(diff, config=config or self._config)
        logger.info(
            "exact_diff_completed",
            source_document_id=str(result.source_document_id),
            target_document_id=str(result.target_document_id),
            clauses_processed=result.metadata.get("clauses_processed"),
            values_detected=result.metadata.get("values_detected"),
            changes_detected=result.metadata.get("changes_detected"),
            money_changes=result.metadata.get("money_changes"),
            percentage_changes=result.metadata.get("percentage_changes"),
            date_changes=result.metadata.get("date_changes"),
            duration_changes=result.metadata.get("duration_changes"),
            quantity_changes=result.metadata.get("quantity_changes"),
            entity_changes=result.metadata.get("entity_changes"),
            needs_review_count=result.metadata.get("needs_review_count"),
            exact_diff_latency_ms=result.metadata.get("exact_diff_latency_ms"),
            exact_diff_llm_calls=result.metadata.get("exact_diff_llm_calls"),
        )
        return result

    def extract_structures(
        self,
        source: NormalizedDocumentStructure,
        target: NormalizedDocumentStructure,
        *,
        config: ExactDiffConfig | None = None,
    ) -> ExactDiffResult:
        diff = self._differ.diff_structures(source, target)
        return self.extract(diff, config=config)
