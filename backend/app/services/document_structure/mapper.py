# =============================================================================
# File: mapper.py
# Module/Service: Clause Identity & Mapping (FR8 / TASK-CMP-03)
# Layer: Service
# Purpose: Application wrapper for full-document clause mapping (0 LLM).
# Responsibilities:
#   - map_structures(v1, v2) from CMP-02 NormalizedDocumentStructure
#   - map_documents(...) extract+normalize both versions then map
#   - Log counts only — never original_text / PII
# Dependencies:
#   - mapping_engine, ClauseNormalizer, DocumentStructureExtractor
# Public Exports:
#   - ClauseMappingEngine
# Database/Table: N/A (runtime MappingResult; no new comparison tables)
# Related Modules: Comparison Service remains unchanged (adapter later)
# Important Notes:
#   - Does not classify ADDED/REMOVED (TASK-CMP-04).
#   - Does not call Hybrid Retrieval / user-query RAG.
# =============================================================================

from __future__ import annotations

import uuid

from app.ai.document_structure.mapping_config import MappingConfig
from app.ai.document_structure.mapping_engine import (
    EmbedFn,
    RerankFn,
    map_normalized_structures,
)
from app.ai.document_structure.mapping_types import MappingResult
from app.ai.document_structure.normalization import NormalizedDocumentStructure
from app.core.logging import get_logger
from app.services.document_structure.extractor import DocumentStructureExtractor
from app.services.document_structure.normalizer import ClauseNormalizer

logger = get_logger(__name__)


class ClauseMappingEngine:
    """Map two full clause sets. Retrieval-independent, 0 LLM."""

    def __init__(
        self,
        *,
        extractor: DocumentStructureExtractor | None = None,
        normalizer: ClauseNormalizer | None = None,
        config: MappingConfig | None = None,
    ) -> None:
        self._extractor = extractor
        self._normalizer = normalizer or ClauseNormalizer()
        self._config = config or MappingConfig()

    def map_structures(
        self,
        source: NormalizedDocumentStructure,
        target: NormalizedDocumentStructure,
        *,
        embed_fn: EmbedFn | None = None,
        rerank_fn: RerankFn | None = None,
        config: MappingConfig | None = None,
    ) -> MappingResult:
        """Map already-normalized trees. Does not query RAG."""
        logger.info(
            "clause_mapping_started",
            source_document_id=str(source.document_id),
            target_document_id=str(target.document_id),
        )
        result = map_normalized_structures(
            source,
            target,
            config=config or self._config,
            embed_fn=embed_fn,
            rerank_fn=rerank_fn,
        )
        logger.info(
            "clause_mapping_completed",
            source_document_id=str(source.document_id),
            target_document_id=str(target.document_id),
            source_clause_count=result.metadata.get("source_clause_count"),
            target_clause_count=result.metadata.get("target_clause_count"),
            exact_mappings=result.metadata.get("exact_mappings"),
            high_confidence_mappings=result.metadata.get("high_confidence_mappings"),
            medium_confidence_mappings=result.metadata.get("medium_confidence_mappings"),
            ambiguous_mappings=result.metadata.get("ambiguous_mappings"),
            unmatched_source=result.metadata.get("unmatched_source"),
            unmatched_target=result.metadata.get("unmatched_target"),
            average_candidates_per_clause=result.metadata.get(
                "average_candidates_per_clause"
            ),
            semantic_matching_count=result.metadata.get("semantic_matching_count"),
            reranker_invocation_count=result.metadata.get("reranker_invocation_count"),
            mapping_latency_ms=result.metadata.get("mapping_latency_ms"),
            mapping_llm_calls=result.metadata.get("mapping_llm_calls"),
        )
        return result

    async def map_documents(
        self,
        *,
        workspace_id: uuid.UUID,
        source_document_id: uuid.UUID,
        target_document_id: uuid.UUID,
        source_version_id: uuid.UUID | None = None,
        target_version_id: uuid.UUID | None = None,
        embed_fn: EmbedFn | None = None,
        rerank_fn: RerankFn | None = None,
        config: MappingConfig | None = None,
    ) -> MappingResult:
        """Load both documents' FULL chunk corpora, normalize, then map."""
        if self._extractor is None:
            raise RuntimeError("DocumentStructureExtractor is required for map_documents")
        source = await self._extractor.extract_normalized(
            source_document_id,
            workspace_id=workspace_id,
            version_id=source_version_id,
        )
        target = await self._extractor.extract_normalized(
            target_document_id,
            workspace_id=workspace_id,
            version_id=target_version_id,
        )
        return self.map_structures(
            source,
            target,
            embed_fn=embed_fn,
            rerank_fn=rerank_fn,
            config=config,
        )
