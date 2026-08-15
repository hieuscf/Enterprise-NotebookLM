# =============================================================================
# File: semantic.py
# Module/Service: Semantic Clause Matching (FR8 / TASK-CMP-05)
# Layer: Service
# Purpose: Application wrapper for second-pass semantic clause matching (0 LLM).
# Responsibilities:
#   - refine(MappingResult) for unmatched / low-confidence / ambiguous rows
#   - Log counts only — never original_text / PII / embedding strings
# Dependencies:
#   - semantic_engine, EmbeddingCache
# Public Exports:
#   - ClauseSemanticMatcher
# Database/Table: N/A (runtime MappingResult; no new tables)
# Related Modules: ClauseMappingEngine, ClauseDiffEngine
# Important Notes:
#   - Does not override EXACT / HIGH / MEDIUM CMP-03 mappings.
#   - Does not call Hybrid Retrieval / user-query RAG / Qdrant chunk search.
# =============================================================================

from __future__ import annotations

from app.ai.document_structure.mapping_engine import EmbedFn, RerankFn
from app.ai.document_structure.mapping_types import MappingResult
from app.ai.document_structure.semantic_config import SemanticMatchConfig
from app.ai.document_structure.semantic_engine import refine_mapping_semantically
from app.ai.document_structure.semantic_text import EmbeddingCache
from app.core.logging import get_logger

logger = get_logger(__name__)


class ClauseSemanticMatcher:
    """Second-pass matcher. Precision-first, retrieval-independent, 0 LLM."""

    def __init__(
        self,
        *,
        config: SemanticMatchConfig | None = None,
        cache: EmbeddingCache | None = None,
    ) -> None:
        self._config = config or SemanticMatchConfig()
        self._cache = cache

    def refine(
        self,
        mapping: MappingResult,
        *,
        embed_fn: EmbedFn | None = None,
        rerank_fn: RerankFn | None = None,
        config: SemanticMatchConfig | None = None,
    ) -> MappingResult:
        cfg = config or self._config
        logger.info(
            "semantic_matching_started",
            source_document_id=str(mapping.source_document_id),
            target_document_id=str(mapping.target_document_id),
            mapping_rows=len(mapping.mappings),
            unmatched_targets=len(mapping.unmatched_targets),
            model_name=cfg.model_name,
            model_version=cfg.model_version,
        )
        result = refine_mapping_semantically(
            mapping,
            config=cfg,
            embed_fn=embed_fn,
            rerank_fn=rerank_fn,
            cache=self._cache,
        )
        logger.info(
            "semantic_matching_completed",
            source_document_id=str(result.source_document_id),
            target_document_id=str(result.target_document_id),
            semantic_clauses_reviewed=result.metadata.get("semantic_clauses_reviewed"),
            semantic_accepted=result.metadata.get("semantic_accepted"),
            semantic_ambiguous=result.metadata.get("semantic_ambiguous"),
            semantic_unmatched=result.metadata.get("semantic_unmatched"),
            semantic_candidate_requests=result.metadata.get("semantic_candidate_requests"),
            average_semantic_candidates=result.metadata.get("average_semantic_candidates"),
            semantic_reranker_calls=result.metadata.get("semantic_reranker_calls"),
            semantic_fallback_count=result.metadata.get("semantic_fallback_count"),
            semantic_cache_hits=result.metadata.get("semantic_cache_hits"),
            semantic_cache_misses=result.metadata.get("semantic_cache_misses"),
            semantic_latency_ms=result.metadata.get("semantic_latency_ms"),
            semantic_llm_calls=result.metadata.get("semantic_llm_calls"),
            semantic_model_name=result.metadata.get("semantic_model_name"),
            semantic_model_version=result.metadata.get("semantic_model_version"),
        )
        return result
