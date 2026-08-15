# =============================================================================
# File: test_clause_diff.py
# Module/Service: Clause Diff Engine (FR8 / TASK-CMP-04)
# Layer: Service
# Purpose: Unit, integration, V1/V2 regression, false-positive/negative tests.
# Responsibilities:
#   - UNCHANGED / MODIFIED / ADDED / REMOVED classification
#   - Numbering/title/parent/format-only vs content change
#   - Ambiguous / low-confidence stay NEEDS_REVIEW
#   - Retrieval independence for Điều 1.2 / 1.3
# Dependencies:
#   - pytest, CMP-01/02/03 pipelines, diff_engine, ClauseDiffEngine
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: tests/fixtures/contracts/Hop_dong_mau_Ra_soat_Phap_ly_V*.txt
# Important Notes: 0 LLM. Diff uses full mapped clause sets, not top-k RAG.
# =============================================================================

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.ai.document_structure.diff_config import DiffConfig
from app.ai.document_structure.diff_engine import (
    classify_pair,
    diff_mapping_result,
    diff_normalized_structures,
)
from app.ai.document_structure.diff_text import (
    content_fingerprint,
    sentence_changes,
    token_changes,
)
from app.ai.document_structure.diff_types import (
    ChangeType,
    DiffClassification,
    DiffVerificationStatus,
)
from app.ai.document_structure.mapping_engine import map_normalized_structures
from app.ai.document_structure.mapping_types import (
    ClauseMapping,
    MappingCandidate,
    MappingResult,
    MappingSignals,
    MappingStatus,
    MappingType,
    clause_ref,
)
from app.ai.document_structure.normalization import (
    NormalizedDocumentStructure,
    NormalizedUnit,
    normalize_structure,
)
from app.ai.document_structure.pipeline import extract_from_pages, extract_from_text
from app.ai.document_structure.types import StructuralUnitType
from app.services.document_structure.differ import ClauseDiffEngine

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


def _norm(text: str, *, title: str = "Doc") -> NormalizedDocumentStructure:
    return normalize_structure(extract_from_text(text, title=title, document_id=uuid4()))


def _unit(
    *,
    source_id: str,
    unit_type: StructuralUnitType,
    number: str,
    title: str,
    body: str,
    parent_key: str | None = None,
    order_index: int = 1,
    document_id=None,
    identity_key: str | None = None,
) -> NormalizedUnit:
    key = identity_key or f"{unit_type.value}:{number}"
    parent_number = parent_key.split(":")[-1] if parent_key else None
    number_path = (parent_number, number) if parent_number else (number,)
    return NormalizedUnit(
        source_id=source_id,
        document_id=document_id or uuid4(),
        type=unit_type,
        canonical_number=number,
        identity_key=key,
        qualified_key=f"{parent_key}/{key}" if parent_key else key,
        number_path=number_path,
        parent_identity_key=parent_key,
        original_title=title,
        original_text=body,
        original_heading=title,
        normalized_title=title.casefold(),
        folded_title=title.casefold(),
        normalized_body=body.casefold(),
        folded_body=body.casefold(),
        aliases=(number, title.casefold()),
        heading_path=title,
        order_index=order_index,
        level=1 if parent_key else 0,
        page_start=1,
        page_end=1,
    )


def _signals(**overrides: object) -> MappingSignals:
    base = MappingSignals(
        number_match=True,
        type_match=True,
        parent_match=True,
        title_similarity=1.0,
        lexical_similarity=1.0,
        method="test",
    )
    return MappingSignals(**{**base.as_dict(), **overrides})  # type: ignore[arg-type]


def _row(
    source: NormalizedUnit | None,
    target: NormalizedUnit | None,
    *,
    status: MappingStatus,
    mapping_type: MappingType = MappingType.EXACT,
    confidence: float = 1.0,
    candidates: list[MappingCandidate] | None = None,
) -> ClauseMapping:
    return ClauseMapping(
        source_unit=source,
        target_unit=target,
        mapping_type=mapping_type,
        confidence=confidence,
        confidence_level=status,
        signals=_signals(),
        source_ref=clause_ref(source, version_id=None) if source else None,
        target_ref=clause_ref(target, version_id=None) if target else None,
        candidates=candidates or [],
    )


def _mapping(
    *rows: ClauseMapping,
    unmatched: tuple[ClauseMapping, ...] = (),
) -> MappingResult:
    source_id = next(
        (row.source_unit.document_id for row in rows if row.source_unit),
        uuid4(),
    )
    target_id = next(
        (
            row.target_unit.document_id
            for row in (*rows, *unmatched)
            if row.target_unit
        ),
        uuid4(),
    )
    return MappingResult(
        source_document_id=source_id,
        target_document_id=target_id,
        source_version_id=None,
        target_version_id=None,
        mappings=list(rows),
        unmatched_targets=list(unmatched),
        metadata={"mapping_llm_calls": 0},
    )


# ---------------------------------------------------------------------------
# Unit — text helpers
# ---------------------------------------------------------------------------


def test_token_replace_and_insert_delete() -> None:
    changes = token_changes(
        "bên a thanh toán trong 30 ngày",
        "bên a thanh toán trong 45 ngày làm việc",
    )
    types = {item.change_type for item in changes}
    assert ChangeType.REPLACED in types or ChangeType.INSERTED in types
    joined = " ".join(f"{item.old}->{item.new}" for item in changes)
    assert "30" in joined and "45" in joined


def test_sentence_level_diff_uses_existing_splitter() -> None:
    old = "Câu một không đổi. Câu hai bị sửa 30 ngày. Câu ba giữ."
    new = "Câu một không đổi. Câu hai bị sửa 45 ngày. Câu ba giữ. Câu bốn thêm."
    changes = sentence_changes(old, new)
    assert changes
    assert any(item.change_type is ChangeType.REPLACED for item in changes)
    assert any(item.change_type is ChangeType.INSERTED for item in changes)


def test_content_hash_is_deterministic() -> None:
    assert content_fingerprint("abc") == content_fingerprint("abc")
    assert content_fingerprint("abc") != content_fingerprint("abd")


# ---------------------------------------------------------------------------
# Unit — classification rules
# ---------------------------------------------------------------------------


def test_unchanged_same_normalized_text_ac01() -> None:
    left = _unit(
        source_id="v1-1.2",
        unit_type=StructuralUnitType.CLAUSE,
        number="1.2",
        title="Phạm vi",
        body="chi tiết tính năng được quy định tại phụ lục 01",
    )
    right = _unit(
        source_id="v2-1.2",
        unit_type=StructuralUnitType.CLAUSE,
        number="1.2",
        title="Phạm vi",
        body="chi tiết tính năng được quy định tại phụ lục 01",
        document_id=uuid4(),
    )
    row = classify_pair(left, right)
    assert row.classification is DiffClassification.UNCHANGED
    assert row.signals.content_changed is False
    assert row.verification_status is DiffVerificationStatus.VERIFIED


def test_modified_when_normalized_text_differs_ac02() -> None:
    left = _unit(
        source_id="v1-3.1",
        unit_type=StructuralUnitType.CLAUSE,
        number="3.1",
        title="Giá trị",
        body="thời hạn hợp đồng là 12 tháng",
    )
    right = _unit(
        source_id="v2-3.1",
        unit_type=StructuralUnitType.CLAUSE,
        number="3.1",
        title="Giá trị",
        body="thời hạn hợp đồng là 24 tháng",
        document_id=uuid4(),
    )
    row = classify_pair(left, right)
    assert row.classification is DiffClassification.MODIFIED
    assert row.signals.content_changed is True
    assert any("12" in item.old and "24" in item.new for item in row.changes)


def test_added_unmatched_target_ac03() -> None:
    target = _unit(
        source_id="v2-7.3",
        unit_type=StructuralUnitType.CLAUSE,
        number="7.3",
        title="Mới",
        body="điều khoản chỉ có ở v2",
    )
    result = diff_mapping_result(
        _mapping(
            unmatched=(_row(None, target, status=MappingStatus.UNMATCHED),),
        )
    )
    row = result.find_target("CLAUSE:7.3")
    assert row is not None
    assert row.classification is DiffClassification.ADDED
    assert row.source_unit is None
    assert row.target_ref is not None
    assert row.verification_status is DiffVerificationStatus.VERIFIED


def test_removed_unmatched_source_ac04() -> None:
    source = _unit(
        source_id="v1-7.3",
        unit_type=StructuralUnitType.CLAUSE,
        number="7.3",
        title="Cũ",
        body="điều khoản chỉ có ở v1",
    )
    result = diff_mapping_result(
        _mapping(_row(source, None, status=MappingStatus.UNMATCHED))
    )
    row = result.find_source("CLAUSE:7.3")
    assert row is not None
    assert row.classification is DiffClassification.REMOVED
    assert row.target_unit is None
    assert row.source_ref is not None


def test_numbering_change_same_content_is_unchanged_ac05() -> None:
    left = _unit(
        source_id="v1-8",
        unit_type=StructuralUnitType.ARTICLE,
        number="8",
        title="Trách nhiệm",
        body="bên vi phạm phải bồi thường thiệt hại trực tiếp",
        identity_key="ARTICLE:8",
    )
    right = _unit(
        source_id="v2-9",
        unit_type=StructuralUnitType.ARTICLE,
        number="9",
        title="Trách nhiệm",
        body="bên vi phạm phải bồi thường thiệt hại trực tiếp",
        identity_key="ARTICLE:9",
        document_id=uuid4(),
    )
    row = classify_pair(left, right)
    assert row.classification is DiffClassification.UNCHANGED
    assert row.signals.number_changed is True
    assert row.signals.content_changed is False


def test_title_parent_position_change_without_content_is_unchanged() -> None:
    left = _unit(
        source_id="v1-8.1",
        unit_type=StructuralUnitType.CLAUSE,
        number="8.1",
        title="Bồi thường",
        body="bồi thường thiệt hại trực tiếp",
        parent_key="ARTICLE:8",
        order_index=1,
    )
    right = _unit(
        source_id="v2-9.1",
        unit_type=StructuralUnitType.CLAUSE,
        number="9.1",
        title="Bồi thường thiệt hại",
        body="bồi thường thiệt hại trực tiếp",
        parent_key="ARTICLE:9",
        order_index=4,
        identity_key="CLAUSE:9.1",
        document_id=uuid4(),
    )
    row = classify_pair(left, right)
    assert row.classification is DiffClassification.UNCHANGED
    assert row.signals.title_changed is True
    assert row.signals.parent_changed is True
    assert row.signals.position_changed is True
    assert row.signals.content_changed is False


def test_whitespace_and_line_wrap_are_unchanged_ac07() -> None:
    v1 = _norm("ĐIỀU 1. A\n1.1. Bên A phải thanh toán\ntrong vòng 30 ngày.\n")
    v2 = _norm("ĐIỀU 1. A\n1.1. Bên A phải thanh toán trong vòng 30 ngày.\n")
    result = diff_normalized_structures(v1, v2)
    row = result.find_source("CLAUSE:1.1")
    assert row is not None
    assert row.classification is DiffClassification.UNCHANGED
    assert row.signals.content_changed is False


def test_ambiguous_mapping_is_not_silently_classified_ac08() -> None:
    source = _unit(
        source_id="a",
        unit_type=StructuralUnitType.CLAUSE,
        number="8.2",
        title="Bồi thường",
        body="bên b bồi thường thiệt hại trực tiếp",
    )
    x = _unit(
        source_id="x",
        unit_type=StructuralUnitType.CLAUSE,
        number="9.2",
        title="Bồi thường",
        body="bên b bồi thường thiệt hại trực tiếp",
        document_id=uuid4(),
    )
    y = _unit(
        source_id="y",
        unit_type=StructuralUnitType.CLAUSE,
        number="9.3",
        title="Bồi thường",
        body="bên b bồi thường thiệt hại trực tiếp",
        document_id=x.document_id,
    )
    candidates = [
        MappingCandidate(
            target_source_id="x",
            target_identity_key="CLAUSE:9.2",
            confidence=0.87,
            signals=_signals(),
        ),
        MappingCandidate(
            target_source_id="y",
            target_identity_key="CLAUSE:9.3",
            confidence=0.86,
            signals=_signals(),
        ),
    ]
    result = diff_mapping_result(
        _mapping(
            _row(
                source,
                None,
                status=MappingStatus.AMBIGUOUS,
                mapping_type=MappingType.ONE_TO_MANY_CANDIDATE,
                confidence=0.87,
                candidates=candidates,
            ),
            unmatched=(
                _row(None, x, status=MappingStatus.UNMATCHED),
                _row(None, y, status=MappingStatus.UNMATCHED),
            ),
        )
    )
    row = result.find_source("CLAUSE:8.2")
    assert row is not None
    assert row.classification is DiffClassification.AMBIGUOUS_MAPPING
    assert row.verification_status is DiffVerificationStatus.NEEDS_REVIEW
    assert row.classification is not DiffClassification.REMOVED
    assert result.find_target("CLAUSE:9.2") is None
    assert result.find_target("CLAUSE:9.3") is None
    assert result.metadata["added_count"] == 0
    assert result.metadata["removed_count"] == 0


def test_low_confidence_is_needs_review_not_definitive() -> None:
    source = _unit(
        source_id="s",
        unit_type=StructuralUnitType.CLAUSE,
        number="4.1",
        title="A",
        body="nội dung cũ",
    )
    target = _unit(
        source_id="t",
        unit_type=StructuralUnitType.CLAUSE,
        number="5.1",
        title="A",
        body="nội dung mới hoàn toàn khác",
        document_id=uuid4(),
    )
    result = diff_mapping_result(
        _mapping(
            _row(
                source,
                target,
                status=MappingStatus.LOW_CONFIDENCE,
                mapping_type=MappingType.LEXICAL,
                confidence=0.58,
            )
        )
    )
    row = result.find_source("CLAUSE:4.1")
    assert row is not None
    assert row.classification is DiffClassification.UNKNOWN
    assert row.verification_status is DiffVerificationStatus.NEEDS_REVIEW
    assert row.definitive is False
    assert result.metadata["modified_count"] == 0


def test_empty_clause_pair_is_unchanged() -> None:
    left = _unit(
        source_id="e1",
        unit_type=StructuralUnitType.ARTICLE,
        number="4",
        title="Nghiệm thu",
        body="",
    )
    right = _unit(
        source_id="e2",
        unit_type=StructuralUnitType.ARTICLE,
        number="4",
        title="Nghiệm thu",
        body="",
        document_id=uuid4(),
    )
    row = classify_pair(left, right)
    assert row.classification is DiffClassification.UNCHANGED


def test_hash_short_circuit_skips_token_diff() -> None:
    left = _unit(
        source_id="h1",
        unit_type=StructuralUnitType.CLAUSE,
        number="1.1",
        title="A",
        body="cùng một nội dung",
    )
    right = _unit(
        source_id="h2",
        unit_type=StructuralUnitType.CLAUSE,
        number="1.1",
        title="A",
        body="cùng một nội dung",
        document_id=uuid4(),
    )
    row = classify_pair(left, right, config=DiffConfig(use_content_hash=True))
    assert row.signals.content_hash_match is True
    assert row.changes == []
    assert row.classification is DiffClassification.UNCHANGED


def test_duplicate_accepted_mapping_is_recorded() -> None:
    source_a = _unit(
        source_id="a",
        unit_type=StructuralUnitType.CLAUSE,
        number="1.1",
        title="A",
        body="x",
    )
    source_b = _unit(
        source_id="b",
        unit_type=StructuralUnitType.CLAUSE,
        number="1.2",
        title="B",
        body="y",
        document_id=source_a.document_id,
    )
    target = _unit(
        source_id="t",
        unit_type=StructuralUnitType.CLAUSE,
        number="1.1",
        title="A",
        body="x",
        document_id=uuid4(),
    )
    result = diff_mapping_result(
        _mapping(
            _row(source_a, target, status=MappingStatus.EXACT),
            _row(source_b, target, status=MappingStatus.HIGH_CONFIDENCE),
        )
    )
    assert result.metadata["error_count"] >= 1
    assert "duplicate_target_mapping" in result.metadata["errors"]


def test_invalid_empty_mapping_is_unknown() -> None:
    result = diff_mapping_result(
        _mapping(_row(None, None, status=MappingStatus.UNMATCHED))
    )
    assert result.diffs[0].classification is DiffClassification.UNKNOWN
    assert result.metadata["error_count"] >= 1


def test_original_text_not_mutated() -> None:
    original = "Bên A thanh toán 30 ngày."
    left = _unit(
        source_id="o1",
        unit_type=StructuralUnitType.CLAUSE,
        number="1.1",
        title="A",
        body=original,
    )
    right = _unit(
        source_id="o2",
        unit_type=StructuralUnitType.CLAUSE,
        number="1.1",
        title="A",
        body="Bên A thanh toán 45 ngày.",
        document_id=uuid4(),
    )
    classify_pair(left, right)
    assert left.original_text == original
    assert right.original_text == "Bên A thanh toán 45 ngày."


def test_as_dict_omits_full_text_by_default() -> None:
    left = _unit(
        source_id="s",
        unit_type=StructuralUnitType.CLAUSE,
        number="1.1",
        title="A",
        body="bí mật thương mại không được log",
    )
    right = _unit(
        source_id="t",
        unit_type=StructuralUnitType.CLAUSE,
        number="1.1",
        title="A",
        body="bí mật thương mại không được log",
        document_id=uuid4(),
    )
    payload = classify_pair(left, right).as_dict()
    assert "bí mật thương mại" not in str(payload)
    assert "old_text" not in payload
    with_text = classify_pair(left, right).as_dict(include_text=True)
    assert with_text["old_text"] == left.original_text


def test_empty_documents_diff_without_crash() -> None:
    result = diff_normalized_structures(_norm(""), _norm(""))
    assert result.diffs == []
    assert result.metadata["diff_llm_calls"] == 0


def test_determinism_same_input_same_output_ac10() -> None:
    v1 = _norm("ĐIỀU 1. A\n1.1. Thanh toán 30 ngày.\n1.2. Bí mật.\n")
    v2 = _norm("ĐIỀU 1. A\n1.1. Thanh toán 45 ngày.\n1.2. Bí mật.\n")
    first = diff_normalized_structures(v1, v2).as_dict()
    second = diff_normalized_structures(v1, v2).as_dict()
    first["metadata"].pop("diff_latency_ms", None)
    second["metadata"].pop("diff_latency_ms", None)
    first.get("mapping_metadata", {}).pop("mapping_latency_ms", None)
    second.get("mapping_metadata", {}).pop("mapping_latency_ms", None)
    assert first == second


# ---------------------------------------------------------------------------
# Integration — extract → normalize → map → diff
# ---------------------------------------------------------------------------


def test_pipeline_added_removed_and_modified() -> None:
    v1 = _norm(
        "ĐIỀU 1. A\n"
        "1.1. Thời hạn là 12 tháng.\n"
        "1.2. Chỉ có ở V1.\n"
    )
    v2 = _norm(
        "ĐIỀU 1. A\n"
        "1.1. Thời hạn là 24 tháng.\n"
        "1.3. Chỉ có ở V2.\n"
    )
    result = ClauseDiffEngine().diff_structures(v1, v2)
    assert result.find_source("CLAUSE:1.1").classification is DiffClassification.MODIFIED  # type: ignore[union-attr]
    assert result.find_source("CLAUSE:1.2").classification is DiffClassification.REMOVED  # type: ignore[union-attr]
    assert result.find_target("CLAUSE:1.3").classification is DiffClassification.ADDED  # type: ignore[union-attr]
    assert result.metadata["diff_llm_calls"] == 0


def test_moved_clause_number_change_is_not_added_removed() -> None:
    v1 = _norm(
        "ĐIỀU 8. TRÁCH NHIỆM\n"
        "8.1. Bên vi phạm phải bồi thường thiệt hại trực tiếp.\n"
    )
    v2 = _norm(
        "ĐIỀU 9. TRÁCH NHIỆM\n"
        "9.1. Bên vi phạm phải bồi thường thiệt hại trực tiếp.\n"
    )
    mapping = map_normalized_structures(v1, v2)
    result = diff_mapping_result(mapping)
    article = result.find_source("ARTICLE:8")
    clause = result.find_source("CLAUSE:8.1")
    assert article is not None and clause is not None
    assert article.classification is DiffClassification.UNCHANGED
    assert article.signals.number_changed is True
    assert clause.classification is DiffClassification.UNCHANGED
    assert result.metadata["added_count"] == 0
    assert result.metadata["removed_count"] == 0


def test_false_negative_amount_duration_and_inserted_sentence() -> None:
    v1 = _norm(
        "ĐIỀU 3. THANH TOÁN\n"
        "3.1. Tổng giá trị là 480.000.000 đồng. Thời hạn 30 ngày.\n"
    )
    v2 = _norm(
        "ĐIỀU 3. THANH TOÁN\n"
        "3.1. Tổng giá trị là 600.000.000 đồng. Thời hạn 30 ngày. Phí phát sinh do bên A chịu.\n"
    )
    result = diff_normalized_structures(v1, v2)
    row = result.find_source("CLAUSE:3.1")
    assert row is not None
    assert row.classification is DiffClassification.MODIFIED
    blob = " ".join(f"{c.old} {c.new}" for c in row.changes)
    assert "480" in blob and "600" in blob


# ---------------------------------------------------------------------------
# Regression + false positives (retrieval independence)
# ---------------------------------------------------------------------------


def test_v1_v2_clause_1_2_and_1_3_unchanged_despite_retrieval_gap_ac06() -> None:
    v1 = normalize_structure(extract_from_pages(_pages(V1_TXT), title="V1"))
    v2 = normalize_structure(extract_from_pages(_pages(V2_TXT), title="V2"))
    # Mapping/diff receive FULL trees even if a caller only "retrieved" V2 1.2.
    result = ClauseDiffEngine().diff_structures(v1, v2)
    for key in ("CLAUSE:1.2", "CLAUSE:1.3"):
        row = result.find_source(key)
        assert row is not None, key
        assert row.classification is DiffClassification.UNCHANGED, key
        assert row.target_unit is not None and row.target_unit.identity_key == key
        assert row.signals.content_changed is False
        assert row.source_ref is not None and row.target_ref is not None
    assert result.find_target("CLAUSE:1.2").classification is not DiffClassification.ADDED  # type: ignore[union-attr]


def test_v1_v2_key_articles_and_added_clauses() -> None:
    v1 = normalize_structure(extract_from_pages(_pages(V1_TXT), title="V1"))
    v2 = normalize_structure(extract_from_pages(_pages(V2_TXT), title="V2"))
    result = diff_normalized_structures(v1, v2)

    assert result.find_source("CLAUSE:2.1").classification is DiffClassification.MODIFIED  # type: ignore[union-attr]
    assert result.find_source("CLAUSE:3.1").classification is DiffClassification.MODIFIED  # type: ignore[union-attr]
    assert result.find_source("CLAUSE:8.2").classification is DiffClassification.MODIFIED  # type: ignore[union-attr]
    assert result.find_source("CLAUSE:9.2").classification is DiffClassification.MODIFIED  # type: ignore[union-attr]
    assert result.find_source("CLAUSE:11.2").classification is DiffClassification.MODIFIED  # type: ignore[union-attr]
    assert result.find_target("CLAUSE:8.3").classification is DiffClassification.ADDED  # type: ignore[union-attr]
    assert result.find_target("CLAUSE:9.3").classification is DiffClassification.ADDED  # type: ignore[union-attr]
    assert result.metadata["removed_count"] == 0
    assert result.metadata["diff_llm_calls"] == 0
    assert result.metadata["diff_latency_ms"] >= 0

    expected_rollup = {
        "ARTICLE:1": DiffClassification.UNCHANGED,
        "ARTICLE:2": DiffClassification.MODIFIED,
        "ARTICLE:3": DiffClassification.MODIFIED,
        "ARTICLE:4": DiffClassification.UNCHANGED,
        "ARTICLE:5": DiffClassification.UNCHANGED,
        "ARTICLE:6": DiffClassification.UNCHANGED,
        "ARTICLE:7": DiffClassification.UNCHANGED,
        "ARTICLE:8": DiffClassification.MODIFIED,
        "ARTICLE:9": DiffClassification.MODIFIED,
        "ARTICLE:10": DiffClassification.UNCHANGED,
        "ARTICLE:11": DiffClassification.MODIFIED,
        "ARTICLE:12": DiffClassification.UNCHANGED,
    }
    for key, expected in expected_rollup.items():
        row = result.find_source(key)
        assert row is not None, key
        assert row.subtree_classification is expected, (
            key,
            row.classification,
            row.subtree_classification,
        )


def test_no_added_removed_labels_in_mapping_metadata() -> None:
    v1 = _norm("ĐIỀU 1. A\n1.1. X\n")
    result = diff_normalized_structures(v1, v1)
    assert result.metadata["diff_llm_calls"] == 0
    dumped = result.as_dict()
    assert "original_text" not in str(dumped["diffs"])
