# =============================================================================
# File: semantic_config.py
# Module/Service: Semantic Clause Matching (FR8 / TASK-CMP-05)
# Layer: Service
# Purpose: Conservative, centralized thresholds for second-pass semantic matching.
# Responsibilities:
#   - Top-k, accept/margin floors, multi-signal weights, negative penalties
# Dependencies:
#   - stdlib dataclasses
# Public Exports:
#   - SemanticMatchConfig
# Database/Table: N/A
# Related Modules: semantic_engine, mapping_config
# Important Notes:
#   - False-positive mapping is worse than leaving a clause unmatched.
#   - Do not scatter thresholds in call sites — pass this object.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SemanticMatchConfig:
    """Testable CMP-05 knobs. Precision-first; semantic score is never enough alone."""

    top_k: int = 5
    accept_min: float = 0.72
    high_min: float = 0.84
    low_min: float = 0.58
    min_margin: float = 0.06
    semantic_candidate_min: float = 0.22
    semantic_strong: float = 0.80
    lexical_floor: float = 0.32
    reword_lexical_min: float = 0.15
    title_only_lexical_max: float = 0.25
    relative_number_bonus: float = 0.08
    sibling_mismatch_penalty: float = 0.22
    incompatible_penalty: float = 0.45
    max_embedding_chars: int = 800
    require_type_match: bool = True
    enable_reranker: bool = False

    weight_structural: float = 0.10
    weight_title: float = 0.14
    weight_lexical: float = 0.16
    weight_semantic: float = 0.30
    weight_reranker: float = 0.08
    weight_parent: float = 0.12
    weight_position: float = 0.04

    model_name: str = "hashing-ngram"
    model_version: str = "ngram-3-5-d256"

    def classify(self, score: float) -> str:
        """Return a MappingStatus name for an already-gated combined score."""
        if score >= self.high_min:
            return "HIGH_CONFIDENCE"
        if score >= self.accept_min:
            return "MEDIUM_CONFIDENCE"
        if score >= self.low_min:
            return "LOW_CONFIDENCE"
        return "UNMATCHED"
