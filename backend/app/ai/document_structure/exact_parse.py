# =============================================================================
# File: exact_parse.py
# Module/Service: Exact Difference Detection (FR8 / TASK-CMP-06)
# Layer: Service
# Purpose: Deterministic extractors for money, %, date, duration, quantity,
#   organization, and location. No LLM. No word-number parser (none exists).
# Responsibilities:
#   - Scan clause text; skip page/clause/contract-id false positives
#   - Normalize with Decimal; preserve raw_text and local offsets
# Dependencies:
#   - stdlib re / datetime / Decimal
#   - exact_types, exact_config; sentence_splitter for context
# Public Exports:
#   - extract_values, parse_number, context_around
# Database/Table: N/A
# Related Modules: exact_align, exact_engine
# Important Notes: Original clause text is read, never written.
# =============================================================================

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.ai.document_structure.exact_config import ExactDiffConfig
from app.ai.document_structure.exact_types import (
    DurationKind,
    ExtractedValue,
    ParseStatus,
    Qualifier,
    ValueType,
)
from app.ai.hierarchical_chunking.sentence_splitter import split_sentences

_SKIP_PREFIX = re.compile(
    r"(?:điều|dieu|khoản|khoan|article|clause|trang|page|mục|muc|"
    r"phụ\s*lục|phu\s*luc|hợp\s*đồng|hop\s*dong|hd)[\s.\-]*$",
    re.I,
)
_ID_NEAR = re.compile(r"(?:hd|so|số|no\.?|id)[\s\-]*$", re.I)
_CURRENCY = r"(?:vnđ|vnd|đồng|dong|usd|eur|\$)"
_SCALE = r"(?:tỷ|ty|triệu|trieu|ngàn|nghin|nghìn)"
_MONEY_RE = re.compile(
    rf"(?P<paren>\()?(?P<sign>âm\s+|giam\s+|giảm\s+|-)?\s*"
    rf"(?P<num>\d{{1,3}}(?:,\d{{3}})+(?:\.\d+)?|\d{{1,3}}(?:[.\s]\d{{3}})+(?:[,.]\d+)?|\d+(?:[.,]\d+)?)"
    rf"(?:\s*(?P<scale>{_SCALE}))?"
    rf"(?:\s*(?P<cur>{_CURRENCY}))?"
    rf"(?(paren)\))",
    re.I,
)
_PERCENT_RE = re.compile(
    r"(?P<sign>-|âm\s+|giảm\s+)?\s*"
    r"(?P<num>\d+(?:[.,]\d+)?)\s*(?:%|phần\s*trăm|phan\s*tram)",
    re.I,
)
_ISO_DATE = re.compile(r"\b(?P<y>20\d{2}|19\d{2})-(?P<m>0?[1-9]|1[0-2])-(?P<d>0?[1-9]|[12]\d|3[01])\b")
_DMY_DATE = re.compile(
    r"\b(?P<d>0?[1-9]|[12]\d|3[01])(?P<sep>[/\-.])(?P<m>0?[1-9]|1[0-2])(?P=sep)(?P<y>20\d{2}|19\d{2})\b"
)
_VN_DATE = re.compile(
    r"\b(?P<d>0?[1-9]|[12]\d|3[01])\s*tháng\s*(?P<m>0?[1-9]|1[0-2])\s*năm\s*(?P<y>20\d{2}|19\d{2})\b",
    re.I,
)
_RANGE_DURATION_RE = re.compile(
    r"(?P<a>\d+(?:[.,]\d+)?)\s*(?:–|—|-|đến|den)\s*(?P<b>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>ngày\s*làm\s*việc|ngày|ngay|tháng|thang|năm|nam|days?|months?|years?)",
    re.I,
)
_RANGE_PERCENT_RE = re.compile(
    r"(?P<a>\d+(?:[.,]\d+)?)\s*(?:–|—|-|đến|den)\s*(?P<b>\d+(?:[.,]\d+)?)\s*%",
    re.I,
)
_DURATION_RE = re.compile(
    r"(?P<num>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>ngày\s*làm\s*việc|ngay\s*lam\s*viec|business\s*days?|"
    r"ngày|ngay|tháng|thang|năm|nam|years?|months?|days?|tuần|tuan|weeks?)",
    re.I,
)
_QTY_RE = re.compile(
    r"(?P<num>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>sản\s*phẩm|san\s*pham|người|nguoi|bản|ban|bộ|bo|lần|lan|"
    r"units?|products?)",
    re.I,
)
_ORG_RE = re.compile(
    r"\b(công ty(?:\s+(?:tnhh|cp|cổ phần|co phan|trách nhiệm hữu hạn|trach nhiem huu han))"
    r"?(?:\s+[A-ZÀ-Ỹ0-9][\wÀ-ỹ.&/-]{1,40}){1,4})",
    re.I,
)
_LOC_RE = re.compile(
    r"\b((?:tp\.?|thành phố|thanh pho|tỉnh|tinh|quận|quan)\s+"
    r"(?:hồ chí minh|ho chi minh|hà nội|ha noi|đà nẵng|da nang|"
    r"hải phòng|hai phong|cần thơ|can tho|huế|hue|[A-ZÀ-Ỹ][\wÀ-ỹ]{2,20})"
    r"|hồ chí minh|hà nội|đà nẵng|hải phòng|cần thơ)\b",
    re.I,
)
_RANGE_SEP = re.compile(r"\s*(?:–|—|-|đến|den|to)\s*", re.I)
_QUALIFIERS: list[tuple[re.Pattern[str], Qualifier]] = [
    (re.compile(r"(?:ít nhất|it nhat|tối thiểu|toi thieu|không dưới|khong duoi)\s*$", re.I), Qualifier.AT_LEAST),
    (re.compile(r"(?:không vượt quá|khong vuot qua|không quá|khong qua|tối đa|toi da)\s*$", re.I), Qualifier.AT_MOST),
    (re.compile(r"(?:hơn|hon)\s*$", re.I), Qualifier.GREATER),
    (re.compile(r"(?:dưới|duoi)\s*$", re.I), Qualifier.LESS),
    (re.compile(r"(?:bằng|bang)\s*$", re.I), Qualifier.EQUAL),
]
_SCALES = {
    "tỷ": Decimal("1000000000"),
    "ty": Decimal("1000000000"),
    "triệu": Decimal("1000000"),
    "trieu": Decimal("1000000"),
    "ngàn": Decimal("1000"),
    "nghin": Decimal("1000"),
    "nghìn": Decimal("1000"),
}
_CURRENCIES = {
    "vnđ": "VND",
    "vnd": "VND",
    "đồng": "VND",
    "dong": "VND",
    "usd": "USD",
    "$": "USD",
    "eur": "EUR",
}
_DURATION_UNITS = {
    "ngày làm việc": ("DAY", DurationKind.BUSINESS_DAY),
    "ngay lam viec": ("DAY", DurationKind.BUSINESS_DAY),
    "business day": ("DAY", DurationKind.BUSINESS_DAY),
    "business days": ("DAY", DurationKind.BUSINESS_DAY),
    "ngày": ("DAY", DurationKind.CALENDAR_DAY),
    "ngay": ("DAY", DurationKind.CALENDAR_DAY),
    "day": ("DAY", DurationKind.CALENDAR_DAY),
    "days": ("DAY", DurationKind.CALENDAR_DAY),
    "tháng": ("MONTH", DurationKind.UNKNOWN),
    "thang": ("MONTH", DurationKind.UNKNOWN),
    "month": ("MONTH", DurationKind.UNKNOWN),
    "months": ("MONTH", DurationKind.UNKNOWN),
    "năm": ("YEAR", DurationKind.UNKNOWN),
    "nam": ("YEAR", DurationKind.UNKNOWN),
    "year": ("YEAR", DurationKind.UNKNOWN),
    "years": ("YEAR", DurationKind.UNKNOWN),
    "tuần": ("WEEK", DurationKind.UNKNOWN),
    "tuan": ("WEEK", DurationKind.UNKNOWN),
    "week": ("WEEK", DurationKind.UNKNOWN),
    "weeks": ("WEEK", DurationKind.UNKNOWN),
}


def extract_values(text: str, *, config: ExactDiffConfig | None = None) -> list[ExtractedValue]:
    """Extract typed values from one clause string. Offsets are local to ``text``."""
    cfg = config or ExactDiffConfig()
    if not text:
        return []
    found: list[ExtractedValue] = []
    occupied: list[tuple[int, int]] = []

    def take(start: int, end: int) -> bool:
        if any(not (end <= left or start >= right) for left, right in occupied):
            return False
        occupied.append((start, end))
        return True

    for match in _RANGE_PERCENT_RE.finditer(text):
        low = parse_number(match.group("a"))
        high = parse_number(match.group("b"))
        if low is None or high is None:
            continue
        if take(match.start(), match.end()):
            found.append(
                _finish(
                    text,
                    ValueType.PERCENTAGE,
                    match.group(0),
                    match.start(),
                    match.end(),
                    number=low,
                    number_max=high,
                    unit="PERCENT",
                    qualifier=Qualifier.RANGE,
                )
            )

    for match in _PERCENT_RE.finditer(text):
        if _skip_false_positive(text, match.start()):
            continue
        number = parse_number(match.group("num"))
        if number is None:
            continue
        if match.group("sign"):
            number = -abs(number)
        if take(match.start(), match.end()):
            found.append(
                _finish(
                    text,
                    ValueType.PERCENTAGE,
                    match.group(0),
                    match.start(),
                    match.end(),
                    number=number,
                    unit="PERCENT",
                    qualifier=_qualifier_before(text, match.start()),
                )
            )

    for match in _MONEY_RE.finditer(text):
        if _skip_false_positive(text, match.start()):
            continue
        scale = (match.group("scale") or "").casefold()
        currency_raw = (match.group("cur") or "").casefold()
        compact = match.group("num").replace(" ", "")
        grouped = bool(
            re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", compact)
        )
        if not scale and not currency_raw and not grouped:
            continue
        if not scale and not currency_raw and grouped and compact.count(".") + compact.count(",") < 2:
            continue
        number = parse_number(match.group("num"))
        if number is None:
            continue
        if scale:
            number *= _SCALES.get(scale, Decimal("1"))
        if match.group("sign") or match.group("paren"):
            number = -abs(number)
        currency = _CURRENCIES.get(currency_raw) if currency_raw else None
        if take(match.start(), match.end()):
            found.append(
                _finish(
                    text,
                    ValueType.MONEY,
                    match.group(0).strip(),
                    match.start(),
                    match.end(),
                    number=number,
                    currency=currency,
                    unit=currency or "AMOUNT",
                    qualifier=_qualifier_before(text, match.start()),
                )
            )

    for matcher, builder in (
        (_ISO_DATE, _date_from_iso),
        (_VN_DATE, _date_from_dmy),
        (_DMY_DATE, _date_from_dmy),
    ):
        for match in matcher.finditer(text):
            if _skip_false_positive(text, match.start()) or _ID_NEAR.search(text[: match.start()][-8:]):
                continue
            parsed = builder(match, cfg)
            if parsed is None:
                continue
            if take(match.start(), match.end()):
                found.append(
                    _finish(
                        text,
                        ValueType.DATE,
                        match.group(0),
                        match.start(),
                        match.end(),
                        iso_date=parsed,
                        unit="DATE",
                    )
                )

    for match in _RANGE_DURATION_RE.finditer(text):
        if _skip_false_positive(text, match.start()):
            continue
        low = parse_number(match.group("a"))
        high = parse_number(match.group("b"))
        if low is None or high is None:
            continue
        unit_key = re.sub(r"\s+", " ", match.group("unit").casefold())
        unit, kind = _DURATION_UNITS.get(unit_key, ("UNKNOWN", DurationKind.UNKNOWN))
        if unit == "UNKNOWN":
            continue
        if take(match.start(), match.end()):
            found.append(
                _finish(
                    text,
                    ValueType.DURATION,
                    match.group(0),
                    match.start(),
                    match.end(),
                    number=low,
                    number_max=high,
                    unit=unit,
                    duration_kind=kind,
                    qualifier=Qualifier.RANGE,
                )
            )

    for match in _DURATION_RE.finditer(text):
        if _skip_false_positive(text, match.start()):
            continue
        number = parse_number(match.group("num"))
        if number is None:
            continue
        unit_key = re.sub(r"\s+", " ", match.group("unit").casefold())
        unit, kind = _DURATION_UNITS.get(unit_key, ("UNKNOWN", DurationKind.UNKNOWN))
        if unit == "UNKNOWN":
            continue
        if take(match.start(), match.end()):
            found.append(
                _finish(
                    text,
                    ValueType.DURATION,
                    match.group(0),
                    match.start(),
                    match.end(),
                    number=number,
                    unit=unit,
                    duration_kind=kind,
                    qualifier=_qualifier_before(text, match.start()),
                )
            )

    for match in _QTY_RE.finditer(text):
        if _skip_false_positive(text, match.start()):
            continue
        number = parse_number(match.group("num"))
        if number is None:
            continue
        if take(match.start(), match.end()):
            found.append(
                _finish(
                    text,
                    ValueType.QUANTITY,
                    match.group(0),
                    match.start(),
                    match.end(),
                    number=number,
                    unit=re.sub(r"\s+", " ", match.group("unit").casefold()),
                    qualifier=_qualifier_before(text, match.start()),
                )
            )

    for match in _ORG_RE.finditer(text):
        raw = match.group(1).strip(" .")
        if take(match.start(), match.end()):
            found.append(
                _finish(
                    text,
                    ValueType.ORGANIZATION,
                    raw,
                    match.start(),
                    match.end(),
                    entity_text=_norm_entity(raw),
                    unit="ORG",
                )
            )

    for match in _LOC_RE.finditer(text):
        raw = match.group(1).strip(" .")
        if take(match.start(), match.end()):
            found.append(
                _finish(
                    text,
                    ValueType.LOCATION,
                    raw,
                    match.start(),
                    match.end(),
                    entity_text=_norm_entity(raw),
                    unit="LOC",
                )
            )

    _index_by_type(found)
    found.sort(key=lambda item: item.start)
    return found


def parse_number(raw: str) -> Decimal | None:
    """Parse VN/US/EU grouped or decimal numbers. None if malformed/OCR junk."""
    text = (raw or "").strip().replace(" ", "")
    if not text or re.search(r"[oO]{2,}", text):
        return None
    try:
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", text):
            return Decimal(text.replace(".", ""))
        if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", text):
            return Decimal(text.replace(",", ""))
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+,\d+", text):
            return Decimal(text.replace(".", "").replace(",", "."))
        if re.fullmatch(r"\d+,\d{1,2}", text):
            return Decimal(text.replace(",", "."))
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def context_around(text: str, start: int, end: int, *, chars: int) -> tuple[str, str, str]:
    left = text[max(0, start - chars) : start]
    right = text[end : end + chars]
    sentence = _sentence_at(text, start)
    return left.strip(), right.strip(), sentence


def _finish(
    text: str,
    value_type: ValueType,
    raw: str,
    start: int,
    end: int,
    **kwargs: object,
) -> ExtractedValue:
    left, right, sentence = context_around(text, start, end, chars=48)
    payload = dict(kwargs)
    payload.setdefault("qualifier", Qualifier.EQUAL)
    payload.setdefault("parse_status", ParseStatus.PARSED)
    return ExtractedValue(
        value_type=value_type,
        raw_text=raw.strip(),
        start=start,
        end=end,
        sentence=sentence,
        left_context=left,
        right_context=right,
        **payload,  # type: ignore[arg-type]
    )


def _qualifier_before(text: str, start: int) -> Qualifier:
    window = text[max(0, start - 32) : start]
    for pattern, qualifier in _QUALIFIERS:
        if pattern.search(window):
            return qualifier
    if _RANGE_SEP.search(window[-8:]):
        return Qualifier.RANGE
    return Qualifier.EQUAL


def _skip_false_positive(text: str, start: int) -> bool:
    prefix = text[max(0, start - 16) : start]
    return bool(_SKIP_PREFIX.search(prefix))


def _date_from_iso(match: re.Match[str], _config: ExactDiffConfig) -> date | None:
    return _safe_date(int(match.group("y")), int(match.group("m")), int(match.group("d")))


def _date_from_dmy(match: re.Match[str], config: ExactDiffConfig) -> date | None:
    day, month, year = int(match.group("d")), int(match.group("m")), int(match.group("y"))
    if config.date_locale.upper() != "VN":
        return None
    return _safe_date(year, month, day)


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return datetime(year, month, day).date()
    except ValueError:
        return None


def _norm_entity(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" .,").casefold()


def _sentence_at(text: str, index: int) -> str:
    for sentence in split_sentences(text):
        pos = text.find(sentence)
        if pos != -1 and pos <= index < pos + len(sentence):
            return sentence
    return text[max(0, index - 40) : index + 40]


def _index_by_type(values: list[ExtractedValue]) -> None:
    counts: dict[ValueType, int] = {}
    indexed: list[ExtractedValue] = []
    for item in values:
        counts[item.value_type] = counts.get(item.value_type, 0)
        indexed.append(
            ExtractedValue(
                value_type=item.value_type,
                raw_text=item.raw_text,
                start=item.start,
                end=item.end,
                number=item.number,
                number_max=item.number_max,
                currency=item.currency,
                unit=item.unit,
                duration_kind=item.duration_kind,
                iso_date=item.iso_date,
                entity_text=item.entity_text,
                qualifier=item.qualifier,
                parse_status=item.parse_status,
                sentence=item.sentence,
                left_context=item.left_context,
                right_context=item.right_context,
                index_in_type=counts[item.value_type],
            )
        )
        counts[item.value_type] += 1
    values[:] = indexed
