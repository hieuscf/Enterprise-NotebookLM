# =============================================================================
# File: confidence_engine.py
# Module/Service: Search Service / Confidence Engine (FR14)
# Layer: Service
# Purpose: Non-LLM confidence scoring from Cross-Encoder re-rank statistics.
# Responsibilities:
#   - Compute top_score, score_spread, above_threshold_count
#   - Produce confidence_score ∈ [0,1] and confidence_level (high|low)
# Dependencies:
#   - pydantic, app.models.enums.ConfidenceLevel, app.core.config.Settings (factory only)
# Public Exports:
#   - RerankedItem, ConfidenceConfig, ConfidenceResult, compute_confidence,
#     build_confidence_config, should_compute_confidence
# Database/Table: N/A (persist later via message_generations)
# Related Modules: reranker.py, Event Policy Engine (next), Prompt Construction
# Important Notes:
#   - Pure function; 0 LLM / 0 embedding / 0 inference. Complex route only.
#   - Weights and thresholds come from ConfidenceConfig — never hardcode in compute.
# =============================================================================

from __future__ import annotations

from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.enums import ConfidenceLevel, RouteType

logger = get_logger(__name__)


class RerankedItem(BaseModel):
    """Minimal post-rerank candidate used by Confidence Engine.

    Extra fields (chunk_id, text_snippet, …) are ignored so callers may pass
    richer objects via ``model_validate`` without coupling to document content.
    """

    model_config = ConfigDict(extra="ignore")

    score: float | None = None
    rank: int | None = None


class ConfidenceConfig(BaseModel):
    """Tunable thresholds / weights for ``compute_confidence`` (env-backed)."""

    model_config = ConfigDict(frozen=True)

    relevance_threshold: float = Field(ge=0.0, le=1.0)
    high_threshold: float = Field(ge=0.0, le=1.0)
    weight_top_score: float = Field(ge=0.0)
    weight_score_spread: float = Field(ge=0.0)
    weight_candidate_count: float = Field(ge=0.0)
    # Cap used to normalize above_threshold_count into [0, 1].
    candidate_count_cap: int = Field(default=3, ge=1)

    @field_validator(
        "relevance_threshold",
        "high_threshold",
        "weight_top_score",
        "weight_score_spread",
        "weight_candidate_count",
        mode="before",
    )
    @classmethod
    def _coerce_float(cls, value: object) -> object:
        if value is None:
            return value
        return float(value)  # type: ignore[arg-type]


class ConfidenceResult(BaseModel):
    """Structured confidence output for Event Policy / message_generations."""

    model_config = ConfigDict(frozen=True)

    top_score: float
    score_spread: float
    above_threshold_count: int = Field(ge=0)
    confidence_score: float = Field(ge=0.0, le=1.0)
    confidence_level: ConfidenceLevel


def build_confidence_config(settings: Settings) -> ConfidenceConfig:
    """Map application ``Settings`` → ``ConfidenceConfig`` (no hardcoded tuning)."""
    return ConfidenceConfig(
        relevance_threshold=float(settings.confidence_relevance_threshold),
        high_threshold=float(settings.confidence_high_threshold),
        weight_top_score=float(settings.confidence_weight_top_score),
        weight_score_spread=float(settings.confidence_weight_score_spread),
        weight_candidate_count=float(settings.confidence_weight_candidate_count),
        candidate_count_cap=max(1, int(settings.confidence_candidate_count_cap)),
    )


def should_compute_confidence(route_type: RouteType | str) -> bool:
    """Return True only for Complex Query route (FR14 gate)."""
    if isinstance(route_type, RouteType):
        return route_type is RouteType.complex
    return str(route_type).strip().lower() == RouteType.complex.value


def compute_confidence(
    reranked_results: Sequence[RerankedItem | dict[str, object]],
    config: ConfidenceConfig,
) -> ConfidenceResult:
    """Compute confidence from Cross-Encoder re-rank statistics (pure, deterministic).

    Formula (weighted sum of normalized signals, then clamp to [0, 1]):

        confidence_score = clamp(
            normalized_top_score      * weight_top_score
          + normalized_score_spread   * weight_score_spread
          + normalized_candidate_count * weight_candidate_count,
            0, 1,
        )

    where:
      - normalized_top_score       = clamp(top_score, 0, 1)
      - normalized_score_spread    = clamp(max(0, score_spread), 0, 1) * normalized_top_score
      - normalized_candidate_count = min(1, above_threshold_count / candidate_count_cap)

    Empty / single-candidate / ``score=None`` inputs never raise; they yield a
    valid ``ConfidenceResult`` (typically ``confidence_score=0``, ``low``).

    Args:
        reranked_results: Post-rerank candidates (at least ``score`` / ``rank``).
        config: Thresholds and weights from Settings.

    Returns:
        ``ConfidenceResult`` ready for Event Policy Engine / persistence.
    """
    items = [_coerce_item(item) for item in reranked_results]
    ordered_scores = _ordered_scores(items)

    if not ordered_scores:
        result = ConfidenceResult(
            top_score=0.0,
            score_spread=0.0,
            above_threshold_count=0,
            confidence_score=0.0,
            confidence_level=ConfidenceLevel.low,
        )
        _log_debug(result)
        return result

    top_score = ordered_scores[0]
    second_score = ordered_scores[1] if len(ordered_scores) > 1 else None
    score_spread = top_score if second_score is None else (top_score - second_score)

    above_threshold_count = sum(
        1 for s in ordered_scores if s >= config.relevance_threshold
    )

    normalized_top = _clamp01(top_score)
    # Spread only helps when top itself is strong (avoids boosting two weak/negative scores).
    normalized_spread = _clamp01(max(0.0, score_spread)) * normalized_top
    normalized_count = min(
        1.0, above_threshold_count / float(config.candidate_count_cap)
    )

    raw = (
        normalized_top * config.weight_top_score
        + normalized_spread * config.weight_score_spread
        + normalized_count * config.weight_candidate_count
    )
    confidence_score = _clamp01(raw)
    confidence_level = (
        ConfidenceLevel.high
        if confidence_score >= config.high_threshold
        else ConfidenceLevel.low
    )

    result = ConfidenceResult(
        top_score=top_score,
        score_spread=score_spread,
        above_threshold_count=above_threshold_count,
        confidence_score=confidence_score,
        confidence_level=confidence_level,
    )
    _log_debug(result)
    return result


def _coerce_item(item: RerankedItem | dict[str, object]) -> RerankedItem:
    if isinstance(item, RerankedItem):
        return item
    return RerankedItem.model_validate(item)


def _safe_score(item: RerankedItem) -> float:
    if item.score is None:
        return 0.0
    try:
        return float(item.score)
    except (TypeError, ValueError):
        return 0.0


def _ordered_scores(items: list[RerankedItem]) -> list[float]:
    """Order candidates by rank ascending; fall back to score descending."""
    if not items:
        return []
    if all(item.rank is not None for item in items):
        ordered = sorted(items, key=lambda item: int(item.rank or 0))
    else:
        ordered = sorted(items, key=_safe_score, reverse=True)
    return [_safe_score(item) for item in ordered]


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return float(value)


def _log_debug(result: ConfidenceResult) -> None:
    logger.debug(
        "confidence_engine_result",
        top_score=result.top_score,
        score_spread=result.score_spread,
        confidence_score=result.confidence_score,
        confidence_level=result.confidence_level.value,
    )
