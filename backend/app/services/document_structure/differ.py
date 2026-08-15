# =============================================================================
# File: differ.py
# Module/Service: Clause Diff Engine (FR8 / TASK-CMP-04)
# Layer: Service
# Purpose: Application wrapper for deterministic clause-level diff (0 LLM).
# Responsibilities:
#   - diff_mapping(MappingResult) — classify the complete mapped clause set
#   - diff_structures(v1, v2) — map then diff
#   - diff_documents(...) — extract+normalize+map+diff both versions
#   - Log counts only — never original_text / PII / change snippets
# Dependencies:
#   - diff_engine, ClauseMappingEngine, DocumentStructureExtractor
# Public Exports:
#   - ClauseDiffEngine
# Database/Table: N/A (runtime DiffResult; no new comparison tables)
# Related Modules: Comparison Service remains unchanged (adapter later)
# Important Notes:
#   - Does not call Hybrid Retrieval / user-query RAG / LLM.
#   - ADDED/REMOVED come only from CMP-03 unmatched units after mapping.
# =============================================================================

from __future__ import annotations

import uuid

from app.ai.document_structure.diff_config import DiffConfig
from app.ai.document_structure.diff_engine import (
    diff_mapping_result,
    diff_normalized_structures,
)
from app.ai.document_structure.diff_types import DiffResult
from app.ai.document_structure.mapping_types import MappingResult
from app.ai.document_structure.normalization import NormalizedDocumentStructure
from app.core.logging import get_logger
from app.services.document_structure.extractor import DocumentStructureExtractor
from app.services.document_structure.mapper import ClauseMappingEngine

logger = get_logger(__name__)


class ClauseDiffEngine:
    """Diff two full clause sets after mapping. Retrieval-independent, 0 LLM."""

    def __init__(
        self,
        *,
        mapper: ClauseMappingEngine | None = None,
        extractor: DocumentStructureExtractor | None = None,
        config: DiffConfig | None = None,
    ) -> None:
        self._mapper = mapper or ClauseMappingEngine(extractor=extractor)
        self._extractor = extractor
        self._config = config or DiffConfig()

    def diff_mapping(
        self,
        mapping: MappingResult,
        *,
        config: DiffConfig | None = None,
    ) -> DiffResult:
        """Classify an existing CMP-03 result. Does not query RAG."""
        logger.info(
            "clause_diff_started",
            source_document_id=str(mapping.source_document_id),
            target_document_id=str(mapping.target_document_id),
            mapping_rows=len(mapping.mappings),
            unmatched_targets=len(mapping.unmatched_targets),
        )
        result = diff_mapping_result(mapping, config=config or self._config)
        self._log_completed(result)
        return result

    def diff_structures(
        self,
        source: NormalizedDocumentStructure,
        target: NormalizedDocumentStructure,
        *,
        mapping: MappingResult | None = None,
        config: DiffConfig | None = None,
    ) -> DiffResult:
        """Map (unless provided) then diff. Input is the full normalized trees."""
        logger.info(
            "clause_diff_started",
            source_document_id=str(source.document_id),
            target_document_id=str(target.document_id),
        )
        result = diff_normalized_structures(
            source,
            target,
            mapping=mapping,
            config=config or self._config,
        )
        self._log_completed(result)
        return result

    async def diff_documents(
        self,
        *,
        workspace_id: uuid.UUID,
        source_document_id: uuid.UUID,
        target_document_id: uuid.UUID,
        source_version_id: uuid.UUID | None = None,
        target_version_id: uuid.UUID | None = None,
        config: DiffConfig | None = None,
    ) -> DiffResult:
        """Load both documents' FULL chunk corpora, map, then diff."""
        mapping = await self._mapper.map_documents(
            workspace_id=workspace_id,
            source_document_id=source_document_id,
            target_document_id=target_document_id,
            source_version_id=source_version_id,
            target_version_id=target_version_id,
        )
        return self.diff_mapping(mapping, config=config)

    def _log_completed(self, result: DiffResult) -> None:
        logger.info(
            "clause_diff_completed",
            source_document_id=str(result.source_document_id),
            target_document_id=str(result.target_document_id),
            total_diffs=result.metadata.get("total_diffs"),
            unchanged_count=result.metadata.get("unchanged_count"),
            modified_count=result.metadata.get("modified_count"),
            added_count=result.metadata.get("added_count"),
            removed_count=result.metadata.get("removed_count"),
            ambiguous_count=result.metadata.get("ambiguous_count"),
            unknown_count=result.metadata.get("unknown_count"),
            needs_review_count=result.metadata.get("needs_review_count"),
            exact_unchanged_rate=result.metadata.get("exact_unchanged_rate"),
            average_diff_size=result.metadata.get("average_diff_size"),
            diff_latency_ms=result.metadata.get("diff_latency_ms"),
            diff_llm_calls=result.metadata.get("diff_llm_calls"),
            error_count=result.metadata.get("error_count"),
        )
