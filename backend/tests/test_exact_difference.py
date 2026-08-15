# =============================================================================
# File: test_exact_difference.py
# Module/Service: Exact Difference Detection (FR8 / TASK-CMP-06)
# Layer: Service
# Purpose: Unit, alignment, pipeline, V1/V2 regression, FP/FN exact-diff tests.
# Responsibilities:
#   - Money / % / date / duration / quantity / org / location
#   - Alignment of multiple values; format-only; false positives
# Dependencies:
#   - pytest, extract_values, extract_exact_differences, CMP-01..05 pipeline
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: tests/fixtures/contracts/Hop_dong_mau_Ra_soat_Phap_ly_V*.txt
# Important Notes: 0 LLM. Facts only — no risk labels.
# =============================================================================

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from app.ai.document_structure.diff_engine import diff_normalized_structures
from app.ai.document_structure.diff_types import (
    ClauseDiff,
    DiffClassification,
    DiffResult,
    DiffSignals,
    DiffVerificationStatus,
)
from app.ai.document_structure.exact_config import ExactDiffConfig
from app.ai.document_structure.exact_engine import (
    extract_exact_differences,
    extract_from_clause_diff,
)
from app.ai.document_structure.exact_parse import extract_values, parse_number
from app.ai.document_structure.exact_types import (
    ParseStatus,
    Qualifier,
    ValueChangeType,
    ValueDirection,
    ValueType,
)
from app.ai.document_structure.mapping_types import MappingStatus, MappingType, clause_ref
from app.ai.document_structure.normalization import (
    NormalizedDocumentStructure,
    NormalizedUnit,
    normalize_structure,
)
from app.ai.document_structure.pipeline import extract_from_pages, extract_from_text
from app.ai.document_structure.types import StructuralUnitType
from app.services.document_structure.exact import ClauseExactDiffEngine

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


def _norm(text: str) -> NormalizedDocumentStructure:
    return normalize_structure(extract_from_text(text, title="Doc", document_id=uuid4()))


def _unit(body: str, *, key: str = "CLAUSE:1.1", title: str = "A") -> NormalizedUnit:
    number = key.split(":")[-1]
    unit_type = StructuralUnitType.CLAUSE if key.startswith("CLAUSE") else StructuralUnitType.ARTICLE
    return NormalizedUnit(
        source_id=key,
        document_id=uuid4(),
        type=unit_type,
        canonical_number=number,
        identity_key=key,
        qualified_key=key,
        number_path=(number,),
        parent_identity_key=None,
        original_title=title,
        original_text=body,
        original_heading=title,
        normalized_title=title.casefold(),
        folded_title=title.casefold(),
        normalized_body=body.casefold(),
        folded_body=body.casefold(),
        aliases=(number,),
        heading_path=title,
        order_index=1,
        level=1,
        page_start=1,
        page_end=1,
    )


def _diff_row(
    classification: DiffClassification,
    source: NormalizedUnit | None,
    target: NormalizedUnit | None,
) -> ClauseDiff:
    return ClauseDiff(
        classification=classification,
        verification_status=DiffVerificationStatus.VERIFIED,
        mapping_status=MappingStatus.EXACT,
        mapping_type=MappingType.EXACT,
        mapping_confidence=1.0,
        source_unit=source,
        target_unit=target,
        source_ref=clause_ref(source, version_id=None) if source else None,
        target_ref=clause_ref(target, version_id=None) if target else None,
        signals=DiffSignals(
            content_changed=classification is DiffClassification.MODIFIED,
            number_changed=False,
            title_changed=False,
            parent_changed=False,
            position_changed=False,
        ),
    )


def _result(*rows: ClauseDiff) -> DiffResult:
    return DiffResult(
        source_document_id=uuid4(),
        target_document_id=uuid4(),
        source_version_id=None,
        target_version_id=None,
        diffs=list(rows),
        metadata={},
    )


def _modified(old: str, new: str) -> list:
    return extract_from_clause_diff(
        _diff_row(DiffClassification.MODIFIED, _unit(old), _unit(new, key="CLAUSE:1.1b"))
    )


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def test_parse_number_vn_us_eu_and_ocr() -> None:
    assert parse_number("480.000.000") == Decimal("480000000")
    assert parse_number("500,000,000") == Decimal("500000000")
    assert parse_number("1.500,50") == Decimal("1500.50")
    assert parse_number("10,5") == Decimal("10.5")
    assert parse_number("500.000.OOO") is None


def test_money_and_million_scale() -> None:
    values = extract_values("Giá trị hợp đồng là 480.000.000 đồng và 500 triệu đồng.")
    money = [item for item in values if item.value_type is ValueType.MONEY]
    assert {item.number for item in money} == {Decimal("480000000"), Decimal("500000000")}
    assert all(item.currency == "VND" for item in money)


def test_page_and_clause_numbers_are_not_values_fp01_fp02() -> None:
    values = extract_values("Page 5. Điều 8.2 quy định trách nhiệm.")
    assert not any(item.number == Decimal("5") for item in values)
    assert not any(item.raw_text.strip().startswith("8.2") for item in values)


def test_contract_id_year_is_not_a_date_fp03() -> None:
    values = extract_values("Số hợp đồng HD-2025-001 được ký kết.")
    assert not any(item.value_type is ValueType.DATE for item in values)


def test_qualifier_at_most() -> None:
    values = extract_values("Tổng trách nhiệm không vượt quá 100% giá trị hợp đồng.")
    pct = [item for item in values if item.value_type is ValueType.PERCENTAGE]
    assert pct and pct[0].qualifier is Qualifier.AT_MOST
    assert pct[0].number == Decimal("100")


# ---------------------------------------------------------------------------
# Calculations / AC
# ---------------------------------------------------------------------------


def test_money_increase_ac01() -> None:
    rows = _modified("Giá trị là 500.000.000 đồng.", "Giá trị là 600.000.000 đồng.")
    money = [row for row in rows if row.value_type is ValueType.MONEY]
    assert len(money) == 1
    row = money[0]
    assert row.change_type is ValueChangeType.REPLACED_VALUE
    assert row.delta == Decimal("100000000")
    assert row.relative_change_percent == Decimal("20")
    assert row.direction is ValueDirection.INCREASE
    assert row.source_offset is not None and row.target_offset is not None


def test_money_decrease_ac02() -> None:
    rows = _modified("Giới hạn 500.000.000 đồng.", "Giới hạn 300.000.000 đồng.")
    row = rows[0]
    assert row.delta == Decimal("-200000000")
    assert row.relative_change_percent == Decimal("-40")
    assert row.direction is ValueDirection.DECREASE


def test_percentage_points_vs_relative_ac03() -> None:
    rows = _modified("Tỷ lệ 10%.", "Tỷ lệ 15%.")
    row = rows[0]
    assert row.value_type is ValueType.PERCENTAGE
    assert row.delta == Decimal("5")
    assert row.delta_unit == "PERCENTAGE_POINTS"
    assert row.relative_change_percent == Decimal("50")


def test_date_change_ac04() -> None:
    rows = _modified("Hiệu lực 01/01/2025.", "Hiệu lực 01/04/2025.")
    row = [item for item in rows if item.value_type is ValueType.DATE][0]
    assert row.old_value and row.old_value.iso_date.isoformat() == "2025-01-01"
    assert row.new_value and row.new_value.iso_date.isoformat() == "2025-04-01"
    assert row.delta == Decimal("90")
    assert row.direction is ValueDirection.LATER


def test_duration_months_ac05() -> None:
    rows = _modified("Thời hạn 12 tháng.", "Thời hạn 24 tháng.")
    row = [item for item in rows if item.value_type is ValueType.DURATION][0]
    assert row.delta == Decimal("12")
    assert row.relative_change_percent == Decimal("100")
    assert row.direction is ValueDirection.INCREASE


def test_added_and_removed_values_ac06_ac07() -> None:
    added = extract_from_clause_diff(
        _diff_row(DiffClassification.ADDED, None, _unit("Giá trị bảo lãnh là 1 tỷ đồng."))
    )
    assert added and added[0].change_type is ValueChangeType.ADDED_VALUE
    assert added[0].new_value and added[0].new_value.number == Decimal("1000000000")
    removed = extract_from_clause_diff(
        _diff_row(DiffClassification.REMOVED, _unit("Giá trị bảo lãnh là 1 tỷ đồng."), None)
    )
    assert removed and removed[0].change_type is ValueChangeType.REMOVED_VALUE


def test_format_only_money_ac08() -> None:
    rows = _modified("Giá 500.000.000 đồng.", "Giá 500,000,000 đồng.")
    substantive = [row for row in rows if row.change_type is ValueChangeType.REPLACED_VALUE]
    assert substantive == []
    with_format = extract_from_clause_diff(
        _diff_row(
            DiffClassification.MODIFIED,
            _unit("Giá 500.000.000 đồng."),
            _unit("Giá 500,000,000 đồng."),
        ),
        config=ExactDiffConfig(include_format_only=True),
    )
    assert with_format[0].change_type in {
        ValueChangeType.FORMAT_ONLY,
        ValueChangeType.UNCHANGED_VALUE,
    }


def test_multiple_values_aligned_ac09() -> None:
    rows = _modified(
        "Thanh toán 30% trong 15 ngày và 70% trong 45 ngày.",
        "Thanh toán 40% trong 15 ngày và 60% trong 60 ngày.",
    )
    pct = {
        (row.old_value.number, row.new_value.number)
        for row in rows
        if row.value_type is ValueType.PERCENTAGE and row.old_value and row.new_value
    }
    dur = {
        (row.old_value.number, row.new_value.number)
        for row in rows
        if row.value_type is ValueType.DURATION
        and row.old_value
        and row.new_value
        and row.change_type is ValueChangeType.REPLACED_VALUE
    }
    assert (Decimal("30"), Decimal("40")) in pct
    assert (Decimal("70"), Decimal("60")) in pct
    assert (Decimal("45"), Decimal("60")) in dur
    assert (Decimal("15"), Decimal("15")) not in dur
    assert (Decimal("30"), Decimal("60")) not in pct


def test_currency_change_no_fx_ac10() -> None:
    rows = _modified("Phí 500.000 USD.", "Phí 500.000 EUR.")
    row = [item for item in rows if item.value_type is ValueType.MONEY][0]
    assert row.currency_changed is True
    assert row.delta is None
    assert row.old_value and row.old_value.currency == "USD"
    assert row.new_value and row.new_value.currency == "EUR"


def test_zero_denominator_ac11() -> None:
    rows = _modified("Tỷ lệ 0%.", "Tỷ lệ 10%.")
    row = rows[0]
    assert row.delta == Decimal("10")
    assert row.relative_change_percent is None
    assert row.direction is ValueDirection.INCREASE


def test_quantity_and_entities() -> None:
    rows = _modified(
        "Giao 10 sản phẩm tại TP. Hồ Chí Minh cho Công ty TNHH ABC.",
        "Giao 15 sản phẩm tại Hà Nội cho Công ty TNHH XYZ.",
    )
    types = {row.value_type for row in rows}
    assert ValueType.QUANTITY in types
    assert ValueType.LOCATION in types
    assert ValueType.ORGANIZATION in types
    qty = next(row for row in rows if row.value_type is ValueType.QUANTITY)
    assert qty.delta == Decimal("5")
    loc = next(row for row in rows if row.value_type is ValueType.LOCATION)
    assert loc.change_type is ValueChangeType.REPLACED_VALUE
    assert loc.direction is ValueDirection.REPLACED


def test_year_equals_twelve_months_not_a_change() -> None:
    rows = _modified("Thời hạn 12 tháng.", "Thời hạn 1 năm.")
    replaced = [row for row in rows if row.change_type is ValueChangeType.REPLACED_VALUE]
    assert replaced == []


def test_business_vs_calendar_day_needs_review() -> None:
    rows = _modified("Thanh toán trong 30 ngày.", "Thanh toán trong 30 ngày làm việc.")
    dur = [row for row in rows if row.value_type is ValueType.DURATION]
    assert dur
    assert dur[0].parse_status in {ParseStatus.NEEDS_REVIEW, ParseStatus.PARSED}
    if dur[0].old_value and dur[0].new_value:
        assert dur[0].old_value.duration_kind != dur[0].new_value.duration_kind or (
            dur[0].change_type is ValueChangeType.REPLACED_VALUE
        )


def test_negative_money_and_ranges() -> None:
    values = extract_values("Phạt (500.000.000) đồng trong 30–60 ngày hoặc 10–20%.")
    money = [item for item in values if item.value_type is ValueType.MONEY]
    dur = [item for item in values if item.value_type is ValueType.DURATION]
    pct = [item for item in values if item.value_type is ValueType.PERCENTAGE]
    assert money and money[0].number == Decimal("-500000000")
    assert dur and dur[0].number == Decimal("30") and dur[0].number_max == Decimal("60")
    assert pct and pct[0].number == Decimal("10") and pct[0].number_max == Decimal("20")
    rows = _modified("Thanh toán trong 30–60 ngày.", "Thanh toán trong 45–90 ngày.")
    changed = [row for row in rows if row.value_type is ValueType.DURATION][0]
    assert changed.old_value and changed.old_value.number_max == Decimal("60")
    assert changed.new_value and changed.new_value.number == Decimal("45")
    assert changed.new_value.number_max == Decimal("90")


def test_date_range_endpoints_and_month_day_not_converted() -> None:
    rows = _modified(
        "Hiệu lực 01/01/2025 - 31/12/2025.",
        "Hiệu lực 01/01/2025 - 31/12/2026.",
    )
    dates = [
        row
        for row in rows
        if row.value_type is ValueType.DATE
        and row.old_value
        and row.new_value
        and row.change_type is ValueChangeType.REPLACED_VALUE
    ]
    assert dates
    assert dates[0].old_value and dates[0].old_value.iso_date.isoformat() == "2025-12-31"
    assert dates[0].new_value and dates[0].new_value.iso_date.isoformat() == "2026-12-31"
    mismatch = _modified("Thời hạn 30 ngày.", "Thời hạn 1 tháng.")
    review = [row for row in mismatch if row.value_type is ValueType.DURATION]
    assert review
    assert review[0].delta is None
    assert review[0].parse_status is ParseStatus.NEEDS_REVIEW


def test_missing_span_is_unavailable() -> None:
    source = _unit("Giá 500.000.000 đồng.")
    source.original_text = ""
    source.normalized_body = "Giá 500.000.000 đồng."
    source.folded_body = "gia 500.000.000 dong."
    rows = extract_from_clause_diff(
        _diff_row(
            DiffClassification.MODIFIED,
            source,
            _unit("Giá 600.000.000 đồng."),
        )
    )
    assert rows
    assert rows[0].source_span_status is ParseStatus.UNAVAILABLE
    assert rows[0].source_offset is None


def test_unchanged_clause_skips_extraction() -> None:
    rows = extract_from_clause_diff(
        _diff_row(DiffClassification.UNCHANGED, _unit("500.000.000 đồng"), _unit("500.000.000 đồng"))
    )
    assert rows == []


def test_no_risk_labels_and_no_llm() -> None:
    result = extract_exact_differences(
        _result(
            _diff_row(
                DiffClassification.MODIFIED,
                _unit("Giá 480.000.000 đồng."),
                _unit("Giá 600.000.000 đồng."),
            )
        )
    )
    dumped = result.as_dict()
    assert result.metadata["exact_diff_llm_calls"] == 0
    blob = str(dumped)
    assert "liability" not in blob.casefold()
    assert "risk" not in blob.casefold()
    assert "ADDED" not in blob or "ADDED_VALUE" in blob


def test_determinism() -> None:
    first = _modified("Phí 10% trong 15 ngày.", "Phí 15% trong 20 ngày.")
    second = _modified("Phí 10% trong 15 ngày.", "Phí 15% trong 20 ngày.")
    keys = ("change_type", "value_type", "direction", "delta", "relative_change_percent")
    assert [{k: row.as_dict()[k] for k in keys} for row in first] == [
        {k: row.as_dict()[k] for k in keys} for row in second
    ]


# ---------------------------------------------------------------------------
# Pipeline + regression
# ---------------------------------------------------------------------------


def test_pipeline_modified_money_and_duration() -> None:
    v1 = _norm("ĐIỀU 2. THỜI HẠN\n2.1. Thời hạn thực hiện là 06 tháng. Giá trị 480.000.000 đồng.\n")
    v2 = _norm("ĐIỀU 2. THỜI HẠN\n2.1. Thời hạn thực hiện là 12 tháng. Giá trị 600.000.000 đồng.\n")
    result = ClauseExactDiffEngine().extract_structures(v1, v2)
    money = [row for row in result.for_source("CLAUSE:2.1") if row.value_type is ValueType.MONEY]
    dur = [row for row in result.for_source("CLAUSE:2.1") if row.value_type is ValueType.DURATION]
    assert money and money[0].delta == Decimal("120000000")
    assert money[0].relative_change_percent == Decimal("25")
    assert dur and dur[0].delta == Decimal("6")
    assert result.metadata["exact_diff_llm_calls"] == 0


def test_v1_v2_regression_key_clauses() -> None:
    v1 = normalize_structure(extract_from_pages(_pages(V1_TXT), title="V1"))
    v2 = normalize_structure(extract_from_pages(_pages(V2_TXT), title="V2"))
    diff = diff_normalized_structures(v1, v2)
    result = extract_exact_differences(diff)
    assert diff.find_source("CLAUSE:1.2").classification is DiffClassification.UNCHANGED  # type: ignore[union-attr]
    assert diff.find_source("CLAUSE:1.3").classification is DiffClassification.UNCHANGED  # type: ignore[union-attr]
    assert result.for_source("CLAUSE:1.2") == []
    assert result.for_source("CLAUSE:1.3") == []

    money_31 = [row for row in result.for_source("CLAUSE:3.1") if row.value_type is ValueType.MONEY]
    assert money_31
    assert money_31[0].old_value and money_31[0].old_value.number == Decimal("480000000")
    assert money_31[0].new_value and money_31[0].new_value.number == Decimal("600000000")
    assert money_31[0].delta == Decimal("120000000")
    assert money_31[0].relative_change_percent == Decimal("25")

    dur_21 = [
        row
        for row in result.for_source("CLAUSE:2.1")
        if row.value_type is ValueType.DURATION
        and row.old_value
        and row.new_value
        and row.change_type is ValueChangeType.REPLACED_VALUE
    ]
    assert dur_21
    assert dur_21[0].old_value and dur_21[0].old_value.number == Decimal("6")
    assert dur_21[0].new_value and dur_21[0].new_value.number == Decimal("12")

    pct_82 = [row for row in result.for_source("CLAUSE:8.2") if row.value_type is ValueType.PERCENTAGE]
    assert pct_82
    assert pct_82[0].old_value and pct_82[0].old_value.number == Decimal("100")
    assert pct_82[0].new_value and pct_82[0].new_value.number == Decimal("30")

    dur_112 = [row for row in result.for_source("CLAUSE:11.2") if row.value_type is ValueType.DURATION]
    assert dur_112
    assert {dur_112[0].old_value.number, dur_112[0].new_value.number} == {  # type: ignore[union-attr]
        Decimal("30"),
        Decimal("15"),
    }
    assert result.metadata["exact_diff_llm_calls"] == 0
    assert result.metadata["clauses_processed"] >= 8
