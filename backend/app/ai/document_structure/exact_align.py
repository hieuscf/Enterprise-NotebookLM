# =============================================================================
# File: exact_align.py
# Module/Service: Exact Difference Detection (FR8 / TASK-CMP-06)
# Layer: Service
# Purpose: Pair old/new extracted values using CMP-04 spans, type, unit, context.
# Responsibilities:
#   - Diff-span-first pairing (never zip-by-index across the whole clause)
#   - Greedy one-to-one leftover alignment by type + context + position
#   - Decimal delta / relative % / direction (no FX, no month↔day conversion)
# Dependencies:
#   - exact_types, exact_config, exact_parse, mapping_similarity.tokenize
# Public Exports:
#   - align_values, compute_change
# Database/Table: N/A
# Related Modules: exact_engine
# Important Notes: 0 LLM. Compatible types only. Zero denominator → relative=None.
# =============================================================================

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from app.ai.document_structure.diff_types import TextChange
from app.ai.document_structure.exact_config import ExactDiffConfig
from app.ai.document_structure.exact_parse import extract_values
from app.ai.document_structure.exact_types import (
    ExtractedValue,
    ParseStatus,
    ValueChangeType,
    ValueDirection,
    ValueType,
)
from app.ai.document_structure.mapping_similarity import lexical_similarity

_YEAR_MONTHS = Decimal("12")


def align_values(
    old_values: list[ExtractedValue],
    new_values: list[ExtractedValue],
    *,
    changes: list[TextChange] | None = None,
    config: ExactDiffConfig | None = None,
) -> list[tuple[ExtractedValue | None, ExtractedValue | None, str]]:
    """Return (old, new, method) pairs. Unchanged same-normalized values omitted."""
    cfg = config or ExactDiffConfig()
    used_old: set[int] = set()
    used_new: set[int] = set()
    pairs: list[tuple[ExtractedValue | None, ExtractedValue | None, str]] = []

    for change in changes or []:
        span_old = extract_values(change.old, config=cfg)
        span_new = extract_values(change.new, config=cfg)
        linked = _link_span(span_old, span_new, old_values, new_values, used_old, used_new)
        pairs.extend(linked)

    leftovers_old = [item for item in old_values if id(item) not in used_old]
    leftovers_new = [item for item in new_values if id(item) not in used_new]
    scored: list[tuple[float, ExtractedValue, ExtractedValue]] = []
    for left in leftovers_old:
        for right in leftovers_new:
            score = _alignment_score(left, right)
            if score >= cfg.min_alignment_score:
                scored.append((score, left, right))
    scored.sort(key=lambda item: (-item[0], item[1].start, item[2].start))
    for _score, left, right in scored:
        if id(left) in used_old or id(right) in used_new:
            continue
        used_old.add(id(left))
        used_new.add(id(right))
        pairs.append((left, right, "context"))

    for left in leftovers_old:
        if id(left) not in used_old:
            pairs.append((left, None, "unpaired"))
    for right in leftovers_new:
        if id(right) not in used_new:
            pairs.append((None, right, "unpaired"))
    return pairs


def compute_change(
    old: ExtractedValue | None,
    new: ExtractedValue | None,
    *,
    config: ExactDiffConfig | None = None,
    method: str = "unaligned",
) -> tuple[ValueChangeType, ValueDirection, Decimal | None, Decimal | None, str | None, bool, ParseStatus]:
    """Facts only. Currency mismatch does not invent an FX delta."""
    cfg = config or ExactDiffConfig()
    if old is None and new is not None:
        return (
            ValueChangeType.ADDED_VALUE,
            ValueDirection.ADDED,
            new.number,
            None,
            new.unit,
            False,
            new.parse_status,
        )
    if old is not None and new is None:
        return (
            ValueChangeType.REMOVED_VALUE,
            ValueDirection.REMOVED,
            None,
            None,
            old.unit,
            False,
            old.parse_status,
        )
    assert old is not None and new is not None
    currency_changed = bool(old.currency and new.currency and old.currency != new.currency)
    if old.value_type is ValueType.DATE and new.value_type is ValueType.DATE:
        return _date_change(old, new)
    if old.value_type in {ValueType.ORGANIZATION, ValueType.LOCATION}:
        same = (old.entity_text or "") == (new.entity_text or "")
        if same:
            return (
                ValueChangeType.FORMAT_ONLY if old.raw_text != new.raw_text else ValueChangeType.UNCHANGED_VALUE,
                ValueDirection.UNCHANGED,
                None,
                None,
                old.unit,
                False,
                ParseStatus.PARSED,
            )
        return (
            ValueChangeType.REPLACED_VALUE,
            ValueDirection.REPLACED,
            None,
            None,
            old.unit,
            False,
            ParseStatus.PARSED,
        )

    old_num = _normalized_number(old, cfg)
    new_num = _normalized_number(new, cfg)
    if old_num is None or new_num is None:
        if _same_identity(old, new):
            return (
                ValueChangeType.FORMAT_ONLY,
                ValueDirection.UNCHANGED,
                None,
                None,
                old.unit,
                currency_changed,
                ParseStatus.NEEDS_REVIEW,
            )
        return (
            ValueChangeType.REPLACED_VALUE,
            ValueDirection.REPLACED,
            None,
            None,
            None,
            currency_changed,
            ParseStatus.NEEDS_REVIEW,
        )
    if currency_changed:
        return (
            ValueChangeType.REPLACED_VALUE,
            ValueDirection.REPLACED,
            None,
            None,
            None,
            True,
            ParseStatus.PARSED,
        )
    if old.unit != new.unit and not _duration_convertible(old, new):
        return (
            ValueChangeType.REPLACED_VALUE,
            ValueDirection.UNKNOWN,
            None,
            None,
            None,
            False,
            ParseStatus.NEEDS_REVIEW,
        )
    if (
        old.value_type is ValueType.DURATION
        and new.value_type is ValueType.DURATION
        and old.duration_kind
        and new.duration_kind
        and old.duration_kind != new.duration_kind
    ):
        return (
            ValueChangeType.REPLACED_VALUE,
            ValueDirection.REPLACED,
            None,
            None,
            old.unit,
            False,
            ParseStatus.NEEDS_REVIEW,
        )
    delta = new_num - old_num
    relative = _relative(old_num, delta, cfg)
    if delta == 0:
        change = (
            ValueChangeType.FORMAT_ONLY
            if old.raw_text.replace(" ", "") != new.raw_text.replace(" ", "")
            else ValueChangeType.UNCHANGED_VALUE
        )
        return change, ValueDirection.UNCHANGED, Decimal("0"), Decimal("0"), _delta_unit(old), False, ParseStatus.PARSED
    direction = ValueDirection.INCREASE if delta > 0 else ValueDirection.DECREASE
    delta_unit = "PERCENTAGE_POINTS" if old.value_type is ValueType.PERCENTAGE else _delta_unit(old)
    return (
        ValueChangeType.REPLACED_VALUE,
        direction,
        delta,
        relative,
        delta_unit,
        False,
        ParseStatus.PARSED,
    )


def _link_span(
    span_old: list[ExtractedValue],
    span_new: list[ExtractedValue],
    old_values: list[ExtractedValue],
    new_values: list[ExtractedValue],
    used_old: set[int],
    used_new: set[int],
) -> list[tuple[ExtractedValue | None, ExtractedValue | None, str]]:
    pairs: list[tuple[ExtractedValue | None, ExtractedValue | None, str]] = []
    if len(span_old) == 1 and len(span_new) == 1 and span_old[0].value_type is span_new[0].value_type:
        left = _resolve(span_old[0], old_values, used_old)
        right = _resolve(span_new[0], new_values, used_new)
        if left or right:
            pairs.append((left, right, "diff_span"))
        return pairs
    # One-sided spans are often a split number ("06" / "12") without a unit.
    # Defer those to context alignment so 06 tháng can pair with 12 tháng.
    return pairs


def _resolve(
    hint: ExtractedValue,
    pool: list[ExtractedValue],
    used: set[int],
) -> ExtractedValue | None:
    for item in pool:
        if id(item) in used:
            continue
        if item.value_type is hint.value_type and _same_identity(item, hint):
            used.add(id(item))
            return item
    for item in pool:
        if id(item) in used:
            continue
        if item.value_type is hint.value_type and item.raw_text.casefold() == hint.raw_text.casefold():
            used.add(id(item))
            return item
    return None


def _alignment_score(left: ExtractedValue, right: ExtractedValue) -> float:
    if left.value_type is not right.value_type:
        return 0.0
    context = lexical_similarity(
        f"{left.left_context} {left.right_context}",
        f"{right.left_context} {right.right_context}",
    )
    lead = lexical_similarity(left.left_context, right.left_context)
    unit = 1.0 if left.unit == right.unit else 0.35
    index = 1.0 if left.index_in_type == right.index_in_type else 0.4
    qualifier = 1.0 if left.qualifier is right.qualifier else 0.6
    return 0.35 + 0.25 * context + 0.20 * lead + 0.10 * unit + 0.07 * index + 0.03 * qualifier


def _same_identity(left: ExtractedValue, right: ExtractedValue) -> bool:
    if left.value_type is ValueType.DATE:
        return left.iso_date == right.iso_date and left.iso_date is not None
    if left.entity_text or right.entity_text:
        return (left.entity_text or "") == (right.entity_text or "")
    return (
        left.number == right.number
        and left.number_max == right.number_max
        and left.unit == right.unit
        and left.currency == right.currency
    )


def _normalized_number(value: ExtractedValue, config: ExactDiffConfig) -> Decimal | None:
    if value.number is None:
        return None
    if value.value_type is ValueType.DURATION:
        if value.unit == "YEAR":
            return value.number * Decimal(config.year_to_months)
        if value.unit == "MONTH":
            return value.number
        if value.unit == "DAY":
            return value.number
        return None
    return value.number


def _duration_convertible(old: ExtractedValue, new: ExtractedValue) -> bool:
    units = {old.unit, new.unit}
    return units <= {"YEAR", "MONTH"} or old.unit == new.unit


def _relative(old: Decimal, delta: Decimal, config: ExactDiffConfig) -> Decimal | None:
    if old == 0:
        return None
    try:
        raw = (delta / old) * Decimal("100")
    except (InvalidOperation, ZeroDivisionError):
        return None
    quant = Decimal("1").scaleb(-config.relative_precision)
    return raw.quantize(quant, rounding=ROUND_HALF_UP)


def _delta_unit(value: ExtractedValue) -> str | None:
    if value.value_type is ValueType.DURATION and value.unit == "YEAR":
        return "MONTH"
    return value.unit


def _date_change(
    old: ExtractedValue, new: ExtractedValue
) -> tuple[ValueChangeType, ValueDirection, Decimal | None, Decimal | None, str | None, bool, ParseStatus]:
    if old.iso_date is None or new.iso_date is None:
        return (
            ValueChangeType.REPLACED_VALUE,
            ValueDirection.UNKNOWN,
            None,
            None,
            "DAY",
            False,
            ParseStatus.NEEDS_REVIEW,
        )
    delta_days = Decimal((new.iso_date - old.iso_date).days)
    if delta_days == 0:
        return (
            ValueChangeType.FORMAT_ONLY if old.raw_text != new.raw_text else ValueChangeType.UNCHANGED_VALUE,
            ValueDirection.UNCHANGED,
            Decimal("0"),
            None,
            "DAY",
            False,
            ParseStatus.PARSED,
        )
    direction = ValueDirection.LATER if delta_days > 0 else ValueDirection.EARLIER
    return (
        ValueChangeType.REPLACED_VALUE,
        direction,
        delta_days,
        None,
        "DAY",
        False,
        ParseStatus.PARSED,
    )
