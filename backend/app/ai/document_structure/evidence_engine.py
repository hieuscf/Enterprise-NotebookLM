# =============================================================================
# File: evidence_engine.py
# Module/Service: Clause Evidence Binding (FR8 / TASK-CMP-10)
# Layer: Service
# Purpose: Bind CMP-06/07/08 findings to V1/V2 clause/chunk/page/span refs.
# Responsibilities:
#   - Highest available precision: TEXT_SPAN > CHUNK > CLAUSE > PAGE
#   - Validate workspace / document / version; never invent ids or offsets
#   - Deterministic ids, order, and reuse of identical EvidenceRef
# Dependencies:
#   - evidence_types; exact_types; scoring_types; taxonomy_types; mapping_types
# Public Exports:
#   - bind_evidence, bind_finding, change_id_for, finding_id_for
# Database/Table: N/A
# Related Modules: ClauseEvidenceBinder; CMP-11 consumes FindingEvidence
# Important Notes:
#   - 0 LLM. 0 retrieval. Offsets are character offsets from CMP-06.
#   - CMP-09 is optional (rule_id from taxonomy when present).
# =============================================================================

from __future__ import annotations

import hashlib
import time
from collections.abc import Sequence
from typing import Any
from uuid import UUID, uuid5, NAMESPACE_URL

from app.ai.document_structure.diff_types import DiffClassification
from app.ai.document_structure.exact_types import (
    ExactChange,
    ExactDiffResult,
    ParseStatus,
)
from app.ai.document_structure.mapping_types import ClauseRef
from app.ai.document_structure.scoring_types import (
    RiskScoreResult,
    RiskScoringResult,
    RiskStatus,
)
from app.ai.document_structure.taxonomy_types import RiskCategory, TaxonomyResult
from app.ai.document_structure.evidence_types import (
    BINDING_VERSION,
    BindingStatus,
    EvidenceBindingResult,
    EvidenceCompleteness,
    EvidenceContext,
    EvidenceRef,
    EvidenceRole,
    EvidenceSide,
    EvidenceSourceType,
    FindingEvidence,
    SourceRecord,
)

_SKIP = frozenset({RiskStatus.NOT_APPLICABLE})
_NS = uuid5(NAMESPACE_URL, "enterprise-notebooklm/cmp-10")


def finding_id_for(
    identity_key: str | None,
    category: RiskCategory | None,
    classification: DiffClassification | None,
) -> str:
    payload = "|".join(
        [
            identity_key or "",
            category.value if category else "",
            classification.value if classification else "",
        ]
    )
    return str(uuid5(_NS, f"finding:{payload}"))


def change_id_for(change: ExactChange) -> str:
    old_raw = change.old_value.raw_text if change.old_value else ""
    new_raw = change.new_value.raw_text if change.new_value else ""
    key = "|".join(
        [
            change.source_ref.identity_key if change.source_ref else "",
            change.target_ref.identity_key if change.target_ref else "",
            change.value_type.value,
            change.change_type.value,
            old_raw,
            new_raw,
            str(change.source_offset or ""),
            str(change.target_offset or ""),
        ]
    )
    return str(uuid5(_NS, f"change:{key}"))


def evidence_id_for(ref: EvidenceRef) -> str:
    payload = "|".join(
        [
            ref.side.value,
            str(ref.document_id or ""),
            str(ref.document_version_id or ""),
            ref.identity_key or ref.clause_id or "",
            str(ref.chunk_id or ""),
            str(ref.start_offset if ref.start_offset is not None else ""),
            str(ref.end_offset if ref.end_offset is not None else ""),
            ref.source_type.value,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def bind_evidence(
    scores: RiskScoringResult,
    exact: ExactDiffResult | None = None,
    taxonomy: TaxonomyResult | None = None,
    *,
    context: EvidenceContext | None = None,
    sources: Sequence[SourceRecord] | None = None,
) -> EvidenceBindingResult:
    """Bind every scored finding. Does not re-score, re-classify, or retrieve."""
    started = time.perf_counter()
    ctx = context or EvidenceContext(
        source_document_id=scores.source_document_id,
        target_document_id=scores.target_document_id,
        source_version_id=scores.source_version_id,
        target_version_id=scores.target_version_id,
    )
    source_map = {item.chunk_id: item for item in sources or ()}
    changes = _index_changes(exact)
    rules = _index_rules(taxonomy)
    reused: dict[str, EvidenceRef] = {}
    rows: list[FindingEvidence] = []
    for score in scores.scores:
        if score.status in _SKIP:
            continue
        if score.diff_classification is DiffClassification.UNCHANGED:
            continue
        rows.append(
            bind_finding(
                score,
                changes.get(score.identity_key or "", []),
                rule_id=rules.get(score.identity_key or ""),
                context=ctx,
                source_map=source_map,
                reused=reused,
            )
        )
    duration_ms = int((time.perf_counter() - started) * 1000)
    return EvidenceBindingResult(
        source_document_id=scores.source_document_id,
        target_document_id=scores.target_document_id,
        source_version_id=scores.source_version_id,
        target_version_id=scores.target_version_id,
        bindings=rows,
        binding_version=BINDING_VERSION,
        metadata=_metadata(rows, reused=len(reused), duration_ms=duration_ms),
    )


def bind_finding(
    score: RiskScoreResult,
    changes: Sequence[ExactChange],
    *,
    rule_id: str | None = None,
    context: EvidenceContext | None = None,
    source_map: dict[UUID, SourceRecord] | None = None,
    reused: dict[str, EvidenceRef] | None = None,
) -> FindingEvidence:
    """Pure bind of one finding. Invalid sources are rejected, not rewritten."""
    ctx = context or EvidenceContext()
    pool = reused if reused is not None else {}
    catalog = source_map or {}
    required = _required_sides(score.diff_classification)
    items: list[EvidenceRef] = []
    statuses: list[BindingStatus] = []
    change_ids: list[str] = []
    if changes:
        for change in changes:
            cid = change_id_for(change)
            change_ids.append(cid)
            old, old_status = _bind_side(
                EvidenceSide.OLD,
                ref=change.source_ref or score.source_ref,
                offset=change.source_offset,
                span_status=change.source_span_status,
                display=change.old_value.raw_text if change.old_value else None,
                change_id=cid,
                context=ctx,
                source_map=catalog,
                expected_document=ctx.source_document_id,
                expected_version=ctx.source_version_id,
            )
            new, new_status = _bind_side(
                EvidenceSide.NEW,
                ref=change.target_ref or score.target_ref,
                offset=change.target_offset,
                span_status=change.target_span_status,
                display=change.new_value.raw_text if change.new_value else None,
                change_id=cid,
                context=ctx,
                source_map=catalog,
                expected_document=ctx.target_document_id,
                expected_version=ctx.target_version_id,
            )
            if EvidenceSide.OLD in required:
                statuses.append(old_status)
                if old:
                    _append_unique(items, _reuse(old, pool))
            if EvidenceSide.NEW in required:
                statuses.append(new_status)
                if new:
                    _append_unique(items, _reuse(new, pool))
    else:
        if EvidenceSide.OLD in required:
            old, old_status = _bind_side(
                EvidenceSide.OLD,
                ref=score.source_ref,
                offset=None,
                span_status=ParseStatus.UNAVAILABLE,
                display=None,
                change_id=None,
                context=ctx,
                source_map=catalog,
                expected_document=ctx.source_document_id,
                expected_version=ctx.source_version_id,
            )
            statuses.append(old_status)
            if old:
                _append_unique(items, _reuse(old, pool))
        if EvidenceSide.NEW in required:
            new, new_status = _bind_side(
                EvidenceSide.NEW,
                ref=score.target_ref,
                offset=None,
                span_status=ParseStatus.UNAVAILABLE,
                display=None,
                change_id=None,
                context=ctx,
                source_map=catalog,
                expected_document=ctx.target_document_id,
                expected_version=ctx.target_version_id,
            )
            statuses.append(new_status)
            if new:
                _append_unique(items, _reuse(new, pool))

    items = _sort(items)
    status, completeness = _aggregate(required, items, statuses)
    return FindingEvidence(
        finding_id=finding_id_for(
            score.identity_key, score.category, score.diff_classification
        ),
        identity_key=score.identity_key,
        category=score.category,
        rule_id=rule_id,
        diff_classification=score.diff_classification,
        source_change_ids=tuple(dict.fromkeys(change_ids)),
        evidence=items,
        status=status,
        completeness=completeness,
    )


def _bind_side(
    side: EvidenceSide,
    *,
    ref: ClauseRef | None,
    offset: tuple[int, int] | None,
    span_status: ParseStatus,
    display: str | None,
    change_id: str | None,
    context: EvidenceContext,
    source_map: dict[UUID, SourceRecord],
    expected_document: UUID | None,
    expected_version: UUID | None,
) -> tuple[EvidenceRef | None, BindingStatus]:
    if ref is None:
        return None, BindingStatus.UNAVAILABLE
    if expected_document and ref.document_id != expected_document:
        return None, BindingStatus.INVALID
    if expected_version and ref.version_id and ref.version_id != expected_version:
        return None, BindingStatus.INVALID

    chunk_id, page, chunk_status = _resolve_chunk(
        ref, source_map, context, expected_document, expected_version
    )
    if chunk_status is BindingStatus.INVALID:
        return None, BindingStatus.INVALID

    start = end = None
    source_type = EvidenceSourceType.CLAUSE
    if (
        offset is not None
        and span_status is ParseStatus.PARSED
        and offset[0] >= 0
        and offset[1] > offset[0]
    ):
        start, end = offset
        source_type = EvidenceSourceType.TEXT_SPAN
    elif chunk_id is not None:
        source_type = EvidenceSourceType.CHUNK
    elif page is not None:
        source_type = EvidenceSourceType.PAGE

    if (
        ref.identity_key is None
        and ref.source_id is None
        and chunk_id is None
        and page is None
    ):
        return None, BindingStatus.UNAVAILABLE

    draft = EvidenceRef(
        evidence_id="",
        side=side,
        document_id=ref.document_id,
        document_version_id=ref.version_id or expected_version,
        clause_id=ref.source_id,
        identity_key=ref.identity_key,
        chunk_id=chunk_id,
        page_number=page,
        start_offset=start,
        end_offset=end,
        source_type=source_type,
        role=EvidenceRole.PRIMARY,
        display_text=display,
        source_change_id=change_id,
    )
    return EvidenceRef(
        evidence_id=evidence_id_for(draft),
        side=draft.side,
        document_id=draft.document_id,
        document_version_id=draft.document_version_id,
        clause_id=draft.clause_id,
        identity_key=draft.identity_key,
        chunk_id=draft.chunk_id,
        page_number=draft.page_number,
        start_offset=draft.start_offset,
        end_offset=draft.end_offset,
        source_type=draft.source_type,
        role=draft.role,
        display_text=draft.display_text,
        source_change_id=draft.source_change_id,
    ), BindingStatus.BOUND


def _resolve_chunk(
    ref: ClauseRef,
    source_map: dict[UUID, SourceRecord],
    context: EvidenceContext,
    expected_document: UUID | None,
    expected_version: UUID | None,
) -> tuple[UUID | None, int | None, BindingStatus]:
    page = ref.page_start
    if not ref.chunk_ids:
        return None, page, BindingStatus.BOUND
    for chunk_id in ref.chunk_ids:
        record = source_map.get(chunk_id)
        if record is None:
            return chunk_id, page, BindingStatus.BOUND
        if context.workspace_id and record.workspace_id:
            if record.workspace_id != context.workspace_id:
                return None, None, BindingStatus.INVALID
        if expected_document and record.document_id != expected_document:
            return None, None, BindingStatus.INVALID
        if expected_version and record.document_version_id != expected_version:
            return None, None, BindingStatus.INVALID
        if record.page_number is not None and page is None:
            page = record.page_number
        return chunk_id, page, BindingStatus.BOUND
    return None, page, BindingStatus.BOUND


def _required_sides(classification: DiffClassification | None) -> frozenset[EvidenceSide]:
    if classification is DiffClassification.ADDED:
        return frozenset({EvidenceSide.NEW})
    if classification is DiffClassification.REMOVED:
        return frozenset({EvidenceSide.OLD})
    return frozenset({EvidenceSide.OLD, EvidenceSide.NEW})


def _aggregate(
    required: frozenset[EvidenceSide],
    items: list[EvidenceRef],
    statuses: list[BindingStatus],
) -> tuple[BindingStatus, EvidenceCompleteness]:
    if BindingStatus.INVALID in statuses:
        return BindingStatus.INVALID, EvidenceCompleteness.MISSING
    present = {item.side for item in items}
    missing_required = bool(required - present)
    if not items:
        return BindingStatus.UNAVAILABLE, EvidenceCompleteness.MISSING
    if BindingStatus.UNAVAILABLE in statuses or missing_required:
        return BindingStatus.PARTIAL, EvidenceCompleteness.PARTIAL
    precise = all(item.source_type is EvidenceSourceType.TEXT_SPAN for item in items)
    if precise:
        return BindingStatus.BOUND, EvidenceCompleteness.COMPLETE
    return BindingStatus.PARTIAL, EvidenceCompleteness.PARTIAL


def _append_unique(items: list[EvidenceRef], item: EvidenceRef) -> None:
    if any(existing.evidence_id == item.evidence_id for existing in items):
        return
    items.append(item)


def _reuse(item: EvidenceRef, pool: dict[str, EvidenceRef]) -> EvidenceRef:
    existing = pool.get(item.evidence_id)
    if existing is not None:
        return existing
    pool[item.evidence_id] = item
    return item


def _sort(items: list[EvidenceRef]) -> list[EvidenceRef]:
    order = {EvidenceSide.OLD: 0, EvidenceSide.NEW: 1}
    return sorted(
        items,
        key=lambda item: (
            order[item.side],
            item.page_number if item.page_number is not None else 10**9,
            str(item.chunk_id or ""),
            item.start_offset if item.start_offset is not None else 10**9,
            item.evidence_id,
        ),
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


def _index_rules(taxonomy: TaxonomyResult | None) -> dict[str, str]:
    mapping: dict[str, str] = {}
    if taxonomy is None:
        return mapping
    for row in taxonomy.assignments:
        if row.identity_key and row.rule_id:
            mapping[row.identity_key] = row.rule_id
    return mapping


def _metadata(
    rows: list[FindingEvidence],
    *,
    reused: int,
    duration_ms: int,
) -> dict[str, Any]:
    counts = {item.value: 0 for item in BindingStatus}
    for row in rows:
        counts[row.status.value] += 1
    return {
        "binding_version": BINDING_VERSION,
        "findings_bound": len(rows),
        "evidence_refs": sum(len(row.evidence) for row in rows),
        "unique_evidence_ids": reused,
        "status_counts": counts,
        "binding_latency_ms": duration_ms,
        "evidence_llm_calls": 0,
        "evidence_retrieval_calls": 0,
    }
