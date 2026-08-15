# =============================================================================
# File: test_comparison_citation_verification.py
# Module/Service: Comparison Citation Verification (FR8 / TASK-CMP-11)
# Layer: Service
# Purpose: Unit, security, Unicode, determinism, V1/V2 verification tests.
# Responsibilities:
#   - VALID/INVALID/INSUFFICIENT; absence ≠ missing; no fabricated conclusions
# Dependencies:
#   - pytest, verify_finding, verify_bindings, CMP-01..10 pipeline
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: tests/fixtures/contracts/Hop_dong_mau_Ra_soat_Phap_ly_V*.txt
# Important Notes: Never assert "V1 does not contain" from missing evidence.
# =============================================================================

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from app.ai.document_structure.diff_types import DiffClassification
from app.ai.document_structure.evidence_engine import bind_finding, change_id_for
from app.ai.document_structure.evidence_types import (
    BindingStatus,
    EvidenceBindingResult,
    EvidenceCompleteness,
    EvidenceContext,
    EvidenceRef,
    EvidenceSide,
    EvidenceSourceType,
)
from app.ai.document_structure.exact_types import (
    ExactChange,
    ExtractedValue,
    ParseStatus,
    ValueChangeType,
    ValueDirection,
    ValueType,
)
from app.ai.document_structure.mapping_types import ClauseRef
from app.ai.document_structure.normalization import normalize_structure
from app.ai.document_structure.pipeline import extract_from_pages
from app.ai.document_structure.scoring_types import (
    RiskImpact,
    RiskLevel,
    RiskPerspective,
    RiskScoreResult,
    RiskStatus,
    ScoringConfidence,
)
from app.ai.document_structure.taxonomy_types import (
    ClassificationConfidence,
    RiskCategory,
)
from app.ai.document_structure.verification_engine import (
    catalog_from_structures,
    inventory_from_structures,
    verify_bindings,
    verify_finding,
)
from app.ai.document_structure.verification_types import (
    INSUFFICIENT_OLD_ABSENCE_MESSAGE,
    AbsenceStatus,
    ClauseInventory,
    EvidenceCheckStatus,
    SourceSnapshot,
    VerificationReasonCode,
    VerificationStatus,
)
from app.services.document_structure.verification import ComparisonCitationVerifier

FIXTURES = Path(__file__).parent / "fixtures" / "contracts"
V1_TXT = FIXTURES / "Hop_dong_mau_Ra_soat_Phap_ly_V1.txt"
V2_TXT = FIXTURES / "Hop_dong_mau_Ra_soat_Phap_ly_V2.txt"

OLD_TEXT = "Liability shall not exceed 1,000,000 USD."
NEW_TEXT = "Liability shall not exceed 500,000 USD."
OLD_SPAN = (OLD_TEXT.find("1,000,000"), OLD_TEXT.find("1,000,000") + len("1,000,000"))
NEW_SPAN = (NEW_TEXT.find("500,000"), NEW_TEXT.find("500,000") + len("500,000"))


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


def _ref(
    *,
    document_id,
    version_id,
    key: str = "CLAUSE:8.2",
    page: int | None = 4,
    chunks: tuple = (),
) -> ClauseRef:
    return ClauseRef(
        document_id=document_id,
        version_id=version_id,
        source_id=key,
        identity_key=key,
        unit_type="CLAUSE",
        canonical_number=key.split(":")[-1],
        page_start=page,
        page_end=page,
        chunk_ids=chunks,
    )


def _value(raw: str, number: Decimal) -> ExtractedValue:
    return ExtractedValue(
        value_type=ValueType.MONEY,
        raw_text=raw,
        start=0,
        end=len(raw),
        number=number,
        currency="USD",
        unit="USD",
    )


def _change(
    source: ClauseRef | None,
    target: ClauseRef | None,
    *,
    old_raw: str = "1,000,000",
    new_raw: str = "500,000",
    source_offset: tuple[int, int] | None = OLD_SPAN,
    target_offset: tuple[int, int] | None = NEW_SPAN,
    source_span: ParseStatus = ParseStatus.PARSED,
    target_span: ParseStatus = ParseStatus.PARSED,
) -> ExactChange:
    return ExactChange(
        change_type=ValueChangeType.REPLACED_VALUE,
        value_type=ValueType.MONEY,
        direction=ValueDirection.DECREASE,
        old_value=_value(old_raw, Decimal("1000000")) if source else None,
        new_value=_value(new_raw, Decimal("500000")) if target else None,
        source_ref=source,
        target_ref=target,
        delta=Decimal("-500000"),
        relative_change_percent=Decimal("-50"),
        source_span_status=source_span,
        target_span_status=target_span,
        source_offset=source_offset if source else None,
        target_offset=target_offset if target else None,
    )


def _score_row(
    *,
    classification: DiffClassification,
    source: ClauseRef | None,
    target: ClauseRef | None,
    key: str = "CLAUSE:8.2",
) -> RiskScoreResult:
    return RiskScoreResult(
        risk_score=70.0,
        risk_level=RiskLevel.HIGH,
        risk_impact=RiskImpact.RISK_INCREASING,
        base_score=40.0,
        score_breakdown=(),
        scoring_confidence=ScoringConfidence.HIGH,
        scoring_version="v1",
        status=RiskStatus.SCORED,
        category=RiskCategory.LIABILITY,
        classification_confidence=ClassificationConfidence.HIGH,
        perspective=RiskPerspective.UNKNOWN,
        identity_key=key,
        diff_classification=classification,
        source_ref=source,
        target_ref=target,
    )


def _snapshot(
    *,
    document_id,
    version_id,
    key: str = "CLAUSE:8.2",
    text: str = OLD_TEXT,
    page: int = 4,
    chunks: tuple = (),
    workspace_id=None,
) -> SourceSnapshot:
    return SourceSnapshot(
        document_id=document_id,
        document_version_id=version_id,
        workspace_id=workspace_id,
        identity_key=key,
        clause_id=key,
        chunk_ids=chunks,
        page_number=page,
        original_text=text,
    )


def _modified_pair():
    d1, d2, v1, v2 = uuid4(), uuid4(), uuid4(), uuid4()
    c1, c2 = uuid4(), uuid4()
    old = _ref(document_id=d1, version_id=v1, chunks=(c1,))
    new = _ref(document_id=d2, version_id=v2, chunks=(c2,))
    change = _change(old, new)
    ctx = EvidenceContext(
        source_document_id=d1,
        target_document_id=d2,
        source_version_id=v1,
        target_version_id=v2,
    )
    finding = bind_finding(
        _score_row(classification=DiffClassification.MODIFIED, source=old, target=new),
        [change],
        context=ctx,
    )
    catalog = [
        _snapshot(document_id=d1, version_id=v1, text=OLD_TEXT, chunks=(c1,)),
        _snapshot(document_id=d2, version_id=v2, text=NEW_TEXT, chunks=(c2,)),
    ]
    return finding, ctx, catalog, change


def test_valid_modified_is_verified() -> None:
    finding, ctx, catalog, change = _modified_pair()
    result = verify_finding(
        finding, context=ctx, catalog=catalog, changes={change_id_for(change): change}
    )
    assert result.status is VerificationStatus.VERIFIED
    assert result.absence_status is AbsenceStatus.NOT_APPLICABLE
    assert {row.side for row in result.evidence_results} == {
        EvidenceSide.OLD,
        EvidenceSide.NEW,
    }
    assert all(row.status is EvidenceCheckStatus.VALID for row in result.evidence_results)


def test_old_version_mismatch_is_invalid() -> None:
    finding, ctx, catalog, _change_row = _modified_pair()
    wrong = finding.evidence[0]
    tampered = EvidenceRef(
        evidence_id=wrong.evidence_id,
        side=EvidenceSide.OLD,
        document_id=wrong.document_id,
        document_version_id=ctx.target_version_id,
        clause_id=wrong.clause_id,
        identity_key=wrong.identity_key,
        chunk_id=wrong.chunk_id,
        page_number=wrong.page_number,
        start_offset=wrong.start_offset,
        end_offset=wrong.end_offset,
        source_type=wrong.source_type,
        display_text=wrong.display_text,
        source_change_id=wrong.source_change_id,
    )
    finding.evidence[0] = tampered
    result = verify_finding(finding, context=ctx, catalog=catalog)
    assert result.status is VerificationStatus.INVALID
    assert VerificationReasonCode.VERSION_MISMATCH in result.reasons


def test_new_version_mismatch_is_invalid() -> None:
    finding, ctx, catalog, _change_row = _modified_pair()
    wrong = finding.evidence[1]
    finding.evidence[1] = EvidenceRef(
        evidence_id=wrong.evidence_id,
        side=EvidenceSide.NEW,
        document_id=wrong.document_id,
        document_version_id=ctx.source_version_id,
        clause_id=wrong.clause_id,
        identity_key=wrong.identity_key,
        chunk_id=wrong.chunk_id,
        page_number=wrong.page_number,
        start_offset=wrong.start_offset,
        end_offset=wrong.end_offset,
        source_type=wrong.source_type,
        display_text=wrong.display_text,
        source_change_id=wrong.source_change_id,
    )
    result = verify_finding(finding, context=ctx, catalog=catalog)
    assert result.status is VerificationStatus.INVALID
    assert VerificationReasonCode.VERSION_MISMATCH in result.reasons


def test_modified_missing_old_is_partial() -> None:
    finding, ctx, catalog, _change_row = _modified_pair()
    finding.evidence[:] = [item for item in finding.evidence if item.side is EvidenceSide.NEW]
    result = verify_finding(finding, context=ctx, catalog=catalog)
    assert result.status is VerificationStatus.PARTIALLY_VERIFIED
    assert VerificationReasonCode.OLD_EVIDENCE_MISSING in result.reasons
    assert result.status is not VerificationStatus.VERIFIED


def test_modified_missing_new_is_partial() -> None:
    finding, ctx, catalog, _change_row = _modified_pair()
    finding.evidence[:] = [item for item in finding.evidence if item.side is EvidenceSide.OLD]
    result = verify_finding(finding, context=ctx, catalog=catalog)
    assert result.status is VerificationStatus.PARTIALLY_VERIFIED
    assert VerificationReasonCode.NEW_EVIDENCE_MISSING in result.reasons


def test_added_without_absence_proof_is_insufficient() -> None:
    d2, v2 = uuid4(), uuid4()
    new = _ref(document_id=d2, version_id=v2, key="CLAUSE:8.3")
    ctx = EvidenceContext(target_document_id=d2, target_version_id=v2)
    finding = bind_finding(
        _score_row(
            classification=DiffClassification.ADDED,
            source=None,
            target=new,
            key="CLAUSE:8.3",
        ),
        [_change(None, new, source_offset=None, source_span=ParseStatus.UNAVAILABLE)],
        context=ctx,
    )
    catalog = [_snapshot(document_id=d2, version_id=v2, key="CLAUSE:8.3", text=NEW_TEXT)]
    result = verify_finding(finding, context=ctx, catalog=catalog)
    assert result.status is VerificationStatus.INSUFFICIENT_EVIDENCE
    assert result.absence_status is AbsenceStatus.INSUFFICIENT_EVIDENCE
    assert result.human_message == INSUFFICIENT_OLD_ABSENCE_MESSAGE
    blob = str(result.as_dict()).casefold()
    assert "v1 không có" not in blob
    assert "does not contain" not in blob
    assert "không tồn tại trong v1." in result.human_message.casefold()


def test_added_with_inventory_absence_is_verified() -> None:
    d2, v2 = uuid4(), uuid4()
    new = _ref(document_id=d2, version_id=v2, key="CLAUSE:8.3")
    ctx = EvidenceContext(target_document_id=d2, target_version_id=v2)
    finding = bind_finding(
        _score_row(
            classification=DiffClassification.ADDED,
            source=None,
            target=new,
            key="CLAUSE:8.3",
        ),
        [_change(None, new, source_offset=None, source_span=ParseStatus.UNAVAILABLE)],
        context=ctx,
    )
    catalog = [_snapshot(document_id=d2, version_id=v2, key="CLAUSE:8.3", text=NEW_TEXT)]
    inventory = ClauseInventory(
        source_identity_keys=frozenset({"CLAUSE:8.2"}),
        target_identity_keys=frozenset({"CLAUSE:8.2", "CLAUSE:8.3"}),
    )
    result = verify_finding(finding, context=ctx, catalog=catalog, inventory=inventory)
    assert result.status is VerificationStatus.VERIFIED
    assert result.absence_status is AbsenceStatus.ABSENCE_CONFIRMED


def test_added_when_v1_inventory_has_key_is_not_absence() -> None:
    d2, v2 = uuid4(), uuid4()
    new = _ref(document_id=d2, version_id=v2, key="CLAUSE:1.2")
    ctx = EvidenceContext(target_document_id=d2, target_version_id=v2)
    finding = bind_finding(
        _score_row(
            classification=DiffClassification.ADDED,
            source=None,
            target=new,
            key="CLAUSE:1.2",
        ),
        [_change(None, new, source_offset=None, source_span=ParseStatus.UNAVAILABLE)],
        context=ctx,
    )
    catalog = [_snapshot(document_id=d2, version_id=v2, key="CLAUSE:1.2", text=NEW_TEXT)]
    inventory = ClauseInventory(
        source_identity_keys=frozenset({"CLAUSE:1.2", "CLAUSE:1.3"}),
        target_identity_keys=frozenset({"CLAUSE:1.2", "CLAUSE:1.3"}),
    )
    result = verify_finding(finding, context=ctx, catalog=catalog, inventory=inventory)
    assert result.status is VerificationStatus.INSUFFICIENT_EVIDENCE
    assert result.absence_status is AbsenceStatus.INSUFFICIENT_EVIDENCE
    assert "does not contain" not in str(result.as_dict()).casefold()


def test_removed_without_new_absence_proof() -> None:
    d1, v1 = uuid4(), uuid4()
    old = _ref(document_id=d1, version_id=v1, key="CLAUSE:9.2")
    ctx = EvidenceContext(source_document_id=d1, source_version_id=v1)
    finding = bind_finding(
        _score_row(
            classification=DiffClassification.REMOVED,
            source=old,
            target=None,
            key="CLAUSE:9.2",
        ),
        [_change(old, None, target_offset=None, target_span=ParseStatus.UNAVAILABLE)],
        context=ctx,
    )
    catalog = [_snapshot(document_id=d1, version_id=v1, key="CLAUSE:9.2", text=OLD_TEXT)]
    result = verify_finding(finding, context=ctx, catalog=catalog)
    assert result.status is VerificationStatus.INSUFFICIENT_EVIDENCE
    assert "no longer contains" not in str(result.as_dict()).casefold()


def test_invalid_span_start_after_end() -> None:
    finding, ctx, catalog, _change_row = _modified_pair()
    item = finding.evidence[0]
    finding.evidence[0] = EvidenceRef(
        evidence_id=item.evidence_id,
        side=item.side,
        document_id=item.document_id,
        document_version_id=item.document_version_id,
        clause_id=item.clause_id,
        identity_key=item.identity_key,
        chunk_id=item.chunk_id,
        page_number=item.page_number,
        start_offset=40,
        end_offset=10,
        source_type=EvidenceSourceType.TEXT_SPAN,
        display_text=item.display_text,
        source_change_id=item.source_change_id,
    )
    result = verify_finding(finding, context=ctx, catalog=catalog)
    assert result.status is VerificationStatus.INVALID
    assert VerificationReasonCode.SPAN_INVALID in result.reasons


def test_span_out_of_range() -> None:
    finding, ctx, catalog, _change_row = _modified_pair()
    item = finding.evidence[0]
    finding.evidence[0] = EvidenceRef(
        evidence_id=item.evidence_id,
        side=item.side,
        document_id=item.document_id,
        document_version_id=item.document_version_id,
        clause_id=item.clause_id,
        identity_key=item.identity_key,
        chunk_id=item.chunk_id,
        page_number=item.page_number,
        start_offset=0,
        end_offset=10_000,
        source_type=EvidenceSourceType.TEXT_SPAN,
        display_text=item.display_text,
        source_change_id=item.source_change_id,
    )
    result = verify_finding(finding, context=ctx, catalog=catalog)
    assert result.status is VerificationStatus.INVALID
    assert VerificationReasonCode.SPAN_OUT_OF_RANGE in result.reasons


def test_chunk_clause_mismatch_is_invalid() -> None:
    finding, ctx, catalog, _change_row = _modified_pair()
    foreign = uuid4()
    catalog[0] = _snapshot(
        document_id=catalog[0].document_id,
        version_id=catalog[0].document_version_id,
        text=OLD_TEXT,
        chunks=(foreign,),
    )
    result = verify_finding(finding, context=ctx, catalog=catalog)
    assert result.status is VerificationStatus.INVALID
    assert VerificationReasonCode.CHUNK_MISMATCH in result.reasons


def test_document_version_belongs_to_other_document() -> None:
    finding, ctx, catalog, _change_row = _modified_pair()
    item = finding.evidence[0]
    finding.evidence[0] = EvidenceRef(
        evidence_id=item.evidence_id,
        side=item.side,
        document_id=ctx.target_document_id,
        document_version_id=item.document_version_id,
        clause_id=item.clause_id,
        identity_key=item.identity_key,
        chunk_id=item.chunk_id,
        page_number=item.page_number,
        start_offset=item.start_offset,
        end_offset=item.end_offset,
        source_type=item.source_type,
        display_text=item.display_text,
        source_change_id=item.source_change_id,
    )
    result = verify_finding(finding, context=ctx, catalog=catalog)
    assert result.status is VerificationStatus.INVALID
    assert VerificationReasonCode.DOCUMENT_MISMATCH in result.reasons


def test_workspace_mismatch_is_invalid() -> None:
    finding, ctx, catalog, _change_row = _modified_pair()
    ws_a, ws_b = uuid4(), uuid4()
    ctx = EvidenceContext(
        workspace_id=ws_a,
        source_document_id=ctx.source_document_id,
        target_document_id=ctx.target_document_id,
        source_version_id=ctx.source_version_id,
        target_version_id=ctx.target_version_id,
    )
    catalog = [
        _snapshot(
            document_id=catalog[0].document_id,
            version_id=catalog[0].document_version_id,
            text=OLD_TEXT,
            chunks=catalog[0].chunk_ids,
            workspace_id=ws_b,
        ),
        catalog[1],
    ]
    result = verify_finding(finding, context=ctx, catalog=catalog)
    assert result.status is VerificationStatus.INVALID
    assert VerificationReasonCode.WORKSPACE_MISMATCH in result.reasons
    assert "workspace" not in (result.human_message or "")


def test_page_mismatch_is_invalid() -> None:
    finding, ctx, catalog, _change_row = _modified_pair()
    item = finding.evidence[0]
    finding.evidence[0] = EvidenceRef(
        evidence_id=item.evidence_id,
        side=item.side,
        document_id=item.document_id,
        document_version_id=item.document_version_id,
        clause_id=item.clause_id,
        identity_key=item.identity_key,
        chunk_id=item.chunk_id,
        page_number=8,
        start_offset=item.start_offset,
        end_offset=item.end_offset,
        source_type=item.source_type,
        display_text=item.display_text,
        source_change_id=item.source_change_id,
    )
    result = verify_finding(finding, context=ctx, catalog=catalog)
    assert result.status is VerificationStatus.INVALID
    assert VerificationReasonCode.PAGE_MISMATCH in result.reasons


def test_source_text_mismatch_is_invalid() -> None:
    finding, ctx, catalog, _change_row = _modified_pair()
    item = finding.evidence[0]
    finding.evidence[0] = EvidenceRef(
        evidence_id=item.evidence_id,
        side=item.side,
        document_id=item.document_id,
        document_version_id=item.document_version_id,
        clause_id=item.clause_id,
        identity_key=item.identity_key,
        chunk_id=item.chunk_id,
        page_number=item.page_number,
        start_offset=item.start_offset,
        end_offset=item.end_offset,
        source_type=item.source_type,
        display_text="USD 2,000,000",
        source_change_id=item.source_change_id,
    )
    result = verify_finding(finding, context=ctx, catalog=catalog)
    assert result.status is VerificationStatus.INVALID
    assert VerificationReasonCode.SOURCE_TEXT_MISMATCH in result.reasons


def test_wrong_numeric_source_is_not_verified() -> None:
    finding, ctx, catalog, change = _modified_pair()
    catalog[0] = _snapshot(
        document_id=catalog[0].document_id,
        version_id=catalog[0].document_version_id,
        text="Liability shall not exceed 2,000,000 USD.",
        chunks=catalog[0].chunk_ids,
    )
    result = verify_finding(
        finding, context=ctx, catalog=catalog, changes={change_id_for(change): change}
    )
    assert result.status is not VerificationStatus.VERIFIED
    assert VerificationReasonCode.VALUE_NOT_IN_SOURCE in result.reasons or (
        VerificationReasonCode.SOURCE_TEXT_MISMATCH in result.reasons
    )


def test_unicode_vietnamese_span() -> None:
    text = "Giới hạn trách nhiệm không vượt quá 500.000.000 VNĐ"
    start = text.find("500.000.000")
    end = start + len("500.000.000")
    d1, v1 = uuid4(), uuid4()
    old = _ref(document_id=d1, version_id=v1, key="CLAUSE:8.2")
    ctx = EvidenceContext(source_document_id=d1, source_version_id=v1)
    change = _change(
        old,
        None,
        old_raw="500.000.000",
        source_offset=(start, end),
        target_offset=None,
        target_span=ParseStatus.UNAVAILABLE,
    )
    finding = bind_finding(
        _score_row(classification=DiffClassification.REMOVED, source=old, target=None),
        [change],
        context=ctx,
    )
    catalog = [_snapshot(document_id=d1, version_id=v1, text=text)]
    inventory = ClauseInventory(
        source_identity_keys=frozenset({"CLAUSE:8.2"}),
        target_identity_keys=frozenset(),
    )
    result = verify_finding(
        finding,
        context=ctx,
        catalog=catalog,
        inventory=inventory,
        changes={change_id_for(change): change},
    )
    assert result.status is VerificationStatus.VERIFIED
    assert result.evidence_results[0].checks.span_valid is True
    assert finding.evidence[0].display_text == "500.000.000"


def test_determinism() -> None:
    finding, ctx, catalog, change = _modified_pair()
    changes = {change_id_for(change): change}
    first = verify_finding(finding, context=ctx, catalog=catalog, changes=changes)
    second = verify_finding(finding, context=ctx, catalog=catalog, changes=changes)
    assert first.as_dict() == second.as_dict()


def test_idempotent_batch_no_duplicate_records() -> None:
    finding, ctx, catalog, change = _modified_pair()
    bindings = EvidenceBindingResult(
        source_document_id=ctx.source_document_id,
        target_document_id=ctx.target_document_id,
        source_version_id=ctx.source_version_id,
        target_version_id=ctx.target_version_id,
        bindings=[finding, finding],
    )
    result = verify_bindings(
        bindings,
        context=ctx,
        catalog=catalog,
        exact=None,
    )
    assert len(result.findings) == 2
    assert result.findings[0].verified_evidence_ids == result.findings[1].verified_evidence_ids


def test_binding_invalid_stays_invalid() -> None:
    finding, ctx, catalog, _change_row = _modified_pair()
    finding.status = BindingStatus.INVALID
    finding.completeness = EvidenceCompleteness.MISSING
    result = verify_finding(finding, context=ctx, catalog=catalog)
    assert result.status is VerificationStatus.INVALID
    assert VerificationReasonCode.BINDING_INVALID in result.reasons


def test_no_legal_or_recommendation_language() -> None:
    finding, ctx, catalog, _change_row = _modified_pair()
    result = verify_finding(finding, context=ctx, catalog=catalog)
    blob = str(result.as_dict()).casefold()
    assert "recommend" not in blob
    assert "unlawful" not in blob
    assert "unfair" not in blob
    assert "citation verified" not in blob


def test_v1_v2_regression_verifies_identity_not_page_guess() -> None:
    v1 = normalize_structure(extract_from_pages(_pages(V1_TXT), title="V1"))
    v2 = normalize_structure(extract_from_pages(_pages(V2_TXT), title="V2"))
    result = ComparisonCitationVerifier().verify_structures(v1, v2)
    assert result.metadata["citation_llm_calls"] == 0
    assert result.metadata["citation_retrieval_calls"] == 0
    assert result.for_source("CLAUSE:1.2") is None
    assert result.for_source("CLAUSE:1.3") is None
    for key in ("CLAUSE:2.1", "CLAUSE:3.1", "CLAUSE:8.2", "CLAUSE:9.1", "CLAUSE:11.2"):
        row = result.for_source(key)
        assert row is not None
        assert row.status in {
            VerificationStatus.VERIFIED,
            VerificationStatus.PARTIALLY_VERIFIED,
        }
        assert row.absence_status is AbsenceStatus.NOT_APPLICABLE
        sides = {item.side for item in row.evidence_results}
        assert EvidenceSide.OLD in sides
        assert EvidenceSide.NEW in sides
    added = result.for_source("CLAUSE:8.3")
    if added:
        assert added.status in {
            VerificationStatus.VERIFIED,
            VerificationStatus.INSUFFICIENT_EVIDENCE,
            VerificationStatus.PARTIALLY_VERIFIED,
        }
        if added.absence_status is AbsenceStatus.INSUFFICIENT_EVIDENCE:
            assert added.human_message == INSUFFICIENT_OLD_ABSENCE_MESSAGE
        assert "v1 không có" not in str(added.as_dict()).casefold()
    inventory = inventory_from_structures(v1, v2)
    assert "CLAUSE:1.2" in inventory.source_identity_keys
    assert "CLAUSE:1.3" in inventory.source_identity_keys
    assert "CLAUSE:1.2" in inventory.target_identity_keys
    catalog = catalog_from_structures(v1, v2)
    assert catalog
    blob = str(result.as_dict()).casefold()
    assert "does not contain" not in blob
    assert "recommend" not in blob
