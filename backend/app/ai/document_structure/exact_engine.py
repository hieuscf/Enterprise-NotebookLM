# =============================================================================
# File: exact_engine.py
# Module/Service: Exact Difference Detection (FR8 / TASK-CMP-06)
# Layer: Service
# Purpose: Turn CMP-04 clause diffs into typed, measurable ExactChange rows.
# Responsibilities:
#   - Skip UNCHANGED / AMBIGUOUS / UNKNOWN (no expensive parse)
#   - MODIFIED: extract + align via diff spans then context
#   - ADDED/REMOVED: one-sided value extraction
#   - Bind ClauseRef + local offsets when the raw snippet exists in original_text
# Dependencies:
#   - diff_types.DiffResult, exact_parse, exact_align, exact_config
# Public Exports:
#   - extract_exact_differences, extract_from_clause_diff
# Database/Table: N/A
# Related Modules: ClauseExactDiffEngine; CMP-07 consumes ExactChange facts
# Important Notes:
#   - 0 LLM. Does not remap clauses or classify legal risk.
#   - Does not invent offsets. Format-only money is omitted unless configured.
# =============================================================================

from __future__ import annotations

import time
from typing import Any

from app.ai.document_structure.diff_types import (
    ClauseDiff,
    DiffClassification,
    DiffResult,
)
from app.ai.document_structure.exact_align import align_values, compute_change
from app.ai.document_structure.exact_config import ExactDiffConfig
from app.ai.document_structure.exact_parse import extract_values
from app.ai.document_structure.exact_types import (
    ExactChange,
    ExactDiffResult,
    ExtractedValue,
    ParseStatus,
    ValueChangeType,
    ValueType,
)
from app.ai.document_structure.normalization import NormalizedUnit

_SKIP = frozenset(
    {
        DiffClassification.UNCHANGED,
        DiffClassification.AMBIGUOUS_MAPPING,
        DiffClassification.UNKNOWN,
    }
)


def extract_exact_differences(
    diff: DiffResult,
    *,
    config: ExactDiffConfig | None = None,
) -> ExactDiffResult:
    """Extract typed value changes from a complete CMP-04 result."""
    started = time.perf_counter()
    cfg = config or ExactDiffConfig()
    rows: list[ExactChange] = []
    processed = 0
    for item in diff.diffs:
        if item.classification in _SKIP:
            continue
        processed += 1
        rows.extend(extract_from_clause_diff(item, config=cfg))
    duration_ms = int((time.perf_counter() - started) * 1000)
    return ExactDiffResult(
        source_document_id=diff.source_document_id,
        target_document_id=diff.target_document_id,
        source_version_id=diff.source_version_id,
        target_version_id=diff.target_version_id,
        changes=rows,
        diff_metadata=dict(diff.metadata),
        metadata=_metadata(rows, processed=processed, duration_ms=duration_ms),
    )


def extract_from_clause_diff(
    item: ClauseDiff,
    *,
    config: ExactDiffConfig | None = None,
) -> list[ExactChange]:
    """One clause row → zero or more ExactChange facts."""
    cfg = config or ExactDiffConfig()
    if item.classification in _SKIP:
        return []
    source_text = _clause_text(item.source_unit)
    target_text = _clause_text(item.target_unit)
    if item.classification is DiffClassification.ADDED:
        return [
            _to_change(None, value, item, config=cfg, method="added_clause")
            for value in extract_values(target_text, config=cfg)
        ]
    if item.classification is DiffClassification.REMOVED:
        return [
            _to_change(value, None, item, config=cfg, method="removed_clause")
            for value in extract_values(source_text, config=cfg)
        ]
    old_values = extract_values(source_text, config=cfg)
    new_values = extract_values(target_text, config=cfg)
    pairs = align_values(
        old_values,
        new_values,
        changes=item.changes,
        config=cfg,
    )
    rows: list[ExactChange] = []
    for old, new, method in pairs:
        change = _to_change(old, new, item, config=cfg, method=method)
        if _should_keep(change, cfg):
            rows.append(change)
    return rows


def _to_change(
    old: ExtractedValue | None,
    new: ExtractedValue | None,
    item: ClauseDiff,
    *,
    config: ExactDiffConfig,
    method: str,
) -> ExactChange:
    value_type = (old or new).value_type if (old or new) else ValueType.NUMBER
    change_type, direction, delta, relative, delta_unit, currency_changed, status = (
        compute_change(old, new, config=config, method=method)
    )
    source_offset, source_span = _locate(item.source_unit, old)
    target_offset, target_span = _locate(item.target_unit, new)
    context = (new.sentence if new and new.sentence else None) or (
        old.sentence if old else ""
    )
    return ExactChange(
        change_type=change_type,
        value_type=value_type,
        direction=direction,
        old_value=old,
        new_value=new,
        source_ref=item.source_ref,
        target_ref=item.target_ref,
        delta=delta,
        relative_change_percent=relative,
        delta_unit=delta_unit,
        currency_changed=currency_changed,
        parse_status=status,
        source_span_status=source_span,
        target_span_status=target_span,
        source_offset=source_offset,
        target_offset=target_offset,
        context=context[:200],
        alignment_method=method,
    )


def _should_keep(change: ExactChange, config: ExactDiffConfig) -> bool:
    if change.change_type is ValueChangeType.UNCHANGED_VALUE:
        return config.include_unchanged_values
    if change.change_type is ValueChangeType.FORMAT_ONLY:
        return config.include_format_only or config.include_unchanged_values
    return True


def _clause_text(unit: NormalizedUnit | None) -> str:
    if unit is None:
        return ""
    original = (unit.original_text or "").strip()
    if original:
        return original
    return (unit.normalized_body or unit.folded_body or "").strip()


def _locate(
    unit: NormalizedUnit | None,
    value: ExtractedValue | None,
) -> tuple[tuple[int, int] | None, ParseStatus]:
    if unit is None or value is None:
        return None, ParseStatus.UNAVAILABLE
    haystack = unit.original_text or ""
    needle = value.raw_text
    if not haystack or not needle:
        return None, ParseStatus.UNAVAILABLE
    pos = haystack.find(needle)
    if pos < 0:
        pos = haystack.casefold().find(needle.casefold())
    if pos < 0:
        return None, ParseStatus.UNAVAILABLE
    return (pos, pos + len(needle)), ParseStatus.PARSED


def _metadata(
    rows: list[ExactChange],
    *,
    processed: int,
    duration_ms: int,
) -> dict[str, Any]:
    counts = {item.value: 0 for item in ValueType}
    change_counts = {item.value: 0 for item in ValueChangeType}
    review = 0
    for row in rows:
        counts[row.value_type.value] += 1
        change_counts[row.change_type.value] += 1
        if row.parse_status is ParseStatus.NEEDS_REVIEW:
            review += 1
    return {
        "clauses_processed": processed,
        "values_detected": len(rows),
        "changes_detected": change_counts[ValueChangeType.REPLACED_VALUE.value]
        + change_counts[ValueChangeType.ADDED_VALUE.value]
        + change_counts[ValueChangeType.REMOVED_VALUE.value],
        "money_changes": counts[ValueType.MONEY.value],
        "percentage_changes": counts[ValueType.PERCENTAGE.value],
        "date_changes": counts[ValueType.DATE.value],
        "duration_changes": counts[ValueType.DURATION.value],
        "quantity_changes": counts[ValueType.QUANTITY.value],
        "entity_changes": counts[ValueType.ORGANIZATION.value]
        + counts[ValueType.LOCATION.value],
        "needs_review_count": review,
        "exact_diff_latency_ms": duration_ms,
        "exact_diff_llm_calls": 0,
    }
