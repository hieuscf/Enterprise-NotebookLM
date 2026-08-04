# =============================================================================
# File: test_confidence_engine.py
# Module/Service: Search Service / Confidence Engine (FR14)
# Layer: Service
# Purpose: Unit tests for pure compute_confidence (non-LLM).
# Responsibilities:
#   - Cover dominant / ambiguous / weak / empty / single / clamp cases
# Dependencies:
#   - pytest, app.services.retrieval.confidence_engine
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: Confidence Engine, Event Policy Engine (later)
# Important Notes: No DB / FastAPI / LLM. Deterministic only.
# =============================================================================

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.models.enums import ConfidenceLevel, RouteType
from app.services.retrieval.confidence_engine import (
    ConfidenceConfig,
    RerankedItem,
    build_confidence_config,
    compute_confidence,
    should_compute_confidence,
)


def _cfg(**overrides: float | int) -> ConfidenceConfig:
    """Default test config aligned with Settings defaults (tunable per case)."""
    base: dict[str, float | int] = {
        "relevance_threshold": 0.65,
        "high_threshold": 0.65,
        "weight_top_score": 0.55,
        "weight_score_spread": 0.35,
        "weight_candidate_count": 0.10,
        "candidate_count_cap": 3,
    }
    base.update(overrides)
    return ConfidenceConfig(**base)  # type: ignore[arg-type]


def _items(*scores: float) -> list[RerankedItem]:
    return [RerankedItem(rank=i, score=s) for i, s in enumerate(scores, start=1)]


def test_case1_dominant_top_candidate_is_high() -> None:
    result = compute_confidence(_items(0.97, 0.55, 0.43, 0.40), _cfg())

    assert result.top_score == pytest.approx(0.97)
    assert result.score_spread == pytest.approx(0.42)
    assert result.above_threshold_count == 1
    assert result.confidence_level is ConfidenceLevel.high
    assert result.confidence_score >= 0.65
    assert result.confidence_score > 0.7


def test_case2_near_tie_candidates_is_low() -> None:
    result = compute_confidence(_items(0.66, 0.65, 0.64, 0.63), _cfg())

    assert result.score_spread == pytest.approx(0.01)
    assert result.confidence_level is ConfidenceLevel.low
    assert result.confidence_score < 0.65


def test_case3_mostly_below_relevance_threshold_is_low() -> None:
    result = compute_confidence(_items(0.42, 0.40, 0.39, 0.38), _cfg())

    assert result.above_threshold_count == 0
    assert result.confidence_level is ConfidenceLevel.low
    assert result.confidence_score < 0.4


def test_case4_empty_list_safe_zero_low() -> None:
    result = compute_confidence([], _cfg())

    assert result.top_score == 0.0
    assert result.score_spread == 0.0
    assert result.above_threshold_count == 0
    assert result.confidence_score == 0.0
    assert result.confidence_level is ConfidenceLevel.low


def test_case5_single_candidate_uses_top_as_spread() -> None:
    result = compute_confidence(_items(0.90), _cfg())

    assert result.top_score == pytest.approx(0.90)
    assert result.score_spread == pytest.approx(0.90)
    assert result.above_threshold_count == 1
    assert 0.0 <= result.confidence_score <= 1.0
    assert result.confidence_level is ConfidenceLevel.high


def test_case6_clamp_keeps_score_in_unit_interval() -> None:
    # Raw weighted sum would exceed 1.0 without clamp (scores >1 + large weights).
    cfg = _cfg(
        weight_top_score=2.0,
        weight_score_spread=2.0,
        weight_candidate_count=2.0,
        high_threshold=0.99,
    )
    result = compute_confidence(_items(5.0, 4.0, 3.0), cfg)

    assert 0.0 <= result.confidence_score <= 1.0
    assert result.confidence_score == pytest.approx(1.0)

    # Negative-leaning path: clamp floor at 0 (scores treated safely).
    neg = compute_confidence(
        [RerankedItem(rank=1, score=-2.0), RerankedItem(rank=2, score=-3.0)],
        _cfg(high_threshold=0.01),
    )
    assert 0.0 <= neg.confidence_score <= 1.0
    assert neg.confidence_level is ConfidenceLevel.low


def test_none_score_treated_as_zero() -> None:
    result = compute_confidence(
        [RerankedItem(rank=1, score=None), RerankedItem(rank=2, score=0.5)],
        _cfg(),
    )
    assert result.top_score == 0.0
    assert result.score_spread == pytest.approx(-0.5)
    assert result.confidence_level is ConfidenceLevel.low


def test_config_validation_rejects_out_of_range() -> None:
    with pytest.raises(ValidationError):
        ConfidenceConfig(
            relevance_threshold=1.5,
            high_threshold=0.5,
            weight_top_score=0.5,
            weight_score_spread=0.3,
            weight_candidate_count=0.2,
        )
    with pytest.raises(ValidationError):
        ConfidenceConfig(
            relevance_threshold=0.5,
            high_threshold=0.5,
            weight_top_score=-1.0,
            weight_score_spread=0.3,
            weight_candidate_count=0.2,
        )


def test_build_confidence_config_from_settings() -> None:
    settings = Settings(
        confidence_relevance_threshold=0.7,
        confidence_high_threshold=0.8,
        confidence_weight_top_score=0.4,
        confidence_weight_score_spread=0.4,
        confidence_weight_candidate_count=0.2,
        confidence_candidate_count_cap=5,
    )
    cfg = build_confidence_config(settings)
    assert cfg.relevance_threshold == pytest.approx(0.7)
    assert cfg.high_threshold == pytest.approx(0.8)
    assert cfg.candidate_count_cap == 5


def test_should_compute_confidence_complex_only() -> None:
    assert should_compute_confidence(RouteType.complex) is True
    assert should_compute_confidence("complex") is True
    assert should_compute_confidence(RouteType.cache_hit) is False
    assert should_compute_confidence(RouteType.metadata) is False
    assert should_compute_confidence(RouteType.factoid) is False


def test_result_json_serializable() -> None:
    result = compute_confidence(_items(0.97, 0.55), _cfg())
    payload = result.model_dump(mode="json")
    assert payload["confidence_level"] == "high"
    assert "confidence_score" in payload


# ---------------------------------------------------------------------------
# Boundary tests (Task 5)
# ---------------------------------------------------------------------------


def test_boundary_score_equals_high_threshold_is_high() -> None:
    """confidence_score == high_threshold → HIGH (>=)."""
    cfg = _cfg(
        high_threshold=0.50,
        weight_top_score=1.0,
        weight_score_spread=0.0,
        weight_candidate_count=0.0,
    )
    # normalized_top=0.50 → raw = 0.50 * 1.0 == high_threshold
    result = compute_confidence(_items(0.50, 0.10), cfg)
    assert result.confidence_score == pytest.approx(0.50)
    assert result.confidence_level is ConfidenceLevel.high


def test_boundary_one_candidate_no_crash() -> None:
    result = compute_confidence(_items(0.88), _cfg())
    assert result.top_score == pytest.approx(0.88)
    assert result.score_spread == pytest.approx(0.88)
    assert 0.0 <= result.confidence_score <= 1.0


def test_boundary_same_scores_zero_spread_low() -> None:
    result = compute_confidence(_items(0.71, 0.71, 0.71, 0.71), _cfg())
    assert result.score_spread == pytest.approx(0.0)
    assert result.confidence_level is ConfidenceLevel.low


def test_boundary_empty_list_zero_low() -> None:
    result = compute_confidence([], _cfg())
    assert result.confidence_score == 0.0
    assert result.confidence_level is ConfidenceLevel.low


def test_boundary_clamp_above_one_and_below_zero() -> None:
    high = compute_confidence(
        _items(9.0, 8.0),
        _cfg(
            weight_top_score=5.0,
            weight_score_spread=5.0,
            weight_candidate_count=5.0,
            high_threshold=0.99,
        ),
    )
    assert high.confidence_score == pytest.approx(1.0)

    low = compute_confidence(
        [RerankedItem(rank=1, score=-5.0), RerankedItem(rank=2, score=-6.0)],
        _cfg(high_threshold=0.01),
    )
    assert low.confidence_score >= 0.0
    assert low.confidence_score <= 1.0
