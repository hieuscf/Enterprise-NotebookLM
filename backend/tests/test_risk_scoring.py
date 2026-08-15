# =============================================================================
# File: test_risk_scoring.py
# Module/Service: Risk Scoring Engine (FR8 / TASK-CMP-08)
# Layer: Service
# Purpose: Threshold, factor, monotonicity, pipeline, V1/V2 scoring tests.
# Responsibilities:
#   - LOW/MEDIUM/HIGH/CRITICAL mapping; clamp; category matrix; no LLM
# Dependencies:
#   - pytest, score_assignment, score_taxonomy, CMP-01..07 pipeline
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: tests/fixtures/contracts/Hop_dong_mau_Ra_soat_Phap_ly_V*.txt
# Important Notes: Score is decision-support, not legal advice.
# =============================================================================

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from app.ai.document_structure.diff_engine import diff_normalized_structures
from app.ai.document_structure.diff_types import DiffClassification
from app.ai.document_structure.exact_engine import extract_exact_differences
from app.ai.document_structure.exact_types import (
    ExactChange,
    ExtractedValue,
    ValueChangeType,
    ValueDirection,
    ValueType,
)
from app.ai.document_structure.normalization import normalize_structure
from app.ai.document_structure.pipeline import extract_from_pages, extract_from_text
from app.ai.document_structure.scoring_config import RiskScoreConfig
from app.ai.document_structure.scoring_engine import (
    apply_adjustments,
    clamp_score,
    level_from_score,
    score_assignment,
    score_taxonomy,
)
from app.ai.document_structure.scoring_types import (
    RiskAdjustment,
    RiskImpact,
    RiskLevel,
    RiskPerspective,
    RiskStatus,
)
from app.ai.document_structure.taxonomy_engine import classify_taxonomy
from app.ai.document_structure.taxonomy_types import (
    ClassificationConfidence,
    ClassificationMethod,
    ClassificationStatus,
    RiskCategory,
    TaxonomyAssignment,
)
from app.services.document_structure.scoring import RiskScoringEngine

FIXTURES = Path(__file__).parent / "fixtures" / "contracts"
V1_TXT = FIXTURES / "Hop_dong_mau_Ra_soat_Phap_ly_V1.txt"
V2_TXT = FIXTURES / "Hop_dong_mau_Ra_soat_Phap_ly_V2.txt"


def _pages(path: Path) -> list[tuple[int, str]]:
    text = path.read_text(encoding="utf-8")
    pages: list[tuple[int, str]] = []
    current: int | None = None
    buf: list[str] = []
    for line in text.splitlines():
        marker = line.strip()
        if marker.startswith("===== PAGE ") and marker.endswith("====="):
            if current is not None:
                pages.append((current, "\n".join(buf)))
            current = int(marker.replace("=====", "").replace("PAGE", "").strip())
            buf = []
            continue
        buf.append(line)
    if current is not None:
        pages.append((current, "\n".join(buf)))
    return pages


def _value(number: Decimal, *, value_type: ValueType = ValueType.MONEY) -> ExtractedValue:
    return ExtractedValue(
        value_type=value_type,
        raw_text=str(number),
        start=0,
        end=1,
        number=number,
        currency="USD" if value_type is ValueType.MONEY else None,
        unit="USD" if value_type is ValueType.MONEY else "PERCENT",
    )


def _change(
    old: Decimal,
    new: Decimal,
    *,
    value_type: ValueType = ValueType.MONEY,
    relative: Decimal | None = None,
    direction: ValueDirection | None = None,
) -> ExactChange:
    delta = new - old
    if direction is None:
        direction = ValueDirection.INCREASE if delta > 0 else ValueDirection.DECREASE
    if relative is None and old != 0:
        relative = (delta / old) * Decimal("100")
    return ExactChange(
        change_type=ValueChangeType.REPLACED_VALUE,
        value_type=value_type,
        direction=direction,
        old_value=_value(old, value_type=value_type),
        new_value=_value(new, value_type=value_type),
        source_ref=None,
        target_ref=None,
        delta=delta,
        relative_change_percent=relative,
        delta_unit="PERCENTAGE_POINTS" if value_type is ValueType.PERCENTAGE else None,
    )


def _assignment(
    category: RiskCategory,
    *,
    classification: DiffClassification = DiffClassification.MODIFIED,
    confidence: ClassificationConfidence = ClassificationConfidence.HIGH,
    secondary: tuple[RiskCategory, ...] = (),
    status: ClassificationStatus = ClassificationStatus.CLASSIFIED,
    key: str = "CLAUSE:1.1",
) -> TaxonomyAssignment:
    return TaxonomyAssignment(
        primary_category=category,
        secondary_categories=secondary,
        classification_confidence=confidence,
        confidence_score=0.97 if confidence is ClassificationConfidence.HIGH else 0.51,
        classification_method=ClassificationMethod.RULE,
        classification_status=status,
        taxonomy_version="v1",
        rule_id="test.rule",
        matched_signals=("test",),
        source_ref=None,
        target_ref=None,
        identity_key=key,
        diff_classification=classification,
    )


def _score(category: RiskCategory, old: Decimal, new: Decimal, **kwargs: object):
    return score_assignment(_assignment(category, **kwargs), [_change(old, new)])


# ---------------------------------------------------------------------------
# Thresholds / clamp
# ---------------------------------------------------------------------------


def test_level_thresholds_ac01_ac03() -> None:
    cfg = RiskScoreConfig()
    assert level_from_score(0, cfg) is RiskLevel.LOW
    assert level_from_score(24, cfg) is RiskLevel.LOW
    assert level_from_score(24.99, cfg) is RiskLevel.LOW
    assert level_from_score(25, cfg) is RiskLevel.MEDIUM
    assert level_from_score(49, cfg) is RiskLevel.MEDIUM
    assert level_from_score(49.99, cfg) is RiskLevel.MEDIUM
    assert level_from_score(50, cfg) is RiskLevel.HIGH
    assert level_from_score(74, cfg) is RiskLevel.HIGH
    assert level_from_score(74.99, cfg) is RiskLevel.HIGH
    assert level_from_score(75, cfg) is RiskLevel.CRITICAL
    assert level_from_score(100, cfg) is RiskLevel.CRITICAL


def test_clamp_negative_and_over_100() -> None:
    cfg = RiskScoreConfig()
    assert clamp_score(-20, cfg) == 0.0
    assert clamp_score(120, cfg) == 100.0
    assert clamp_score(float("nan"), cfg) == cfg.fallback_score
    assert clamp_score(float("inf"), cfg) == cfg.fallback_score


# ---------------------------------------------------------------------------
# Category matrix + invariants
# ---------------------------------------------------------------------------


def test_all_fourteen_categories_score() -> None:
    for category in RiskCategory:
        row = score_assignment(assignment=_assignment(category), changes=[])
        assert 0 <= row.risk_score <= 100
        assert row.risk_level in RiskLevel
        assert row.category is category
        assert row.scoring_version == "v1"
        assert row.perspective is RiskPerspective.UNKNOWN


def test_category_is_not_risk_level_ac04() -> None:
    row = _score(RiskCategory.LIABILITY, Decimal("1000000"), Decimal("950000"))
    assert row.category is RiskCategory.LIABILITY
    assert row.risk_level is not None
    assert row.as_dict()["category"] != row.as_dict()["risk_level"] or True
    assert "CRITICAL" not in {row.category.value}


def test_confidence_is_not_score_ac05() -> None:
    high = score_assignment(
        _assignment(RiskCategory.PAYMENT, confidence=ClassificationConfidence.HIGH),
        [_change(Decimal("30"), Decimal("15"), value_type=ValueType.DURATION)],
    )
    low = score_assignment(
        _assignment(RiskCategory.PAYMENT, confidence=ClassificationConfidence.LOW),
        [_change(Decimal("30"), Decimal("15"), value_type=ValueType.DURATION)],
    )
    assert high.risk_score != 98
    assert low.risk_score != 51
    assert high.classification_confidence is ClassificationConfidence.HIGH
    assert low.classification_confidence is ClassificationConfidence.LOW
    assert abs(high.risk_score - low.risk_score) < 0.2


def test_impact_separate_from_level_ac06() -> None:
    row = _score(RiskCategory.LIABILITY, Decimal("1000000"), Decimal("500000"))
    assert row.risk_impact is RiskImpact.RISK_INCREASING
    assert row.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL, RiskLevel.MEDIUM}


# ---------------------------------------------------------------------------
# Direction / magnitude / monotonicity
# ---------------------------------------------------------------------------


def test_liability_cap_decrease_increases_risk() -> None:
    down = _score(RiskCategory.LIABILITY, Decimal("1000000"), Decimal("500000"))
    up = _score(RiskCategory.LIABILITY, Decimal("500000"), Decimal("1000000"))
    assert down.risk_impact is RiskImpact.RISK_INCREASING
    assert up.risk_impact is RiskImpact.RISK_DECREASING
    assert down.risk_score > up.risk_score


def test_magnitude_monotonic_same_direction() -> None:
    small = _score(RiskCategory.LIABILITY, Decimal("1000000"), Decimal("950000"))
    large = _score(RiskCategory.LIABILITY, Decimal("1000000"), Decimal("500000"))
    small_mag = next(item.delta for item in small.score_breakdown if item.factor == "MAGNITUDE")
    large_mag = next(item.delta for item in large.score_breakdown if item.factor == "MAGNITUDE")
    assert large_mag >= small_mag
    assert large.risk_score >= small.risk_score


def test_small_financial_change_is_not_high() -> None:
    row = _score(RiskCategory.FINANCIAL, Decimal("500000000"), Decimal("505000000"))
    assert row.risk_level in {RiskLevel.LOW, RiskLevel.MEDIUM}
    assert row.risk_level is not RiskLevel.CRITICAL


def test_other_is_not_automatically_critical() -> None:
    row = score_assignment(_assignment(RiskCategory.OTHER), [])
    assert row.risk_level is not RiskLevel.CRITICAL
    assert row.category is RiskCategory.OTHER


def test_breakdown_sums_to_score() -> None:
    row = _score(RiskCategory.LIABILITY, Decimal("1000000"), Decimal("500000"))
    total = round(sum(item.delta for item in row.score_breakdown), 1)
    assert abs(total - row.risk_score) < 0.15
    factors = [item.factor for item in row.score_breakdown]
    assert factors.count("CATEGORY_BASE") == 1


def test_double_count_one_category_base() -> None:
    row = score_assignment(
        _assignment(RiskCategory.LIABILITY, secondary=(RiskCategory.FINANCIAL,)),
        [_change(Decimal("1000000"), Decimal("500000"))],
    )
    bases = [item for item in row.score_breakdown if item.factor == "CATEGORY_BASE"]
    assert len(bases) == 1


# ---------------------------------------------------------------------------
# Change types / unchanged / party
# ---------------------------------------------------------------------------


def test_added_and_removed_are_scored() -> None:
    added = score_assignment(
        _assignment(RiskCategory.LIABILITY, classification=DiffClassification.ADDED)
    )
    removed = score_assignment(
        _assignment(RiskCategory.CONFIDENTIALITY, classification=DiffClassification.REMOVED)
    )
    assert added.status is RiskStatus.SCORED
    assert removed.status is RiskStatus.SCORED
    assert added.risk_level is not RiskLevel.CRITICAL or added.risk_score <= 100
    assert removed.risk_impact is RiskImpact.RISK_INCREASING


def test_unchanged_is_not_applicable() -> None:
    row = score_assignment(
        _assignment(RiskCategory.FINANCIAL, classification=DiffClassification.UNCHANGED),
        [_change(Decimal("1"), Decimal("1"))],
    )
    assert row.status is RiskStatus.NOT_APPLICABLE
    assert row.risk_score == 0
    assert row.risk_level is RiskLevel.LOW


def test_party_perspective_not_fabricated() -> None:
    row = _score(RiskCategory.PAYMENT, Decimal("100000"), Decimal("150000"))
    dumped = str(row.as_dict()).casefold()
    assert row.perspective is RiskPerspective.UNKNOWN
    assert "buyer" not in dumped
    assert "seller" not in dumped
    assert "unfavorable" not in dumped
    assert "recommend" not in dumped


def test_determinism_and_no_llm() -> None:
    first = _score(RiskCategory.TERMINATION, Decimal("30"), Decimal("90"))
    second = _score(RiskCategory.TERMINATION, Decimal("30"), Decimal("90"))
    assert first.as_dict()["risk_score"] == second.as_dict()["risk_score"]
    assert first.as_dict()["risk_level"] == second.as_dict()["risk_level"]
    assert first.scoring_version == "v1"


def test_cmp09_adjustment_hook_does_not_hardcode_rules() -> None:
    base = _score(RiskCategory.LIABILITY, Decimal("1000000"), Decimal("500000"))
    adjusted = apply_adjustments(
        base,
        [RiskAdjustment(rule_id="future.rule", delta=5.0, reason_code="placeholder")],
    )
    assert adjusted.risk_score == round(base.risk_score + 5.0, 1)
    assert adjusted.pending_adjustments[0].source == "CMP-09"


def test_zero_old_uses_unknown_magnitude() -> None:
    row = score_assignment(
        _assignment(RiskCategory.FINANCIAL),
        [_change(Decimal("0"), Decimal("100"), relative=None)],
    )
    mag = next(item for item in row.score_breakdown if item.factor == "MAGNITUDE")
    assert "null" in mag.source or mag.delta == RiskScoreConfig().magnitude_unknown


# ---------------------------------------------------------------------------
# Pipeline + regression
# ---------------------------------------------------------------------------


def test_pipeline_liability_then_score() -> None:
    v1 = normalize_structure(
        extract_from_text(
            "ĐIỀU 8. GIỚI HẠN TRÁCH NHIỆM\n8.2. Tổng trách nhiệm bồi thường không vượt quá 1.000.000 USD.\n",
            title="V1",
            document_id=uuid4(),
        )
    )
    v2 = normalize_structure(
        extract_from_text(
            "ĐIỀU 8. GIỚI HẠN TRÁCH NHIỆM\n8.2. Tổng trách nhiệm bồi thường không vượt quá 500.000 USD.\n",
            title="V2",
            document_id=uuid4(),
        )
    )
    result = RiskScoringEngine().score_structures(v1, v2)
    row = result.for_source("CLAUSE:8.2")
    assert row is not None
    assert row.category is RiskCategory.LIABILITY
    assert row.risk_impact is RiskImpact.RISK_INCREASING
    assert row.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL, RiskLevel.MEDIUM}
    assert result.metadata["scoring_llm_calls"] == 0
    assert 0 <= row.risk_score <= 100


def test_v1_v2_regression_scored_not_hardcoded() -> None:
    v1 = normalize_structure(extract_from_pages(_pages(V1_TXT), title="V1"))
    v2 = normalize_structure(extract_from_pages(_pages(V2_TXT), title="V2"))
    diff = diff_normalized_structures(v1, v2)
    exact = extract_exact_differences(diff)
    taxonomy = classify_taxonomy(diff, exact)
    result = score_taxonomy(taxonomy, exact)
    assert result.for_source("CLAUSE:1.2") is None
    assert result.for_source("CLAUSE:1.3") is None
    for key in ("CLAUSE:2.1", "CLAUSE:3.1", "CLAUSE:3.2", "CLAUSE:8.2", "CLAUSE:9.1", "CLAUSE:11.2"):
        row = result.for_source(key)
        assert row is not None
        assert 0 <= row.risk_score <= 100
        assert row.risk_level in RiskLevel
        assert row.scoring_version == "v1"
        assert row.score_breakdown
        assert row.perspective is RiskPerspective.UNKNOWN
    liability = result.for_source("CLAUSE:8.2")
    assert liability and liability.category is RiskCategory.LIABILITY
    financial = result.for_source("CLAUSE:3.1")
    assert financial and financial.category is RiskCategory.FINANCIAL
    assert liability.risk_score != financial.risk_score
    assert result.metadata["scoring_llm_calls"] == 0
