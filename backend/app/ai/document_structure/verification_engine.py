# =============================================================================
# File: verification_engine.py
# Module/Service: Comparison Citation Verification (FR8 / TASK-CMP-11)
# Layer: Service
# Purpose: Deterministically verify CMP-10 evidence refs against canonical source.
# Responsibilities:
#   - Validate workspace / document / version / clause / chunk / page / span
#   - Enforce OLD/NEW completeness by change type
#   - Distinguish missing evidence from confirmed absence
# Dependencies:
#   - verification_types; evidence_types; exact_types; citation source_validator
# Public Exports:
#   - verify_bindings, verify_finding, catalog_from_structures, inventory_from_structures
# Database/Table: N/A
# Related Modules: ComparisonCitationVerifier; does not write citations.verified
# Important Notes:
#   - 0 LLM. 0 retrieval. Never repairs invalid refs. Never infers absence.
# =============================================================================

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from app.ai.document_structure.diff_types import DiffClassification
from app.ai.document_structure.evidence_engine import change_id_for
from app.ai.document_structure.evidence_types import (
    BindingStatus,
    EvidenceBindingResult,
    EvidenceContext,
    EvidenceRef,
    EvidenceSide,
    EvidenceSourceType,
    FindingEvidence,
    SourceRecord,
)
from app.ai.document_structure.exact_types import ExactChange, ExactDiffResult
from app.ai.document_structure.normalization import NormalizedDocumentStructure
from app.ai.document_structure.verification_types import (
    INSUFFICIENT_NEW_ABSENCE_MESSAGE,
    INSUFFICIENT_OLD_ABSENCE_MESSAGE,
    VERIFICATION_VERSION,
    AbsenceStatus,
    ClauseInventory,
    ComparisonVerificationResult,
    EvidenceChecks,
    EvidenceCheckStatus,
    EvidenceVerification,
    FindingVerification,
    SourceSnapshot,
    VerificationReasonCode,
    VerificationStatus,
)
from app.services.citation_verification.source_validator import (
    page_matches,
    quote_in_source,
    slice_text,
    span_is_valid,
)

_Reason = VerificationReasonCode


def catalog_from_structures(
    source: NormalizedDocumentStructure,
    target: NormalizedDocumentStructure,
) -> list[SourceSnapshot]:
    """Batch-build canonical snapshots from CMP-01/02 trees. No DB access."""
    rows: list[SourceSnapshot] = []
    rows.extend(_snapshots(source))
    rows.extend(_snapshots(target))
    return rows


def inventory_from_structures(
    source: NormalizedDocumentStructure,
    target: NormalizedDocumentStructure,
) -> ClauseInventory:
    return ClauseInventory(
        source_identity_keys=frozenset(source.identity_keys()),
        target_identity_keys=frozenset(target.identity_keys()),
    )


def verify_bindings(
    bindings: EvidenceBindingResult,
    *,
    context: EvidenceContext | None = None,
    catalog: Sequence[SourceSnapshot] | None = None,
    chunks: Sequence[SourceRecord] | None = None,
    inventory: ClauseInventory | None = None,
    exact: ExactDiffResult | None = None,
) -> ComparisonVerificationResult:
    """Verify every bound finding. Does not re-bind, re-score, or retrieve."""
    started = time.perf_counter()
    ctx = context or EvidenceContext(
        source_document_id=bindings.source_document_id,
        target_document_id=bindings.target_document_id,
        source_version_id=bindings.source_version_id,
        target_version_id=bindings.target_version_id,
    )
    snapshots = list(catalog or ())
    chunk_map = {item.chunk_id: item for item in chunks or ()}
    changes = _index_changes(exact)
    reused: dict[str, EvidenceVerification] = {}
    rows: list[FindingVerification] = []
    for finding in bindings.bindings:
        rows.append(
            verify_finding(
                finding,
                context=ctx,
                catalog=snapshots,
                chunks=chunk_map,
                inventory=inventory,
                changes=changes,
                reused=reused,
            )
        )
    duration_ms = int((time.perf_counter() - started) * 1000)
    return ComparisonVerificationResult(
        source_document_id=bindings.source_document_id,
        target_document_id=bindings.target_document_id,
        source_version_id=bindings.source_version_id,
        target_version_id=bindings.target_version_id,
        findings=rows,
        verification_version=VERIFICATION_VERSION,
        metadata=_metadata(rows, reused=len(reused), duration_ms=duration_ms),
    )


def verify_finding(
    finding: FindingEvidence,
    *,
    context: EvidenceContext | None = None,
    catalog: Sequence[SourceSnapshot] | None = None,
    chunks: dict[UUID, SourceRecord] | Sequence[SourceRecord] | None = None,
    inventory: ClauseInventory | None = None,
    changes: dict[str, ExactChange] | None = None,
    reused: dict[str, EvidenceVerification] | None = None,
) -> FindingVerification:
    """Pure verification of one finding. Invalid refs are rejected, not rewritten."""
    ctx = context or EvidenceContext()
    pool = reused if reused is not None else {}
    chunk_map = chunks if isinstance(chunks, dict) else {item.chunk_id: item for item in chunks or ()}
    change_map = changes or {}
    snapshots = list(catalog or ())

    if finding.status is BindingStatus.INVALID:
        return _terminal(
            finding,
            VerificationStatus.INVALID,
            AbsenceStatus.NOT_APPLICABLE,
            (_Reason.BINDING_INVALID,),
        )
    if finding.status is BindingStatus.UNAVAILABLE and not finding.evidence:
        return _terminal(
            finding,
            VerificationStatus.UNVERIFIED,
            AbsenceStatus.NOT_APPLICABLE,
            (_Reason.BINDING_UNAVAILABLE, _Reason.EVIDENCE_NOT_FOUND),
        )

    results: list[EvidenceVerification] = []
    for item in finding.evidence:
        cached = pool.get(item.evidence_id)
        if cached is not None:
            results.append(cached)
            continue
        verified = _verify_ref(
            item,
            finding=finding,
            context=ctx,
            catalog=snapshots,
            chunks=chunk_map,
            changes=change_map,
        )
        pool[item.evidence_id] = verified
        results.append(verified)

    required = _required_sides(finding.diff_classification)
    present_valid = {
        row.side for row in results if row.status is EvidenceCheckStatus.VALID
    }
    missing = tuple(sorted(side.value for side in required - present_valid))
    absence, absence_reason = _absence(
        finding.diff_classification, finding.identity_key, inventory
    )
    status, reasons, message = _aggregate(
        finding=finding,
        required=required,
        results=results,
        missing=missing,
        absence=absence,
        absence_reason=absence_reason,
    )
    valid_ids = tuple(
        row.evidence_id for row in results if row.status is EvidenceCheckStatus.VALID
    )
    invalid_ids = tuple(
        row.evidence_id
        for row in results
        if row.status in {EvidenceCheckStatus.INVALID, EvidenceCheckStatus.MISMATCH}
    )
    return FindingVerification(
        finding_id=finding.finding_id,
        identity_key=finding.identity_key,
        status=status,
        absence_status=absence,
        evidence_results=results,
        verified_evidence_ids=valid_ids,
        invalid_evidence_ids=invalid_ids,
        missing_sides=missing,
        reasons=reasons,
        human_message=message,
        diff_classification=finding.diff_classification,
        rule_id=finding.rule_id,
    )


def _verify_ref(
    item: EvidenceRef,
    *,
    finding: FindingEvidence,
    context: EvidenceContext,
    catalog: Sequence[SourceSnapshot],
    chunks: dict[UUID, SourceRecord],
    changes: dict[str, ExactChange],
) -> EvidenceVerification:
    reasons: list[_Reason] = []
    expected_doc, expected_ver = _expected(item.side, context)
    snapshot = _lookup(item, catalog)
    chunk = chunks.get(item.chunk_id) if item.chunk_id else None

    workspace_ok = True
    if context.workspace_id is not None:
        snap_ws = snapshot.workspace_id if snapshot else None
        chunk_ws = chunk.workspace_id if chunk else None
        if snap_ws is not None and snap_ws != context.workspace_id:
            workspace_ok = False
            reasons.append(_Reason.WORKSPACE_MISMATCH)
        elif chunk_ws is not None and chunk_ws != context.workspace_id:
            workspace_ok = False
            reasons.append(_Reason.WORKSPACE_MISMATCH)

    document_ok = True
    if expected_doc is not None and item.document_id is not None:
        if item.document_id != expected_doc:
            document_ok = False
            reasons.append(_Reason.DOCUMENT_MISMATCH)
    if snapshot is not None and item.document_id is not None:
        if item.document_id != snapshot.document_id:
            document_ok = False
            if _Reason.DOCUMENT_MISMATCH not in reasons:
                reasons.append(_Reason.DOCUMENT_MISMATCH)
    if chunk is not None and item.document_id is not None:
        if chunk.document_id != item.document_id:
            document_ok = False
            if _Reason.DOCUMENT_MISMATCH not in reasons:
                reasons.append(_Reason.DOCUMENT_MISMATCH)

    version_ok = True
    if expected_ver is not None and item.document_version_id is not None:
        if item.document_version_id != expected_ver:
            version_ok = False
            reasons.append(_Reason.VERSION_MISMATCH)
    if snapshot is not None and item.document_version_id and snapshot.document_version_id:
        if item.document_version_id != snapshot.document_version_id:
            version_ok = False
            if _Reason.VERSION_MISMATCH not in reasons:
                reasons.append(_Reason.VERSION_MISMATCH)
    if chunk is not None and item.document_version_id is not None:
        if chunk.document_version_id != item.document_version_id:
            version_ok = False
            if _Reason.VERSION_MISMATCH not in reasons:
                reasons.append(_Reason.VERSION_MISMATCH)

    source_exists = snapshot is not None or chunk is not None or not catalog
    if catalog and snapshot is None and item.identity_key:
        source_exists = False
        reasons.append(_Reason.EVIDENCE_NOT_FOUND)
    elif catalog and snapshot is None and item.clause_id:
        source_exists = False
        reasons.append(_Reason.DOCUMENT_NOT_FOUND)

    clause_ok = True
    if snapshot is not None:
        if item.identity_key and snapshot.identity_key:
            if item.identity_key != snapshot.identity_key:
                clause_ok = False
                reasons.append(_Reason.CLAUSE_MISMATCH)
        if item.clause_id and snapshot.clause_id:
            if item.clause_id != snapshot.clause_id:
                clause_ok = False
                if _Reason.CLAUSE_MISMATCH not in reasons:
                    reasons.append(_Reason.CLAUSE_MISMATCH)
        if finding.identity_key and item.identity_key:
            if item.identity_key != finding.identity_key:
                clause_ok = False
                if _Reason.CLAUSE_MISMATCH not in reasons:
                    reasons.append(_Reason.CLAUSE_MISMATCH)

    chunk_ok = True
    if item.chunk_id is not None:
        if snapshot is not None and snapshot.chunk_ids:
            if item.chunk_id not in snapshot.chunk_ids:
                chunk_ok = False
                reasons.append(_Reason.CHUNK_MISMATCH)
        if chunk is not None and snapshot is not None and snapshot.document_version_id:
            if chunk.document_version_id != snapshot.document_version_id:
                chunk_ok = False
                if _Reason.CHUNK_MISMATCH not in reasons:
                    reasons.append(_Reason.CHUNK_MISMATCH)

    page_ok = True
    canonical_page = None
    if snapshot is not None:
        canonical_page = snapshot.page_number
    if chunk is not None and chunk.page_number is not None:
        canonical_page = chunk.page_number if canonical_page is None else canonical_page
        if snapshot is not None and snapshot.page_number is not None:
            if chunk.page_number != snapshot.page_number and item.page_number == chunk.page_number:
                canonical_page = chunk.page_number
    if not page_matches(item.page_number, canonical_page):
        page_ok = False
        reasons.append(_Reason.PAGE_MISMATCH)
    if (
        chunk is not None
        and item.page_number is not None
        and chunk.page_number is not None
        and item.page_number != chunk.page_number
    ):
        page_ok = False
        if _Reason.PAGE_MISMATCH not in reasons:
            reasons.append(_Reason.PAGE_MISMATCH)

    type_ok = True
    span_ok = True
    text_ok = True
    source_text = snapshot.original_text if snapshot is not None else None
    if item.source_type is EvidenceSourceType.TEXT_SPAN:
        if item.start_offset is None or item.end_offset is None:
            type_ok = False
            span_ok = False
            reasons.append(_Reason.SOURCE_TYPE_INCONSISTENT)
        else:
            length = len(source_text) if source_text is not None else None
            ok, code = span_is_valid(item.start_offset, item.end_offset, length)
            if not ok:
                span_ok = False
                reasons.append(
                    _Reason.SPAN_OUT_OF_RANGE if code == "SPAN_OUT_OF_RANGE" else _Reason.SPAN_INVALID
                )
            elif source_text is None and catalog:
                text_ok = False
                reasons.append(_Reason.SOURCE_TEXT_MISSING)
            elif source_text is not None:
                sliced = slice_text(source_text, item.start_offset, item.end_offset)
                if item.display_text and sliced is not None and sliced != item.display_text:
                    text_ok = False
                    reasons.append(_Reason.SOURCE_TEXT_MISMATCH)
                elif item.display_text and sliced is None:
                    text_ok = False
                    reasons.append(_Reason.SOURCE_TEXT_MISMATCH)
    elif item.source_type is EvidenceSourceType.CHUNK and item.chunk_id is None:
        type_ok = False
        reasons.append(_Reason.SOURCE_TYPE_INCONSISTENT)
    elif item.source_type is EvidenceSourceType.PAGE and item.page_number is None:
        type_ok = False
        reasons.append(_Reason.SOURCE_TYPE_INCONSISTENT)

    if (
        item.display_text
        and source_text is not None
        and item.source_type is not EvidenceSourceType.TEXT_SPAN
    ):
        if not quote_in_source(quote=item.display_text, source=source_text):
            text_ok = False
            reasons.append(_Reason.SOURCE_TEXT_MISMATCH)

    value_ok: bool | None = None
    change = changes.get(item.source_change_id) if item.source_change_id else None
    expected_raw = _expected_raw(item.side, change)
    if expected_raw:
        haystack = source_text
        if item.source_type is EvidenceSourceType.TEXT_SPAN and source_text is not None:
            sliced = slice_text(source_text, item.start_offset, item.end_offset)
            haystack = sliced if sliced is not None else source_text
        if haystack is None and not catalog:
            value_ok = None
        elif haystack is None:
            value_ok = False
            reasons.append(_Reason.VALUE_NOT_IN_SOURCE)
        elif not quote_in_source(quote=expected_raw, source=haystack):
            value_ok = False
            reasons.append(_Reason.VALUE_NOT_IN_SOURCE)
        else:
            value_ok = True

    checks = EvidenceChecks(
        source_exists=source_exists,
        version_matches=version_ok,
        document_matches=document_ok,
        clause_matches=clause_ok,
        chunk_matches=chunk_ok,
        page_matches=page_ok,
        span_valid=span_ok if item.source_type is EvidenceSourceType.TEXT_SPAN else True,
        source_text_matches=text_ok,
        workspace_matches=workspace_ok,
        source_type_consistent=type_ok,
        value_in_source=value_ok,
    )
    status = _evidence_status(checks, reasons, has_catalog=bool(catalog))
    if status is EvidenceCheckStatus.VALID and not reasons:
        reasons.append(_Reason.VALID)
    return EvidenceVerification(
        evidence_id=item.evidence_id,
        side=item.side,
        status=status,
        checks=checks,
        reasons=tuple(dict.fromkeys(reasons)),
    )


def _evidence_status(
    checks: EvidenceChecks,
    reasons: Sequence[_Reason],
    *,
    has_catalog: bool,
) -> EvidenceCheckStatus:
    hard = {
        _Reason.WORKSPACE_MISMATCH,
        _Reason.VERSION_MISMATCH,
        _Reason.DOCUMENT_MISMATCH,
        _Reason.CLAUSE_MISMATCH,
        _Reason.CHUNK_MISMATCH,
        _Reason.PAGE_MISMATCH,
        _Reason.SPAN_INVALID,
        _Reason.SPAN_OUT_OF_RANGE,
        _Reason.SOURCE_TEXT_MISMATCH,
        _Reason.SOURCE_TYPE_INCONSISTENT,
        _Reason.VALUE_NOT_IN_SOURCE,
    }
    if any(item in hard for item in reasons):
        return EvidenceCheckStatus.INVALID
    if _Reason.EVIDENCE_NOT_FOUND in reasons or _Reason.DOCUMENT_NOT_FOUND in reasons:
        return EvidenceCheckStatus.UNAVAILABLE
    if _Reason.SOURCE_TEXT_MISSING in reasons:
        return EvidenceCheckStatus.UNAVAILABLE
    if has_catalog and not checks.source_exists:
        return EvidenceCheckStatus.UNAVAILABLE
    if not (
        checks.version_matches
        and checks.document_matches
        and checks.clause_matches
        and checks.chunk_matches
        and checks.page_matches
        and checks.workspace_matches
        and checks.source_type_consistent
        and checks.source_text_matches
    ):
        return EvidenceCheckStatus.MISMATCH
    return EvidenceCheckStatus.VALID


def _aggregate(
    *,
    finding: FindingEvidence,
    required: frozenset[EvidenceSide],
    results: list[EvidenceVerification],
    missing: tuple[str, ...],
    absence: AbsenceStatus,
    absence_reason: _Reason | None,
) -> tuple[VerificationStatus, tuple[_Reason, ...], str | None]:
    reasons: list[_Reason] = []
    invalid = any(
        row.status in {EvidenceCheckStatus.INVALID, EvidenceCheckStatus.MISMATCH}
        for row in results
    )
    valid_sides = {
        row.side for row in results if row.status is EvidenceCheckStatus.VALID
    }
    if invalid:
        for row in results:
            reasons.extend(
                code for code in row.reasons if code is not _Reason.VALID
            )
        return VerificationStatus.INVALID, _unique(reasons), None

    if required <= valid_sides:
        if absence is AbsenceStatus.INSUFFICIENT_EVIDENCE:
            reasons.append(absence_reason or _Reason.INSUFFICIENT_ABSENCE_PROOF)
            message = _absence_message(finding.diff_classification)
            return VerificationStatus.INSUFFICIENT_EVIDENCE, _unique(reasons), message
        reasons.append(_Reason.VALID)
        return VerificationStatus.VERIFIED, _unique(reasons), None

    if valid_sides and required - valid_sides:
        for side in required - valid_sides:
            reasons.append(
                _Reason.OLD_EVIDENCE_MISSING
                if side is EvidenceSide.OLD
                else _Reason.NEW_EVIDENCE_MISSING
            )
        if absence is AbsenceStatus.INSUFFICIENT_EVIDENCE and absence_reason:
            reasons.append(absence_reason)
        message = None
        if finding.diff_classification is DiffClassification.ADDED:
            message = INSUFFICIENT_OLD_ABSENCE_MESSAGE
        elif finding.diff_classification is DiffClassification.REMOVED:
            message = INSUFFICIENT_NEW_ABSENCE_MESSAGE
        if finding.diff_classification is DiffClassification.MODIFIED:
            return VerificationStatus.PARTIALLY_VERIFIED, _unique(reasons), None
        return VerificationStatus.INSUFFICIENT_EVIDENCE, _unique(reasons), message

    for side in required:
        reasons.append(
            _Reason.OLD_EVIDENCE_MISSING
            if side is EvidenceSide.OLD
            else _Reason.NEW_EVIDENCE_MISSING
        )
    if absence_reason:
        reasons.append(absence_reason)
    return VerificationStatus.INSUFFICIENT_EVIDENCE, _unique(reasons), _absence_message(
        finding.diff_classification
    )


def _absence(
    classification: DiffClassification | None,
    identity_key: str | None,
    inventory: ClauseInventory | None,
) -> tuple[AbsenceStatus, _Reason | None]:
    if classification is DiffClassification.ADDED:
        if inventory is None or not identity_key:
            return AbsenceStatus.INSUFFICIENT_EVIDENCE, _Reason.INSUFFICIENT_ABSENCE_PROOF
        if identity_key in inventory.source_identity_keys:
            return AbsenceStatus.INSUFFICIENT_EVIDENCE, _Reason.INSUFFICIENT_ABSENCE_PROOF
        return AbsenceStatus.ABSENCE_CONFIRMED, None
    if classification is DiffClassification.REMOVED:
        if inventory is None or not identity_key:
            return AbsenceStatus.INSUFFICIENT_EVIDENCE, _Reason.INSUFFICIENT_ABSENCE_PROOF
        if identity_key in inventory.target_identity_keys:
            return AbsenceStatus.INSUFFICIENT_EVIDENCE, _Reason.INSUFFICIENT_ABSENCE_PROOF
        return AbsenceStatus.ABSENCE_CONFIRMED, None
    return AbsenceStatus.NOT_APPLICABLE, None


def _absence_message(classification: DiffClassification | None) -> str | None:
    if classification is DiffClassification.ADDED:
        return INSUFFICIENT_OLD_ABSENCE_MESSAGE
    if classification is DiffClassification.REMOVED:
        return INSUFFICIENT_NEW_ABSENCE_MESSAGE
    return None


def _required_sides(classification: DiffClassification | None) -> frozenset[EvidenceSide]:
    if classification is DiffClassification.ADDED:
        return frozenset({EvidenceSide.NEW})
    if classification is DiffClassification.REMOVED:
        return frozenset({EvidenceSide.OLD})
    if classification is DiffClassification.UNCHANGED:
        return frozenset()
    return frozenset({EvidenceSide.OLD, EvidenceSide.NEW})


def _expected(
    side: EvidenceSide, context: EvidenceContext
) -> tuple[UUID | None, UUID | None]:
    if side is EvidenceSide.OLD:
        return context.source_document_id, context.source_version_id
    return context.target_document_id, context.target_version_id


def _lookup(item: EvidenceRef, catalog: Sequence[SourceSnapshot]) -> SourceSnapshot | None:
    """Prefer identity/clause over shared page-level chunk ids."""

    def _same_doc(snapshot: SourceSnapshot) -> bool:
        if item.document_id and snapshot.document_id != item.document_id:
            return False
        if (
            item.document_version_id
            and snapshot.document_version_id
            and snapshot.document_version_id != item.document_version_id
        ):
            return False
        return True

    if item.identity_key:
        for snapshot in catalog:
            if snapshot.identity_key == item.identity_key and _same_doc(snapshot):
                return snapshot
    if item.clause_id:
        for snapshot in catalog:
            if snapshot.clause_id == item.clause_id and _same_doc(snapshot):
                return snapshot
    if item.chunk_id:
        for snapshot in catalog:
            if item.chunk_id in snapshot.chunk_ids and _same_doc(snapshot):
                return snapshot
    return None


def _expected_raw(side: EvidenceSide, change: ExactChange | None) -> str | None:
    if change is None:
        return None
    if side is EvidenceSide.OLD and change.old_value is not None:
        return change.old_value.raw_text
    if side is EvidenceSide.NEW and change.new_value is not None:
        return change.new_value.raw_text
    return None


def _index_changes(exact: ExactDiffResult | None) -> dict[str, ExactChange]:
    mapping: dict[str, ExactChange] = {}
    if exact is None:
        return mapping
    for change in exact.changes:
        mapping[change_id_for(change)] = change
    return mapping


def _snapshots(structure: NormalizedDocumentStructure) -> list[SourceSnapshot]:
    rows: list[SourceSnapshot] = []
    for unit in structure.walk():
        if not unit.identity_key and not unit.source_id:
            continue
        rows.append(
            SourceSnapshot(
                document_id=unit.document_id,
                document_version_id=structure.version_id,
                workspace_id=structure.workspace_id,
                identity_key=unit.identity_key,
                clause_id=unit.source_id,
                chunk_ids=tuple(unit.chunk_ids),
                page_number=unit.page_start,
                original_text=unit.original_text,
            )
        )
    return rows


def _terminal(
    finding: FindingEvidence,
    status: VerificationStatus,
    absence: AbsenceStatus,
    reasons: tuple[_Reason, ...],
) -> FindingVerification:
    return FindingVerification(
        finding_id=finding.finding_id,
        identity_key=finding.identity_key,
        status=status,
        absence_status=absence,
        evidence_results=[],
        verified_evidence_ids=(),
        invalid_evidence_ids=(),
        missing_sides=(),
        reasons=reasons,
        human_message=None,
        diff_classification=finding.diff_classification,
        rule_id=finding.rule_id,
    )


def _unique(reasons: Sequence[_Reason]) -> tuple[_Reason, ...]:
    return tuple(dict.fromkeys(reasons))


def _metadata(
    rows: list[FindingVerification],
    *,
    reused: int,
    duration_ms: int,
) -> dict[str, Any]:
    counts = {item.value: 0 for item in VerificationStatus}
    for row in rows:
        counts[row.status.value] += 1
    return {
        "verification_version": VERIFICATION_VERSION,
        "findings_verified": len(rows),
        "status_counts": counts,
        "reused_evidence": reused,
        "verification_latency_ms": duration_ms,
        "citation_llm_calls": 0,
        "citation_retrieval_calls": 0,
    }
