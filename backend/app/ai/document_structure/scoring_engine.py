# =============================================================================
# File: scoring_engine.py
# Module/Service: Risk Scoring Engine (FR8 / TASK-CMP-08)
# Layer: Service
# Purpose: Turn CMP-06 exact changes + CMP-07 taxonomy into a 0–100 score.
# Responsibilities:
#   - Factorized score (category, impact, magnitude, change type)
#   - Deterministic level mapping; clamp; CMP-09 adjustment hook
#   - Consume ExactChange / TaxonomyAssignment — do not re-parse or re-classify
# Dependencies:
#   - scoring_types, scoring_config, exact_types, taxonomy_types, diff_types
# Public Exports:
#   - score_taxonomy, score_assignment, level_from_score, clamp_score,
#     apply_adjustments
# Database/Table: N/A
# Related Modules: RiskScoringEngine; CMP-09 applies RiskAdjustment later
# Important Notes:
#   - 0 LLM. Party perspective stays UNKNOWN unless the caller supplies it.
#   - Article numbers never drive the score. Breakdown sums to final_score.
# =============================================================================

from __future__ import annotations

import math
import time
from typing import Any

from app.ai.document_structure.diff_types import DiffClassification
from app.ai.document_structure.exact_types import (
    ExactChange,
    ExactDiffResult,
    ValueChangeType,
    ValueDirection,
)
from app.ai.document_structure.scoring_config import (
    DirectionPolicy,
    MagnitudeBucket,
    RiskScoreConfig,
)
from app.ai.document_structure.scoring_types import (
    SCORING_VERSION,
    RiskAdjustment,
    RiskImpact,
    RiskLevel,
    RiskPerspective,
    RiskScoreResult,
    RiskScoringResult,
    RiskStatus,
    ScoreFactor,
    ScoringConfidence,
)
from app.ai.document_structure.taxonomy_types import (
    ClassificationConfidence,
    ClassificationStatus,
    RiskCategory,
    TaxonomyAssignment,
    TaxonomyResult,
)

_SKIP = frozenset(
    {
        DiffClassification.UNCHANGED,
        DiffClassification.AMBIGUOUS_MAPPING,
        DiffClassification.UNKNOWN,
    }
)
_INCREASE_DIRS = frozenset(
    {ValueDirection.INCREASE, ValueDirection.LATER, ValueDirection.ADDED}
)
_DECREASE_DIRS = frozenset(
    {ValueDirection.DECREASE, ValueDirection.EARLIER, ValueDirection.REMOVED}
)


def level_from_score(score: float, config: RiskScoreConfig | None = None) -> RiskLevel:
    """Map a clamped score onto LOW/MEDIUM/HIGH/CRITICAL. No gaps or overlap."""
    cfg = config or RiskScoreConfig()
    value = clamp_score(score, cfg)
    if value < cfg.medium_min:
        return RiskLevel.LOW
    if value < cfg.high_min:
        return RiskLevel.MEDIUM
    if value < cfg.critical_min:
        return RiskLevel.HIGH
    return RiskLevel.CRITICAL


def clamp_score(score: float, config: RiskScoreConfig | None = None) -> float:
    cfg = config or RiskScoreConfig()
    if not math.isfinite(score):
        return cfg.fallback_score
    return max(cfg.score_min, min(cfg.score_max, score))


def apply_adjustments(
    result: RiskScoreResult,
    adjustments: list[RiskAdjustment],
    *,
    config: RiskScoreConfig | None = None,
) -> RiskScoreResult:
    """CMP-09 hook. Re-clamps and remaps level. CMP-08 does not emit adjustments."""
    cfg = config or RiskScoreConfig()
    extra = tuple(
        ScoreFactor(factor="RULE_ADJUSTMENT", delta=_q(item.delta, cfg), source=item.rule_id)
        for item in adjustments
    )
    raw = result.risk_score + sum(item.delta for item in extra)
    final, breakdown = _finalize(list(result.score_breakdown) + list(extra), raw, cfg)
    return RiskScoreResult(
        risk_score=final,
        risk_level=level_from_score(final, cfg),
        risk_impact=result.risk_impact,
        base_score=result.base_score,
        score_breakdown=tuple(breakdown),
        scoring_confidence=result.scoring_confidence,
        scoring_version=cfg.scoring_version,
        status=result.status,
        category=result.category,
        classification_confidence=result.classification_confidence,
        perspective=result.perspective,
        identity_key=result.identity_key,
        diff_classification=result.diff_classification,
        source_ref=result.source_ref,
        target_ref=result.target_ref,
        pending_adjustments=tuple(adjustments),
    )


def score_taxonomy(
    taxonomy: TaxonomyResult,
    exact: ExactDiffResult | None = None,
    *,
    config: RiskScoreConfig | None = None,
    perspective: RiskPerspective = RiskPerspective.UNKNOWN,
) -> RiskScoringResult:
    """Score every CMP-07 assignment. Does not re-run taxonomy or exact-diff."""
    started = time.perf_counter()
    cfg = config or RiskScoreConfig()
    grouped = _index_changes(exact)
    rows: list[RiskScoreResult] = []
    fallback = 0
    review = 0
    for assignment in taxonomy.assignments:
        if assignment.diff_classification in _SKIP:
            continue
        try:
            scored = score_assignment(
                assignment,
                _changes_for(assignment, grouped),
                config=cfg,
                perspective=perspective,
            )
        except Exception:
            scored = _failed(assignment, cfg, perspective)
            fallback += 1
        if scored.status is RiskStatus.NEEDS_REVIEW:
            review += 1
        if scored.status is RiskStatus.FAILED:
            fallback += 1
        rows.append(scored)
    duration_ms = int((time.perf_counter() - started) * 1000)
    return RiskScoringResult(
        source_document_id=taxonomy.source_document_id,
        target_document_id=taxonomy.target_document_id,
        source_version_id=taxonomy.source_version_id,
        target_version_id=taxonomy.target_version_id,
        scores=rows,
        scoring_version=cfg.scoring_version,
        metadata=_metadata(rows, fallback=fallback, review=review, duration_ms=duration_ms),
    )


def score_assignment(
    assignment: TaxonomyAssignment,
    changes: list[ExactChange] | None = None,
    *,
    config: RiskScoreConfig | None = None,
    perspective: RiskPerspective = RiskPerspective.UNKNOWN,
) -> RiskScoreResult:
    """Score one taxonomy row using already-normalized CMP-06 values."""
    cfg = config or RiskScoreConfig()
    if assignment.diff_classification is DiffClassification.UNCHANGED:
        return _not_applicable(assignment, cfg, perspective)
    category = assignment.primary_category
    if category not in cfg.category_base:
        category = RiskCategory.OTHER
    rows = list(changes or [])
    primary = _strongest_change(rows)
    impact = _impact(category, assignment.diff_classification, primary, cfg)
    bucket, mag_source = _magnitude(category, primary, cfg)
    factors = [
        ScoreFactor(
            factor="CATEGORY_BASE",
            delta=_q(cfg.category_base[category], cfg),
            source=f"CMP-07.primary_category:{category.value}",
        ),
        ScoreFactor(
            factor="DIRECTION",
            delta=_q(_impact_delta(impact, cfg), cfg),
            source=f"CMP-06.direction:{_dir_label(primary)}",
        ),
        ScoreFactor(
            factor="MAGNITUDE",
            delta=_q(_magnitude_delta(bucket, cfg), cfg),
            source=mag_source,
        ),
        ScoreFactor(
            factor="CHANGE_TYPE",
            delta=_q(_change_type_delta(assignment.diff_classification, cfg), cfg),
            source=f"CMP-04.classification:{_cls(assignment)}",
        ),
    ]
    if assignment.secondary_categories:
        factors.append(
            ScoreFactor(
                factor="CLAUSE_IMPORTANCE",
                delta=_q(cfg.multi_domain_delta, cfg),
                source="CMP-07.secondary_categories",
            )
        )
    if len(rows) > 1:
        factors.append(
            ScoreFactor(
                factor="MULTI_CHANGE",
                delta=_q(cfg.extra_change_delta, cfg),
                source="CMP-06.exact_changes",
            )
        )
    raw = sum(item.delta for item in factors)
    final, breakdown = _finalize(factors, raw, cfg)
    status = _status(assignment, primary)
    return RiskScoreResult(
        risk_score=final,
        risk_level=level_from_score(final, cfg),
        risk_impact=impact,
        base_score=_q(cfg.category_base[category], cfg),
        score_breakdown=tuple(breakdown),
        scoring_confidence=_scoring_confidence(assignment, bucket),
        scoring_version=cfg.scoring_version,
        status=status,
        category=category,
        classification_confidence=assignment.classification_confidence,
        perspective=perspective,
        identity_key=assignment.identity_key,
        diff_classification=assignment.diff_classification,
        source_ref=assignment.source_ref,
        target_ref=assignment.target_ref,
    )


def _impact(
    category: RiskCategory,
    classification: DiffClassification | None,
    change: ExactChange | None,
    config: RiskScoreConfig,
) -> RiskImpact:
    policy = config.direction_policy.get(category, DirectionPolicy.MATERIALITY_ONLY)
    if classification is DiffClassification.REMOVED and policy is DirectionPolicy.PROTECTION_LIMIT:
        return RiskImpact.RISK_INCREASING
    if change is None:
        if classification in {DiffClassification.ADDED, DiffClassification.REMOVED}:
            return RiskImpact.UNKNOWN
        return RiskImpact.UNKNOWN
    if change.change_type is ValueChangeType.UNCHANGED_VALUE:
        return RiskImpact.NEUTRAL
    if change.old_value and change.new_value and change.old_value.number == change.new_value.number:
        if not change.currency_changed:
            return RiskImpact.NEUTRAL
    direction = change.direction
    if policy is DirectionPolicy.PROTECTION_LIMIT:
        if direction in _DECREASE_DIRS:
            return RiskImpact.RISK_INCREASING
        if direction in _INCREASE_DIRS:
            return RiskImpact.RISK_DECREASING
        return RiskImpact.UNKNOWN
    if policy is DirectionPolicy.OBLIGATION_BURDEN:
        if direction in _INCREASE_DIRS:
            return RiskImpact.RISK_INCREASING
        if direction in _DECREASE_DIRS:
            return RiskImpact.RISK_DECREASING
        return RiskImpact.UNKNOWN
    return RiskImpact.UNKNOWN


def _impact_delta(impact: RiskImpact, config: RiskScoreConfig) -> float:
    if impact is RiskImpact.RISK_INCREASING:
        return config.impact_increasing
    if impact is RiskImpact.RISK_DECREASING:
        return config.impact_decreasing
    if impact is RiskImpact.NEUTRAL:
        return config.impact_neutral
    return config.impact_unknown


def _magnitude(
    category: RiskCategory,
    change: ExactChange | None,
    config: RiskScoreConfig,
) -> tuple[MagnitudeBucket, str]:
    if change is None:
        return MagnitudeBucket.UNKNOWN, "CMP-06.relative_change:missing"
    if change.old_value and change.new_value and change.old_value.number == change.new_value.number:
        if not change.currency_changed:
            return MagnitudeBucket.VERY_SMALL, "CMP-06.relative_change:0"
    if category is RiskCategory.SLA and change.delta is not None:
        points = abs(float(change.delta))
        return _bucket_sla(points, config), f"CMP-06.delta_pp:{points}"
    relative = change.relative_change_percent
    if relative is None:
        return MagnitudeBucket.UNKNOWN, "CMP-06.relative_change:null"
    return (
        _bucket_relative(abs(float(relative)), config),
        f"CMP-06.relative_change:{relative}",
    )


def _bucket_relative(abs_relative: float, config: RiskScoreConfig) -> MagnitudeBucket:
    if abs_relative < config.rel_small:
        return MagnitudeBucket.VERY_SMALL
    if abs_relative < config.rel_medium:
        return MagnitudeBucket.SMALL
    if abs_relative < config.rel_large:
        return MagnitudeBucket.MEDIUM
    if abs_relative < config.rel_very_large:
        return MagnitudeBucket.LARGE
    return MagnitudeBucket.VERY_LARGE


def _bucket_sla(points: float, config: RiskScoreConfig) -> MagnitudeBucket:
    if points < config.sla_pp_small:
        return MagnitudeBucket.VERY_SMALL
    if points < config.sla_pp_medium:
        return MagnitudeBucket.SMALL
    if points < config.sla_pp_large:
        return MagnitudeBucket.MEDIUM
    if points < config.sla_pp_very_large:
        return MagnitudeBucket.LARGE
    return MagnitudeBucket.VERY_LARGE


def _magnitude_delta(bucket: MagnitudeBucket, config: RiskScoreConfig) -> float:
    return {
        MagnitudeBucket.VERY_SMALL: config.magnitude_very_small,
        MagnitudeBucket.SMALL: config.magnitude_small,
        MagnitudeBucket.MEDIUM: config.magnitude_medium,
        MagnitudeBucket.LARGE: config.magnitude_large,
        MagnitudeBucket.VERY_LARGE: config.magnitude_very_large,
        MagnitudeBucket.UNKNOWN: config.magnitude_unknown,
    }[bucket]


def _change_type_delta(
    classification: DiffClassification | None,
    config: RiskScoreConfig,
) -> float:
    if classification is DiffClassification.ADDED:
        return config.added_delta
    if classification is DiffClassification.REMOVED:
        return config.removed_delta
    return config.modified_delta


def _strongest_change(changes: list[ExactChange]) -> ExactChange | None:
    if not changes:
        return None
    def key(item: ExactChange) -> float:
        if item.relative_change_percent is not None:
            return abs(float(item.relative_change_percent))
        if item.delta is not None:
            return abs(float(item.delta))
        return 0.0
    return max(changes, key=key)


def _finalize(
    factors: list[ScoreFactor],
    raw: float,
    config: RiskScoreConfig,
) -> tuple[float, list[ScoreFactor]]:
    clamped = clamp_score(raw, config)
    final = _q(clamped, config)
    if _q(raw, config) != final:
        factors = [
            *factors,
            ScoreFactor(
                factor="CLAMP",
                delta=_q(final - _q(raw, config), config),
                source="scoring.clamp",
            ),
        ]
    return final, factors


def _q(value: float, config: RiskScoreConfig) -> float:
    return round(float(value), config.score_precision)


def _status(assignment: TaxonomyAssignment, change: ExactChange | None) -> RiskStatus:
    if assignment.classification_status is ClassificationStatus.NEEDS_REVIEW:
        return RiskStatus.NEEDS_REVIEW
    if (
        assignment.primary_category is RiskCategory.OTHER
        and change is None
    ):
        return RiskStatus.NEEDS_REVIEW
    return RiskStatus.SCORED


def _scoring_confidence(
    assignment: TaxonomyAssignment,
    bucket: MagnitudeBucket,
) -> ScoringConfidence:
    if (
        assignment.classification_confidence is ClassificationConfidence.LOW
        or assignment.primary_category is RiskCategory.OTHER
    ):
        return ScoringConfidence.LOW
    if (
        bucket is MagnitudeBucket.UNKNOWN
        or assignment.classification_confidence is ClassificationConfidence.MEDIUM
    ):
        return ScoringConfidence.MEDIUM
    return ScoringConfidence.HIGH


def _not_applicable(
    assignment: TaxonomyAssignment,
    config: RiskScoreConfig,
    perspective: RiskPerspective,
) -> RiskScoreResult:
    return RiskScoreResult(
        risk_score=0.0,
        risk_level=RiskLevel.LOW,
        risk_impact=RiskImpact.NEUTRAL,
        base_score=0.0,
        score_breakdown=(),
        scoring_confidence=ScoringConfidence.HIGH,
        scoring_version=config.scoring_version,
        status=RiskStatus.NOT_APPLICABLE,
        category=assignment.primary_category,
        classification_confidence=assignment.classification_confidence,
        perspective=perspective,
        identity_key=assignment.identity_key,
        diff_classification=assignment.diff_classification,
        source_ref=assignment.source_ref,
        target_ref=assignment.target_ref,
    )


def _failed(
    assignment: TaxonomyAssignment,
    config: RiskScoreConfig,
    perspective: RiskPerspective,
) -> RiskScoreResult:
    score = _q(config.fallback_score, config)
    return RiskScoreResult(
        risk_score=score,
        risk_level=level_from_score(score, config),
        risk_impact=RiskImpact.UNKNOWN,
        base_score=score,
        score_breakdown=(
            ScoreFactor(factor="FALLBACK", delta=score, source="scoring.fallback"),
        ),
        scoring_confidence=ScoringConfidence.LOW,
        scoring_version=config.scoring_version,
        status=RiskStatus.FAILED,
        category=assignment.primary_category,
        classification_confidence=assignment.classification_confidence,
        perspective=perspective,
        identity_key=assignment.identity_key,
        diff_classification=assignment.diff_classification,
        source_ref=assignment.source_ref,
        target_ref=assignment.target_ref,
    )


def _index_changes(exact: ExactDiffResult | None) -> dict[str, list[ExactChange]]:
    grouped: dict[str, list[ExactChange]] = {}
    if exact is None:
        return grouped
    for change in exact.changes:
        for ref in (change.source_ref, change.target_ref):
            if ref and ref.identity_key:
                grouped.setdefault(ref.identity_key, []).append(change)
                break
    return grouped


def _changes_for(
    assignment: TaxonomyAssignment,
    grouped: dict[str, list[ExactChange]],
) -> list[ExactChange]:
    keys: list[str] = []
    if assignment.identity_key:
        keys.append(assignment.identity_key)
    if assignment.source_ref and assignment.source_ref.identity_key:
        keys.append(assignment.source_ref.identity_key)
    if assignment.target_ref and assignment.target_ref.identity_key:
        keys.append(assignment.target_ref.identity_key)
    rows: list[ExactChange] = []
    seen: set[int] = set()
    for key in keys:
        for change in grouped.get(key, []):
            marker = id(change)
            if marker in seen:
                continue
            seen.add(marker)
            rows.append(change)
    return rows


def _dir_label(change: ExactChange | None) -> str:
    if change is None:
        return "missing"
    return change.direction.value


def _cls(assignment: TaxonomyAssignment) -> str:
    if assignment.diff_classification is None:
        return "missing"
    return assignment.diff_classification.value


def _metadata(
    rows: list[RiskScoreResult],
    *,
    fallback: int,
    review: int,
    duration_ms: int,
) -> dict[str, Any]:
    levels = {item.value: 0 for item in RiskLevel}
    categories = {item.value: 0 for item in RiskCategory}
    total = 0.0
    unknown_perspective = 0
    for row in rows:
        levels[row.risk_level.value] += 1
        categories[row.category.value] += 1
        total += row.risk_score
        if row.perspective is RiskPerspective.UNKNOWN:
            unknown_perspective += 1
    count = len(rows) or 1
    return {
        "scoring_version": SCORING_VERSION,
        "findings_scored": len(rows),
        "risk_level_counts": levels,
        "category_counts": categories,
        "average_score": round(total / count, 1),
        "fallback_count": fallback,
        "needs_review_count": review,
        "unknown_perspective_count": unknown_perspective,
        "scoring_latency_ms": duration_ms,
        "scoring_llm_calls": 0,
    }
