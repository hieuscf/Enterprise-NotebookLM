# =============================================================================
# File: mapping_config.py
# Module/Service: Clause Identity & Mapping (FR8 / TASK-CMP-03)
# Layer: Service
# Purpose: Single configurable threshold/weight set for clause mapping.
# Responsibilities:
#   - Confidence cutoffs, ambiguity margin, candidate caps, score weights
# Dependencies:
#   - stdlib dataclasses
# Public Exports:
#   - MappingConfig
# Database/Table: N/A
# Related Modules: mapping_engine, mapping_types
# Important Notes: Do not scatter thresholds in call sites — pass this object.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MappingConfig:
    """Testable mapping knobs. All scoring code must read from here."""

    exact_min: float = 0.97
    high_min: float = 0.85
    medium_min: float = 0.70
    low_min: float = 0.55
    ambiguous_margin: float = 0.05
    max_candidates_per_source: int = 8
    max_same_type_comparisons: int = 64
    order_window: int = 4

    weight_number: float = 0.38
    weight_type: float = 0.10
    weight_parent: float = 0.12
    weight_title: float = 0.16
    weight_lexical: float = 0.14
    weight_semantic: float = 0.06
    weight_position: float = 0.04

    enable_semantic: bool = False
    enable_reranker: bool = False

    def classify(self, score: float, *, number_match: bool, type_match: bool) -> str:
        """Return a MappingStatus value name for a numeric score."""
        if number_match and type_match and score >= self.exact_min:
            return "EXACT"
        if score >= self.high_min:
            return "HIGH_CONFIDENCE"
        if score >= self.medium_min:
            return "MEDIUM_CONFIDENCE"
        if score >= self.low_min:
            return "LOW_CONFIDENCE"
        return "UNMATCHED"
