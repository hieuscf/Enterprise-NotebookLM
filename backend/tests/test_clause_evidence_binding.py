# =============================================================================
# File: test_clause_evidence_binding.py
# Module/Service: Clause Evidence Binding (FR8 / TASK-CMP-10)
# Layer: Service
# Purpose: Unit, security, Unicode, determinism, V1/V2 evidence-binding tests.
# Responsibilities:
#   - OLD/NEW sides; ADDED/REMOVED/MODIFIED; no fabricated offsets/pages
# Dependencies:
#   - pytest, bind_finding, bind_evidence, CMP-01..08 pipeline
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: tests/fixtures/contracts/Hop_dong_mau_Ra_soat_Phap_ly_V*.txt
# Important Notes: Binding only — never assert citation verified.
# =============================================================================

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from app.ai.document_structure.diff_engine import diff_normalized_structures
from app.ai.document_structure.diff_types import DiffClassification
from app.ai.document_structure.evidence_engine import bind_evidence, bind_finding, finding_id_for
from app.ai.document_structure.evidence_types import (
    BindingStatus,
    EvidenceCompleteness,
    EvidenceContext,
    EvidenceSide,
    EvidenceSourceType,
    SourceRecord,
)
from app.ai.document_structure.exact_engine import extract_exact_differences
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
from app.ai.document_structure.scoring_engine import score_taxonomy
from app.ai.document_structure.scoring_types import (
    RiskImpact,
    RiskLevel,
    RiskPerspective,
    RiskScoreResult,
    RiskScoringResult,
    RiskStatus,
    ScoringConfidence,
)
from app.ai.document_structure.taxonomy_engine import classify_taxonomy
from app.ai.document_structure.taxonomy_types import (
    ClassificationConfidence,
    RiskCategory,
)
from app.services.document_structure.evidence import ClauseEvidenceBinder

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
    source_offset: tuple[int, int] | None = (10, 19),
    target_offset: tuple[int, int] | None = (10, 17),
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
    category: RiskCategory = RiskCategory.LIABILITY,
    status: RiskStatus = RiskStatus.SCORED,
) -> RiskScoreResult:
    return RiskScoreResult(
        risk_score=70.0,
        risk_level=RiskLevel.HIGH,
        risk_impact=RiskImpact.RISK_INCREASING,
        base_score=40.0,
        score_breakdown=(),
        scoring_confidence=ScoringConfidence.HIGH,
        scoring_version="v1",
        status=status,
        category=category,
        classification_confidence=ClassificationConfidence.HIGH,
        perspective=RiskPerspective.UNKNOWN,
        identity_key=key,
        diff_classification=classification,
        source_ref=source,
        target_ref=target,
    )


def _batch(*rows: RiskScoreResult, source_id=None, target_id=None) -> RiskScoringResult:
    return RiskScoringResult(
        source_document_id=source_id or uuid4(),
        target_document_id=target_id or uuid4(),
        source_version_id=None,
        target_version_id=None,
        scores=list(rows),
    )


# ---------------------------------------------------------------------------
# Sides / change types
# ---------------------------------------------------------------------------


def test_modified_binds_old_and_new_spans() -> None:
    v1, v2 = uuid4(), uuid4()
    d1, d2 = uuid4(), uuid4()
    old = _ref(document_id=d1, version_id=v1, chunks=(uuid4(),))
    new = _ref(document_id=d2, version_id=v2, chunks=(uuid4(),))
    finding = bind_finding(
        _score_row(classification=DiffClassification.MODIFIED, source=old, target=new),
        [_change(old, new)],
        context=EvidenceContext(
            source_document_id=d1,
            target_document_id=d2,
            source_version_id=v1,
            target_version_id=v2,
        ),
    )
    sides = {item.side for item in finding.evidence}
    assert sides == {EvidenceSide.OLD, EvidenceSide.NEW}
    assert all(item.source_type is EvidenceSourceType.TEXT_SPAN for item in finding.evidence)
    assert finding.status is BindingStatus.BOUND
    assert finding.completeness is EvidenceCompleteness.COMPLETE
    assert finding.evidence[0].start_offset == 10
    assert finding.evidence[0].document_version_id == v1
    assert finding.evidence[1].document_version_id == v2


def test_added_binds_new_only() -> None:
    d2, v2 = uuid4(), uuid4()
    new = _ref(document_id=d2, version_id=v2, key="CLAUSE:8.3")
    finding = bind_finding(
        _score_row(
            classification=DiffClassification.ADDED,
            source=None,
            target=new,
            key="CLAUSE:8.3",
        ),
        [_change(None, new, source_offset=None, source_span=ParseStatus.UNAVAILABLE)],
        context=EvidenceContext(target_document_id=d2, target_version_id=v2),
    )
    assert [item.side for item in finding.evidence] == [EvidenceSide.NEW]
    assert finding.status in {BindingStatus.BOUND, BindingStatus.PARTIAL}


def test_removed_binds_old_only() -> None:
    d1, v1 = uuid4(), uuid4()
    old = _ref(document_id=d1, version_id=v1, key="CLAUSE:9.2")
    finding = bind_finding(
        _score_row(
            classification=DiffClassification.REMOVED,
            source=old,
            target=None,
            key="CLAUSE:9.2",
        ),
        [_change(old, None, target_offset=None, target_span=ParseStatus.UNAVAILABLE)],
        context=EvidenceContext(source_document_id=d1, source_version_id=v1),
    )
    assert [item.side for item in finding.evidence] == [EvidenceSide.OLD]


def test_unchanged_is_skipped() -> None:
    d1, v1 = uuid4(), uuid4()
    ref = _ref(document_id=d1, version_id=v1)
    result = bind_evidence(
        _batch(
            _score_row(
                classification=DiffClassification.UNCHANGED,
                source=ref,
                target=ref,
                status=RiskStatus.NOT_APPLICABLE,
            )
        )
    )
    assert result.bindings == []


def test_span_fallback_to_chunk_then_clause() -> None:
    d1, v1 = uuid4(), uuid4()
    chunk = uuid4()
    old = _ref(document_id=d1, version_id=v1, chunks=(chunk,))
    finding = bind_finding(
        _score_row(classification=DiffClassification.REMOVED, source=old, target=None),
        [_change(old, None, source_offset=None, source_span=ParseStatus.UNAVAILABLE)],
        context=EvidenceContext(source_document_id=d1, source_version_id=v1),
    )
    assert finding.evidence[0].source_type is EvidenceSourceType.CHUNK
    assert finding.evidence[0].chunk_id == chunk
    assert finding.evidence[0].start_offset is None

    bare = _ref(document_id=d1, version_id=v1, page=None, chunks=())
    clause_only = bind_finding(
        _score_row(classification=DiffClassification.REMOVED, source=bare, target=None),
        [_change(bare, None, source_offset=None, source_span=ParseStatus.UNAVAILABLE)],
        context=EvidenceContext(source_document_id=d1, source_version_id=v1),
    )
    assert clause_only.evidence[0].source_type is EvidenceSourceType.CLAUSE
    assert clause_only.evidence[0].chunk_id is None


def test_does_not_fabricate_page_from_clause_number() -> None:
    d1, v1 = uuid4(), uuid4()
    old = _ref(document_id=d1, version_id=v1, key="CLAUSE:8.2", page=None, chunks=())
    finding = bind_finding(
        _score_row(classification=DiffClassification.REMOVED, source=old, target=None),
        [_change(old, None, source_offset=None, source_span=ParseStatus.UNAVAILABLE)],
        context=EvidenceContext(source_document_id=d1, source_version_id=v1),
    )
    assert finding.evidence[0].page_number is None


# ---------------------------------------------------------------------------
# Validation / security
# ---------------------------------------------------------------------------


def test_wrong_version_is_invalid() -> None:
    d1, v1, v2 = uuid4(), uuid4(), uuid4()
    old = _ref(document_id=d1, version_id=v2)
    finding = bind_finding(
        _score_row(classification=DiffClassification.REMOVED, source=old, target=None),
        [_change(old, None)],
        context=EvidenceContext(source_document_id=d1, source_version_id=v1),
    )
    assert finding.status is BindingStatus.INVALID
    assert finding.evidence == []


def test_cross_tenant_chunk_is_rejected() -> None:
    d1, v1, ws_a, ws_b, chunk = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    old = _ref(document_id=d1, version_id=v1, chunks=(chunk,))
    finding = bind_finding(
        _score_row(classification=DiffClassification.REMOVED, source=old, target=None),
        [_change(old, None, source_offset=None, source_span=ParseStatus.UNAVAILABLE)],
        context=EvidenceContext(
            workspace_id=ws_a,
            source_document_id=d1,
            source_version_id=v1,
        ),
        source_map={
            chunk: SourceRecord(
                chunk_id=chunk,
                document_id=d1,
                document_version_id=v1,
                workspace_id=ws_b,
            )
        },
    )
    assert finding.status is BindingStatus.INVALID


def test_missing_source_is_unavailable() -> None:
    finding = bind_finding(
        _score_row(classification=DiffClassification.REMOVED, source=None, target=None),
        [],
    )
    assert finding.status is BindingStatus.UNAVAILABLE
    assert finding.completeness is EvidenceCompleteness.MISSING


def test_unicode_display_text_preserved() -> None:
    d1, v1 = uuid4(), uuid4()
    raw = "Giới hạn trách nhiệm không vượt quá 500.000.000 VNĐ"
    old = _ref(document_id=d1, version_id=v1)
    finding = bind_finding(
        _score_row(classification=DiffClassification.REMOVED, source=old, target=None),
        [_change(old, None, old_raw=raw, source_offset=(0, len(raw)))],
        context=EvidenceContext(source_document_id=d1, source_version_id=v1),
    )
    assert finding.evidence[0].display_text == raw
    assert finding.evidence[0].end_offset == len(raw)


def test_determinism_and_reuse() -> None:
    d1, d2, v1, v2 = uuid4(), uuid4(), uuid4(), uuid4()
    old = _ref(document_id=d1, version_id=v1)
    new = _ref(document_id=d2, version_id=v2)
    score = _score_row(classification=DiffClassification.MODIFIED, source=old, target=new)
    change = _change(old, new)
    ctx = EvidenceContext(
        source_document_id=d1,
        target_document_id=d2,
        source_version_id=v1,
        target_version_id=v2,
    )
    first = bind_finding(score, [change], context=ctx)
    second = bind_finding(score, [change], context=ctx)
    assert first.finding_id == second.finding_id
    assert [item.evidence_id for item in first.evidence] == [
        item.evidence_id for item in second.evidence
    ]
    assert first.finding_id == finding_id_for(
        "CLAUSE:8.2", RiskCategory.LIABILITY, DiffClassification.MODIFIED
    )


def test_duplicate_span_is_reused_once() -> None:
    d1, v1 = uuid4(), uuid4()
    old = _ref(document_id=d1, version_id=v1)
    first = _change(old, None, old_raw="100%", source_offset=(23, 26))
    second = _change(old, None, old_raw="100%", source_offset=(23, 26))
    finding = bind_finding(
        _score_row(classification=DiffClassification.REMOVED, source=old, target=None),
        [first, second],
        context=EvidenceContext(source_document_id=d1, source_version_id=v1),
    )
    assert len(finding.evidence) == 1


def test_no_legal_or_citation_claims() -> None:
    d1, v1 = uuid4(), uuid4()
    old = _ref(document_id=d1, version_id=v1)
    finding = bind_finding(
        _score_row(classification=DiffClassification.REMOVED, source=old, target=None),
        [_change(old, None)],
        context=EvidenceContext(source_document_id=d1, source_version_id=v1),
    )
    blob = str(finding.as_dict()).casefold()
    assert "verified" not in blob
    assert "recommend" not in blob
    assert "unlawful" not in blob
    assert "unfavorable" not in blob


# ---------------------------------------------------------------------------
# Pipeline / regression
# ---------------------------------------------------------------------------


def test_v1_v2_regression_binds_identity_not_page_guess() -> None:
    v1 = normalize_structure(extract_from_pages(_pages(V1_TXT), title="V1"))
    v2 = normalize_structure(extract_from_pages(_pages(V2_TXT), title="V2"))
    result = ClauseEvidenceBinder().bind_structures(v1, v2)
    assert result.metadata["evidence_llm_calls"] == 0
    assert result.metadata["evidence_retrieval_calls"] == 0
    assert result.for_source("CLAUSE:1.2") is None
    for key in ("CLAUSE:2.1", "CLAUSE:3.1", "CLAUSE:8.2", "CLAUSE:9.1", "CLAUSE:11.2"):
        row = result.for_source(key)
        assert row is not None
        assert row.identity_key == key
        assert row.evidence
        sides = {item.side for item in row.evidence}
        assert EvidenceSide.OLD in sides
        assert EvidenceSide.NEW in sides
        for item in row.evidence:
            assert item.document_id is not None
            assert item.identity_key == key
    added = next((row for row in result.bindings if row.identity_key == "CLAUSE:8.3"), None)
    if added:
        assert {item.side for item in added.evidence} <= {EvidenceSide.NEW}
    blob = str(result.as_dict()).casefold()
    assert "citation verified" not in blob
