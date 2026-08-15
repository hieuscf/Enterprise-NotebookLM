# =============================================================================
# File: scoring_config.py
# Module/Service: Risk Scoring Engine (FR8 / TASK-CMP-08)
# Layer: Service
# Purpose: Central knobs for deterministic 0–100 risk scoring.
# Responsibilities:
#   - Scale, level thresholds, category bases, direction/magnitude/change weights
# Dependencies:
#   - scoring_types.SCORING_VERSION; taxonomy_types.RiskCategory
# Public Exports:
#   - RiskScoreConfig, DirectionPolicy, MagnitudeBucket
# Database/Table: N/A
# Related Modules: scoring_engine
# Important Notes:
#   - Defaults are implementation starting points, not a legal standard.
#   - Do not scatter thresholds. Bump scoring_version when weights change.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.ai.document_structure.scoring_types import SCORING_VERSION
from app.ai.document_structure.taxonomy_types import RiskCategory


class DirectionPolicy(StrEnum):
    """How CMP-06 direction maps to risk impact. Party-neutral."""

    PROTECTION_LIMIT = "PROTECTION_LIMIT"
    OBLIGATION_BURDEN = "OBLIGATION_BURDEN"
    MATERIALITY_ONLY = "MATERIALITY_ONLY"
    CATEGORICAL = "CATEGORICAL"


class MagnitudeBucket(StrEnum):
    VERY_SMALL = "VERY_SMALL"
    SMALL = "SMALL"
    MEDIUM = "MEDIUM"
    LARGE = "LARGE"
    VERY_LARGE = "VERY_LARGE"
    UNKNOWN = "UNKNOWN"


# Implementation defaults — not legal authority.
_CATEGORY_BASE: dict[RiskCategory, float] = {
    RiskCategory.LIABILITY: 40.0,
    RiskCategory.TERMINATION: 38.0,
    RiskCategory.DATA_PROTECTION: 38.0,
    RiskCategory.INTELLECTUAL_PROPERTY: 36.0,
    RiskCategory.DISPUTE_RESOLUTION: 32.0,
    RiskCategory.GOVERNING_LAW: 32.0,
    RiskCategory.PENALTY: 30.0,
    RiskCategory.PAYMENT: 26.0,
    RiskCategory.CONFIDENTIALITY: 26.0,
    RiskCategory.WARRANTY: 26.0,
    RiskCategory.FINANCIAL: 24.0,
    RiskCategory.SLA: 24.0,
    RiskCategory.CONTRACT_TERM: 22.0,
    RiskCategory.OTHER: 12.0,
}

_DIRECTION_POLICY: dict[RiskCategory, DirectionPolicy] = {
    RiskCategory.LIABILITY: DirectionPolicy.PROTECTION_LIMIT,
    RiskCategory.CONFIDENTIALITY: DirectionPolicy.PROTECTION_LIMIT,
    RiskCategory.WARRANTY: DirectionPolicy.PROTECTION_LIMIT,
    RiskCategory.SLA: DirectionPolicy.PROTECTION_LIMIT,
    RiskCategory.PENALTY: DirectionPolicy.OBLIGATION_BURDEN,
    RiskCategory.PAYMENT: DirectionPolicy.MATERIALITY_ONLY,
    RiskCategory.FINANCIAL: DirectionPolicy.MATERIALITY_ONLY,
    RiskCategory.CONTRACT_TERM: DirectionPolicy.MATERIALITY_ONLY,
    RiskCategory.TERMINATION: DirectionPolicy.MATERIALITY_ONLY,
    RiskCategory.DATA_PROTECTION: DirectionPolicy.MATERIALITY_ONLY,
    RiskCategory.INTELLECTUAL_PROPERTY: DirectionPolicy.CATEGORICAL,
    RiskCategory.DISPUTE_RESOLUTION: DirectionPolicy.CATEGORICAL,
    RiskCategory.GOVERNING_LAW: DirectionPolicy.CATEGORICAL,
    RiskCategory.OTHER: DirectionPolicy.MATERIALITY_ONLY,
}


@dataclass(frozen=True, slots=True)
class RiskScoreConfig:
    """Testable scoring knobs. One config per comparison run."""

    scoring_version: str = SCORING_VERSION
    score_min: float = 0.0
    score_max: float = 100.0
    score_precision: int = 1
    medium_min: float = 25.0
    high_min: float = 50.0
    critical_min: float = 75.0
    category_base: dict[RiskCategory, float] = field(
        default_factory=lambda: dict(_CATEGORY_BASE)
    )
    direction_policy: dict[RiskCategory, DirectionPolicy] = field(
        default_factory=lambda: dict(_DIRECTION_POLICY)
    )
    impact_increasing: float = 12.0
    impact_decreasing: float = -8.0
    impact_unknown: float = 4.0
    impact_neutral: float = 0.0
    magnitude_very_small: float = 2.0
    magnitude_small: float = 6.0
    magnitude_medium: float = 12.0
    magnitude_large: float = 18.0
    magnitude_very_large: float = 24.0
    magnitude_unknown: float = 4.0
    rel_small: float = 5.0
    rel_medium: float = 15.0
    rel_large: float = 35.0
    rel_very_large: float = 60.0
    sla_pp_small: float = 0.1
    sla_pp_medium: float = 0.5
    sla_pp_large: float = 1.0
    sla_pp_very_large: float = 2.0
    added_delta: float = 8.0
    removed_delta: float = 10.0
    modified_delta: float = 0.0
    multi_domain_delta: float = 3.0
    extra_change_delta: float = 2.0
    fallback_score: float = 12.0
