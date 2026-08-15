# =============================================================================
# File: taxonomy_config.py
# Module/Service: Legal Risk Taxonomy (FR8 / TASK-CMP-07)
# Layer: Service
# Purpose: Central knobs for deterministic legal-domain classification.
# Responsibilities:
#   - Taxonomy version, accept/secondary/ambiguity thresholds, layer weights
# Dependencies:
#   - taxonomy_types.TAXONOMY_VERSION
# Public Exports:
#   - TaxonomyConfig
# Database/Table: N/A
# Related Modules: taxonomy_engine, taxonomy_rules
# Important Notes: Do not scatter thresholds in call sites. Not a risk-score config.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass

from app.ai.document_structure.taxonomy_types import TAXONOMY_VERSION


@dataclass(frozen=True, slots=True)
class TaxonomyConfig:
    """Testable taxonomy knobs. Classification stays deterministic."""

    taxonomy_version: str = TAXONOMY_VERSION
    accept_min: float = 0.62
    secondary_min: float = 0.62
    ambiguous_margin: float = 0.08
    title_override_min: float = 0.70
    high_confidence_min: float = 0.80
    medium_confidence_min: float = 0.62
    title_weight: float = 1.00
    parent_weight: float = 0.90
    local_weight: float = 0.95
    body_weight: float = 0.85
    value_signal_weight: float = 0.22
