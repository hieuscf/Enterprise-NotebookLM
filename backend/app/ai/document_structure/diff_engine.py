# =============================================================================
# File: diff_engine.py
# Module/Service: Clause Diff Engine (FR8 / TASK-CMP-04)
# Layer: Service
# Purpose: Classify every mapped/unmatched clause as UNCHANGED/MODIFIED/ADDED/
#   REMOVED (or AMBIGUOUS/UNKNOWN) from the FULL CMP-03 mapping result.
# Responsibilities:
#   - Consume MappingResult — never top-k RAG / user query / LLM
#   - Content equality on CMP-02 folded/normalized body; metadata flags separate
#   - Preserve AMBIGUOUS and LOW_CONFIDENCE as NEEDS_REVIEW
#   - Token/sentence change lists for TASK-CMP-06
# Dependencies:
#   - mapping_types, mapping_engine, diff_types, diff_config, diff_text
# Public Exports:
#   - diff_mapping_result, diff_normalized_structures, classify_pair
# Database/Table: N/A
# Related Modules: ClauseDiffEngine; ComparisonService remains unchanged
# Important Notes:
#   - Numbering/title/parent/position change alone is NOT MODIFIED.
#   - Unmatched after mapping = ADDED/REMOVED. Unretrieved ≠ missing.
#   - Does not mutate original_title / original_text.
# =============================================================================

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from app.ai.document_structure.diff_config import DiffConfig
from app.ai.document_structure.diff_text import (
    content_fingerprint,
    content_texts,
    select_comparison_text,
    sentence_changes,
    token_changes,
)
from app.ai.document_structure.diff_types import (
    ClauseDiff,
    DiffClassification,
    DiffResult,
    DiffSignals,
    DiffVerificationStatus,
    TextChange,
)
from app.ai.document_structure.mapping_engine import map_normalized_structures
from app.ai.document_structure.mapping_types import (
    ClauseMapping,
    MappingResult,
    MappingSignals,
    MappingStatus,
    MappingType,
    clause_ref,
)
from app.ai.document_structure.normalization import (
    NormalizedDocumentStructure,
    NormalizedUnit,
)

_REVIEW_STATUSES = frozenset({MappingStatus.AMBIGUOUS, MappingStatus.LOW_CONFIDENCE})
_SUBTREE_DIRTY = frozenset(
    {
        DiffClassification.MODIFIED,
        DiffClassification.ADDED,
        DiffClassification.REMOVED,
    }
)


def diff_normalized_structures(
    source: NormalizedDocumentStructure,
    target: NormalizedDocumentStructure,
    *,
    mapping: MappingResult | None = None,
    config: DiffConfig | None = None,
) -> DiffResult:
    """Map (if needed) then diff the complete clause sets."""
    mapping_result = mapping or map_normalized_structures(source, target)
    return diff_mapping_result(mapping_result, config=config)


def diff_mapping_result(
    mapping: MappingResult,
    *,
    config: DiffConfig | None = None,
) -> DiffResult:
    """Classify every CMP-03 row. Does not query retrieval or call an LLM."""
    started = time.perf_counter()
    cfg = config or DiffConfig()
    reserved_targets = _reserved_target_keys(mapping)
    rows: list[ClauseDiff] = []
    errors: list[str] = []
    seen_targets: set[str] = set()
    seen_sources: set[str] = set()

    for item in mapping.mappings:
        if item.accepted:
            target_key = _unit_key(item.target_unit)
            source_key = _unit_key(item.source_unit)
            if source_key and source_key in seen_sources:
                errors.append("duplicate_source_mapping")
            if target_key and target_key in seen_targets:
                errors.append("duplicate_target_mapping")
        row, error = _classify_mapping(item, config=cfg)
        if error:
            errors.append(error)
        _remember(seen_sources, seen_targets, row)
        rows.append(row)

    for item in mapping.unmatched_targets:
        target_key = _unit_key(item.target_unit)
        if target_key and target_key in reserved_targets:
            continue
        if target_key and target_key in seen_targets:
            errors.append("duplicate_unmatched_target")
            continue
        row, error = _classify_mapping(item, config=cfg)
        if error:
            errors.append(error)
        _remember(seen_sources, seen_targets, row)
        rows.append(row)

    rows.sort(key=_sort_key)
    _apply_subtree_classification(rows)
    duration_ms = int((time.perf_counter() - started) * 1000)
    metadata = _metadata(rows, duration_ms=duration_ms, errors=errors)
    return DiffResult(
        source_document_id=mapping.source_document_id,
        target_document_id=mapping.target_document_id,
        source_version_id=mapping.source_version_id,
        target_version_id=mapping.target_version_id,
        diffs=rows,
        mapping_metadata=dict(mapping.metadata),
        metadata=metadata,
    )


def classify_pair(
    source: NormalizedUnit,
    target: NormalizedUnit,
    *,
    mapping_status: MappingStatus = MappingStatus.EXACT,
    config: DiffConfig | None = None,
) -> ClauseDiff:
    """Compare one accepted pair. Used by tests and by the engine."""
    mapping = ClauseMapping(
        source_unit=source,
        target_unit=target,
        mapping_type=MappingType.EXACT,
        confidence=1.0,
        confidence_level=mapping_status,
        signals=MappingSignals(
            number_match=source.identity_key == target.identity_key,
            type_match=source.type is target.type,
            parent_match=source.parent_identity_key == target.parent_identity_key,
            title_similarity=1.0,
            lexical_similarity=1.0,
            method="classify_pair",
        ),
        source_ref=clause_ref(source, version_id=None),
        target_ref=clause_ref(target, version_id=None),
    )
    return _diff_accepted(mapping, config=config or DiffConfig())


def _classify_mapping(
    item: ClauseMapping,
    *,
    config: DiffConfig,
) -> tuple[ClauseDiff, str | None]:
    status = item.confidence_level
    if status is MappingStatus.AMBIGUOUS:
        return _review_row(item, DiffClassification.AMBIGUOUS_MAPPING), None
    if status is MappingStatus.LOW_CONFIDENCE:
        return _review_row(item, DiffClassification.UNKNOWN, preview=True, config=config), None
    if item.accepted:
        if item.source_unit is None or item.target_unit is None:
            return (
                _review_row(item, DiffClassification.UNKNOWN),
                "accepted_mapping_missing_unit",
            )
        return _diff_accepted(item, config=config), None
    if item.source_unit is not None and item.target_unit is None:
        return _one_sided(item, DiffClassification.REMOVED), None
    if item.source_unit is None and item.target_unit is not None:
        return _one_sided(item, DiffClassification.ADDED), None
    return _review_row(item, DiffClassification.UNKNOWN), "invalid_mapping"


def _diff_accepted(item: ClauseMapping, *, config: DiffConfig) -> ClauseDiff:
    source = item.source_unit
    target = item.target_unit
    assert source is not None and target is not None
    content_changed, field, source_text, target_text = content_texts(source, target)
    source_hash = content_fingerprint(source_text) if config.use_content_hash else None
    target_hash = content_fingerprint(target_text) if config.use_content_hash else None
    hash_match = (
        source_hash == target_hash
        if source_hash is not None and target_hash is not None
        else None
    )
    if hash_match is True:
        content_changed = False
    signals = DiffSignals(
        content_changed=content_changed,
        number_changed=_number_changed(source, target),
        title_changed=_title_changed(source, target),
        parent_changed=source.parent_identity_key != target.parent_identity_key,
        position_changed=source.order_index != target.order_index,
        content_hash_match=hash_match,
        comparison_field=field,
    )
    changes: list[TextChange] = []
    sent_changes: list[TextChange] = []
    if content_changed and config.compute_token_diff:
        changes = token_changes(source_text, target_text, config=config)
    if content_changed and config.compute_sentence_diff:
        sent_changes = sentence_changes(source_text, target_text, config=config)
    classification = (
        DiffClassification.MODIFIED
        if content_changed
        else DiffClassification.UNCHANGED
    )
    return ClauseDiff(
        classification=classification,
        verification_status=DiffVerificationStatus.VERIFIED,
        mapping_status=item.confidence_level,
        mapping_type=item.mapping_type,
        mapping_confidence=item.confidence,
        source_unit=source,
        target_unit=target,
        source_ref=item.source_ref,
        target_ref=item.target_ref,
        signals=signals,
        changes=changes,
        sentence_changes=sent_changes,
        candidates=list(item.candidates),
        content_hash_source=source_hash,
        content_hash_target=target_hash,
    )


def _one_sided(item: ClauseMapping, classification: DiffClassification) -> ClauseDiff:
    unit = item.source_unit or item.target_unit
    text, field = select_comparison_text(unit)
    digest = content_fingerprint(text) if text else None
    return ClauseDiff(
        classification=classification,
        verification_status=DiffVerificationStatus.VERIFIED,
        mapping_status=item.confidence_level,
        mapping_type=item.mapping_type,
        mapping_confidence=item.confidence,
        source_unit=item.source_unit,
        target_unit=item.target_unit,
        source_ref=item.source_ref,
        target_ref=item.target_ref,
        signals=DiffSignals(
            content_changed=True,
            number_changed=False,
            title_changed=False,
            parent_changed=False,
            position_changed=False,
            comparison_field=field,
        ),
        candidates=list(item.candidates),
        content_hash_source=digest if item.source_unit is not None else None,
        content_hash_target=digest if item.target_unit is not None else None,
    )


def _review_row(
    item: ClauseMapping,
    classification: DiffClassification,
    *,
    preview: bool = False,
    config: DiffConfig | None = None,
) -> ClauseDiff:
    signals = DiffSignals(
        content_changed=False,
        number_changed=False,
        title_changed=False,
        parent_changed=False,
        position_changed=False,
    )
    changes: list[TextChange] = []
    sent_changes: list[TextChange] = []
    source_hash = None
    target_hash = None
    if (
        preview
        and item.source_unit is not None
        and item.target_unit is not None
        and config is not None
    ):
        preview_row = _diff_accepted(item, config=config)
        signals = preview_row.signals
        changes = preview_row.changes
        sent_changes = preview_row.sentence_changes
        source_hash = preview_row.content_hash_source
        target_hash = preview_row.content_hash_target
    return ClauseDiff(
        classification=classification,
        verification_status=DiffVerificationStatus.NEEDS_REVIEW,
        mapping_status=item.confidence_level,
        mapping_type=item.mapping_type,
        mapping_confidence=item.confidence,
        source_unit=item.source_unit,
        target_unit=item.target_unit,
        source_ref=item.source_ref,
        target_ref=item.target_ref,
        signals=signals,
        changes=changes,
        sentence_changes=sent_changes,
        candidates=list(item.candidates),
        content_hash_source=source_hash,
        content_hash_target=target_hash,
    )


def _reserved_target_keys(mapping: MappingResult) -> set[str]:
    """Targets that sit on AMBIGUOUS/LOW_CONFIDENCE rows must not become ADDED."""
    reserved: set[str] = set()
    for item in mapping.mappings:
        if item.confidence_level not in _REVIEW_STATUSES:
            continue
        key = _unit_key(item.target_unit)
        if key:
            reserved.add(key)
        for candidate in item.candidates:
            if candidate.target_identity_key:
                reserved.add(f"id:{candidate.target_identity_key}")
            reserved.add(f"src:{candidate.target_source_id}")
    return reserved


def _unit_key(unit: NormalizedUnit | None) -> str | None:
    if unit is None:
        return None
    if unit.identity_key:
        return f"id:{unit.identity_key}"
    return f"src:{unit.source_id}"


def _remember(
    seen_sources: set[str],
    seen_targets: set[str],
    row: ClauseDiff,
) -> None:
    source_key = _unit_key(row.source_unit)
    target_key = _unit_key(row.target_unit)
    if source_key:
        seen_sources.add(source_key)
    if target_key:
        seen_targets.add(target_key)


def _number_changed(source: NormalizedUnit, target: NormalizedUnit) -> bool:
    if source.identity_key and target.identity_key:
        return source.identity_key != target.identity_key
    return source.canonical_number != target.canonical_number


def _title_changed(source: NormalizedUnit, target: NormalizedUnit) -> bool:
    left = (source.folded_title or source.normalized_title or "").strip()
    right = (target.folded_title or target.normalized_title or "").strip()
    if left or right:
        return left != right
    return (source.original_title or "").strip() != (target.original_title or "").strip()


def _apply_subtree_classification(rows: list[ClauseDiff]) -> None:
    """Article rollup: descendant ADDED/REMOVED/MODIFIED → parent MODIFIED."""
    by_key: dict[str, ClauseDiff] = {}
    children: dict[str, list[ClauseDiff]] = defaultdict(list)
    for row in rows:
        unit = row.source_unit or row.target_unit
        if unit is None:
            continue
        if unit.identity_key:
            by_key[unit.identity_key] = row
        if unit.parent_identity_key:
            children[unit.parent_identity_key].append(row)

    def walk(identity_key: str) -> DiffClassification | None:
        row = by_key.get(identity_key)
        if row is None:
            return None
        dirty = row.classification in _SUBTREE_DIRTY
        review = row.classification in {
            DiffClassification.AMBIGUOUS_MAPPING,
            DiffClassification.UNKNOWN,
        }
        for child in children.get(identity_key, ()):
            child_unit = child.source_unit or child.target_unit
            child_key = child_unit.identity_key if child_unit else None
            child_class = walk(child_key) if child_key else child.classification
            if child_class in _SUBTREE_DIRTY:
                dirty = True
            if child_class in {
                DiffClassification.AMBIGUOUS_MAPPING,
                DiffClassification.UNKNOWN,
            }:
                review = True
        if dirty:
            row.subtree_classification = DiffClassification.MODIFIED
        elif review:
            row.subtree_classification = DiffClassification.AMBIGUOUS_MAPPING
        else:
            row.subtree_classification = row.classification
        return row.subtree_classification

    for key in list(by_key):
        walk(key)


def _sort_key(row: ClauseDiff) -> tuple[str, str, str]:
    source_key = row.source_unit.identity_key if row.source_unit else ""
    target_key = row.target_unit.identity_key if row.target_unit else ""
    return (source_key or "", target_key or "", row.classification.value)


def _metadata(
    rows: list[ClauseDiff],
    *,
    duration_ms: int,
    errors: list[str],
) -> dict[str, Any]:
    counts: dict[str, int] = {item.value: 0 for item in DiffClassification}
    verified = 0
    review = 0
    change_spans = 0
    for row in rows:
        counts[row.classification.value] += 1
        if row.verification_status is DiffVerificationStatus.VERIFIED:
            verified += 1
        else:
            review += 1
        change_spans += len(row.changes)
    total = len(rows)
    unchanged = counts[DiffClassification.UNCHANGED.value]
    return {
        "total_diffs": total,
        "unchanged_count": unchanged,
        "modified_count": counts[DiffClassification.MODIFIED.value],
        "added_count": counts[DiffClassification.ADDED.value],
        "removed_count": counts[DiffClassification.REMOVED.value],
        "ambiguous_count": counts[DiffClassification.AMBIGUOUS_MAPPING.value],
        "unknown_count": counts[DiffClassification.UNKNOWN.value],
        "verified_count": verified,
        "needs_review_count": review,
        "exact_unchanged_rate": (
            round(unchanged / total, 4) if total else 0.0
        ),
        "average_diff_size": (
            round(change_spans / max(1, counts[DiffClassification.MODIFIED.value]), 4)
            if counts[DiffClassification.MODIFIED.value]
            else 0.0
        ),
        "diff_latency_ms": duration_ms,
        "diff_llm_calls": 0,
        "error_count": len(errors),
        "errors": errors[:20],
    }
