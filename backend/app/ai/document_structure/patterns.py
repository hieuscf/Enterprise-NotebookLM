# =============================================================================
# File: patterns.py
# Module/Service: Document Structure Extraction (FR8 / TASK-CMP-01)
# Layer: Service
# Purpose: Deterministic legal/document numbering detection and normalization.
# Responsibilities:
#   - Recognize Điều / Khoản / Điểm / Phụ lục / Article / Clause / Appendix
#   - Normalize type+number without rewriting original text
#   - Assign HIGH/MEDIUM/LOW confidence from the actual match quality
# Dependencies:
#   - stdlib re / unicodedata
#   - app.ai.hierarchical_chunking.section_parser (numbered heading fallback)
# Public Exports:
#   - classify_heading_line, normalize_unit_number, fold_ocr_text,
#     is_boilerplate_line, strip_markdown_heading
# Database/Table: N/A
# Related Modules: app.ai.document_structure.pipeline
# Important Notes:
#   - Rule-based only — no LLM. OCR variants must not crash the parser.
#   - Appendix is matched before Article so "PHỤ LỤC 01" is never ARTICLE 01.
# =============================================================================

from __future__ import annotations

import re
import unicodedata

from app.ai.document_structure.types import (
    DetectedMarker,
    ExtractionConfidence,
    StructuralUnitType,
)
from app.ai.hierarchical_chunking.section_parser import parse_numbered_heading

_MD_HEADING_PREFIX = re.compile(r"^(#{1,6})\s+")
_SPACE_RE = re.compile(r"\s+", re.UNICODE)

# Running headers/footers from the sample legal PDFs (and similar templates).
_BOILERPLATE_RE = re.compile(
    r"^(?:trang\s+\d+|tài\s+liệu\s+mẫu\b|page\s+\d+)\s*$",
    re.IGNORECASE | re.UNICODE,
)

# --- Legal keywords (applied after NFKC + strip markdown hashes) ---
# Appendix FIRST so it cannot be classified as an article.
_APPENDIX_RE = re.compile(
    r"^(?:phụ\s*lục|phu\s*luc|appendix|annex|schedule)\s*"
    r"(?P<number>\d+[a-zA-Z]?)?"
    r"\s*[:.\-—–]?\s*"
    r"(?P<title>.*)$",
    re.IGNORECASE | re.UNICODE,
)

_ARTICLE_RE = re.compile(
    r"^(?:điều|dieu|điẻu|điếu|điêu|điẽu|article|art\.?)\s+"
    r"(?P<number>\d+(?:\.\d+)*)\s*"
    r"[:.\-—–]?\s*"
    r"(?P<title>.*)$",
    re.IGNORECASE | re.UNICODE,
)

_CHAPTER_RE = re.compile(
    r"^(?:chương|chuong|chapter)\s+"
    r"(?P<number>\d+|[ivxlcdm]+)\s*"
    r"[:.\-—–]?\s*"
    r"(?P<title>.*)$",
    re.IGNORECASE | re.UNICODE,
)

_SECTION_RE = re.compile(
    r"^(?:mục|muc|section|phần|phan)\s+"
    r"(?P<number>\d+(?:\.\d+)*)\s*"
    r"[:.\-—–]?\s*"
    r"(?P<title>.*)$",
    re.IGNORECASE | re.UNICODE,
)

_KHOAN_RE = re.compile(
    r"^(?:khoản|khoan|clause)\s+"
    r"(?P<number>\d+(?:\.\d+)*)\s*"
    r"[:.\-—–]?\s*"
    r"(?P<title>.*)$",
    re.IGNORECASE | re.UNICODE,
)

_DIEM_RE = re.compile(
    r"^(?:điểm|diem)\s+"
    r"(?P<number>[a-z]|\d+|[ivx]+)\s*"
    r"[).:\-—–]?\s*"
    r"(?P<title>.*)$",
    re.IGNORECASE | re.UNICODE,
)

# 1.1 / 1.2.3 at line start. Components are 1–2 digits to avoid 480.000.000 / dates.
_DOTTED_CLAUSE_RE = re.compile(
    r"^(?P<number>\d{1,2}(?:\.\d{1,2})+)(?:[.)]\s+|\.\s+|\s+)(?P<title>\S.*)$",
    re.UNICODE,
)

# a) / b. / (a) / (i) — letter or short roman, not dotted clauses.
_ITEM_RE = re.compile(
    r"^(?:\((?P<paren>[a-z]|[ivx]{1,4})\)|(?P<plain>[a-z]|[ivx]{1,4})[.)])\s+"
    r"(?P<title>\S.*)$",
    re.IGNORECASE | re.UNICODE,
)

# Integer khoản/article: "1. Title" — requires a period/paren so "01 buổi" is rejected.
_INTEGER_HEADING_RE = re.compile(
    r"^(?P<number>\d{1,2})[.)]\s+(?P<title>\S.*)$",
    re.UNICODE,
)

_PROPER_DIEU_RE = re.compile(r"điều", re.IGNORECASE | re.UNICODE)
_PROPER_PHU_LUC_RE = re.compile(r"phụ\s*lục", re.IGNORECASE | re.UNICODE)
_PROPER_ARTICLE_EN_RE = re.compile(r"\b(?:article|art\.?)\b", re.IGNORECASE)
_PROPER_APPENDIX_EN_RE = re.compile(r"\b(?:appendix|annex|schedule)\b", re.IGNORECASE)


def fold_ocr_text(text: str) -> str:
    """NFKC + strip combining marks + đ→d for OCR-tolerant keyword matching."""
    value = unicodedata.normalize("NFKC", text or "")
    value = unicodedata.normalize("NFD", value)
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = value.replace("đ", "d").replace("Đ", "D")
    return value


def strip_markdown_heading(text: str) -> tuple[str, int | None]:
    """Return ``(body, heading_level)`` without mutating the original caller string."""
    raw = unicodedata.normalize("NFKC", (text or "").replace("\u00a0", " ")).strip()
    match = _MD_HEADING_PREFIX.match(raw)
    if not match:
        return raw, None
    return raw[match.end() :].strip(), len(match.group(1))


def is_boilerplate_line(text: str) -> bool:
    """True for running headers/footers that must not become structural units."""
    folded = _SPACE_RE.sub(" ", unicodedata.normalize("NFKC", text or "")).strip()
    if not folded:
        return False
    if _BOILERPLATE_RE.match(folded):
        return True
    lowered = folded.casefold()
    return lowered.startswith("tài liệu mẫu phục vụ kiểm thử")


def normalize_unit_number(raw: str | None, unit_type: StructuralUnitType) -> str | None:
    """Canonical number. Original heading/body text is never rewritten.

    Articles/clauses drop leading zeros (``01`` → ``1``). Appendices keep
    the source form (``01``) so PHỤ LỤC 01 stays distinct from ARTICLE 1.
    """
    if raw is None:
        return None
    value = unicodedata.normalize("NFKC", str(raw)).strip().strip(".)]")
    if not value:
        return None
    if unit_type is StructuralUnitType.APPENDIX:
        return value
    parts: list[str] = []
    for part in value.split("."):
        token = part.strip()
        if token.isdigit():
            parts.append(str(int(token)))
        else:
            parts.append(token.upper() if token.isalpha() else token)
    return ".".join(parts) if parts else None


def classify_heading_line(
    text: str,
    *,
    line_index: int = 0,
    in_article: bool = False,
    known_heading: bool = False,
) -> DetectedMarker | None:
    """Classify one line as a structural marker. Returns None when unsure.

    Args:
        text: Original line (not mutated).
        line_index: Position in the flattened corpus.
        in_article: True when a current ARTICLE is open (integer khoản heuristic).
        known_heading: True when layout/chunk metadata already marked a heading.
    """
    original = text or ""
    body, md_level = strip_markdown_heading(original)
    if not body or is_boilerplate_line(body):
        return None

    folded = fold_ocr_text(body)
    folded_compact = _SPACE_RE.sub(" ", folded).strip()

    appendix = _match_appendix(body, folded_compact, original, line_index)
    if appendix is not None:
        return appendix

    article = _match_article(body, folded_compact, original, line_index)
    if article is not None:
        return article

    chapter = _CHAPTER_RE.match(body) or _CHAPTER_RE.match(folded_compact)
    if chapter:
        number = normalize_unit_number(chapter.group("number"), StructuralUnitType.CHAPTER)
        title = (chapter.group("title") or "").strip().strip("-—–").strip()
        proper = bool(re.search(r"chương", body, re.IGNORECASE)) or bool(
            re.search(r"\bchapter\b", body, re.IGNORECASE)
        )
        return DetectedMarker(
            unit_type=StructuralUnitType.CHAPTER,
            number=number,
            title=title,
            raw_line=original,
            confidence=(
                ExtractionConfidence.HIGH if proper else ExtractionConfidence.LOW
            ),
            source="legal_keyword" if proper else "ocr_variant",
            line_index=line_index,
        )

    section = _SECTION_RE.match(body) or _SECTION_RE.match(folded_compact)
    if section and not _looks_like_sentence_muc(body):
        number = normalize_unit_number(section.group("number"), StructuralUnitType.SECTION)
        title = (section.group("title") or "").strip().strip("-—–").strip()
        return DetectedMarker(
            unit_type=StructuralUnitType.SECTION,
            number=number,
            title=title,
            raw_line=original,
            confidence=ExtractionConfidence.MEDIUM,
            source="legal_keyword",
            line_index=line_index,
        )

    khoan = _KHOAN_RE.match(body) or _KHOAN_RE.match(folded_compact)
    if khoan:
        number = normalize_unit_number(khoan.group("number"), StructuralUnitType.CLAUSE)
        title = (khoan.group("title") or "").strip()
        unit_type = _clause_type_for_number(number)
        proper = bool(re.search(r"khoản", body, re.IGNORECASE)) or bool(
            re.search(r"\bclause\b", body, re.IGNORECASE)
        )
        return DetectedMarker(
            unit_type=unit_type,
            number=number,
            title=title,
            raw_line=original,
            confidence=(
                ExtractionConfidence.HIGH if proper else ExtractionConfidence.LOW
            ),
            source="legal_keyword" if proper else "ocr_variant",
            line_index=line_index,
        )

    diem = _DIEM_RE.match(body) or _DIEM_RE.match(folded_compact)
    if diem:
        number = (diem.group("number") or "").strip().lower()
        title = (diem.group("title") or "").strip()
        proper = bool(re.search(r"điểm", body, re.IGNORECASE))
        return DetectedMarker(
            unit_type=StructuralUnitType.ITEM,
            number=number or None,
            title=title,
            raw_line=original,
            confidence=(
                ExtractionConfidence.HIGH if proper else ExtractionConfidence.LOW
            ),
            source="legal_keyword" if proper else "ocr_variant",
            line_index=line_index,
        )

    dotted = _DOTTED_CLAUSE_RE.match(body)
    if dotted and not _looks_like_date_or_money(dotted.group("number")):
        number = normalize_unit_number(dotted.group("number"), StructuralUnitType.CLAUSE)
        title = (dotted.group("title") or "").strip()
        unit_type = _clause_type_for_number(number)
        return DetectedMarker(
            unit_type=unit_type,
            number=number,
            title=title,
            raw_line=original,
            confidence=ExtractionConfidence.HIGH,
            source="dotted_number",
            line_index=line_index,
        )

    item = _ITEM_RE.match(body)
    if item:
        number = (item.group("paren") or item.group("plain") or "").strip().lower()
        title = (item.group("title") or "").strip()
        if number and not number.isdigit():
            return DetectedMarker(
                unit_type=StructuralUnitType.ITEM,
                number=number,
                title=title,
                raw_line=original,
                confidence=ExtractionConfidence.MEDIUM,
                source="item_letter",
                line_index=line_index,
            )

    integer = _INTEGER_HEADING_RE.match(body)
    if integer:
        raw_num = integer.group("number")
        title = (integer.group("title") or "").strip()
        if _looks_like_integer_heading(title):
            if in_article:
                number = normalize_unit_number(raw_num, StructuralUnitType.CLAUSE)
                return DetectedMarker(
                    unit_type=StructuralUnitType.CLAUSE,
                    number=number,
                    title=title,
                    raw_line=original,
                    confidence=ExtractionConfidence.MEDIUM,
                    source="integer_khoan",
                    line_index=line_index,
                )
            number = normalize_unit_number(raw_num, StructuralUnitType.ARTICLE)
            return DetectedMarker(
                unit_type=StructuralUnitType.ARTICLE,
                number=number,
                title=title,
                raw_line=original,
                confidence=ExtractionConfidence.MEDIUM,
                source="integer_article",
                line_index=line_index,
            )

    if known_heading or md_level is not None:
        return _fallback_heading(body, original, line_index)

    return None


def _match_appendix(
    body: str,
    folded_compact: str,
    original: str,
    line_index: int,
) -> DetectedMarker | None:
    match = _APPENDIX_RE.match(body) or _APPENDIX_RE.match(folded_compact)
    if not match:
        return None
    number = normalize_unit_number(match.group("number"), StructuralUnitType.APPENDIX)
    title = (match.group("title") or "").strip().strip("-—–").strip()
    proper = bool(_PROPER_PHU_LUC_RE.search(body) or _PROPER_APPENDIX_EN_RE.search(body))
    return DetectedMarker(
        unit_type=StructuralUnitType.APPENDIX,
        number=number,
        title=title,
        raw_line=original,
        confidence=ExtractionConfidence.HIGH if proper else ExtractionConfidence.LOW,
        source="legal_keyword" if proper else "ocr_variant",
        line_index=line_index,
    )


def _match_article(
    body: str,
    folded_compact: str,
    original: str,
    line_index: int,
) -> DetectedMarker | None:
    match = _ARTICLE_RE.match(body) or _ARTICLE_RE.match(folded_compact)
    if not match:
        return None
    raw_number = match.group("number")
    title = (match.group("title") or "").strip().strip("-—–").strip()
    dotted = "." in (raw_number or "")
    # "ĐIỀU 8.2" (or OCR DIEU 8.2) is treated as a clause, not an article.
    if dotted:
        number = normalize_unit_number(raw_number, StructuralUnitType.CLAUSE)
        unit_type = _clause_type_for_number(number)
    else:
        number = normalize_unit_number(raw_number, StructuralUnitType.ARTICLE)
        unit_type = StructuralUnitType.ARTICLE
    proper = bool(_PROPER_DIEU_RE.search(body) or _PROPER_ARTICLE_EN_RE.search(body))
    return DetectedMarker(
        unit_type=unit_type,
        number=number,
        title=title,
        raw_line=original,
        confidence=ExtractionConfidence.HIGH if proper else ExtractionConfidence.LOW,
        source="legal_keyword" if proper else "ocr_variant",
        line_index=line_index,
    )


def _fallback_heading(
    body: str,
    original: str,
    line_index: int,
) -> DetectedMarker:
    """Parser/Markdown heading without a legal keyword — SECTION, never invented article."""
    parsed = parse_numbered_heading(body)
    number = parsed.number
    title = parsed.title or body
    unit_type = StructuralUnitType.SECTION
    if number and "." in number:
        unit_type = _clause_type_for_number(number)
        number = normalize_unit_number(number, unit_type)
    elif number:
        number = normalize_unit_number(number, StructuralUnitType.SECTION)
    return DetectedMarker(
        unit_type=unit_type,
        number=number,
        title=title,
        raw_line=original,
        confidence=ExtractionConfidence.MEDIUM,
        source="heading_metadata",
        line_index=line_index,
    )


def _clause_type_for_number(number: str | None) -> StructuralUnitType:
    if number and number.count(".") >= 2:
        return StructuralUnitType.SUB_CLAUSE
    return StructuralUnitType.CLAUSE


def _looks_like_date_or_money(number: str) -> bool:
    parts = number.split(".")
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        last = int(parts[2])
        if last >= 1900:
            return True
    return any(len(part) >= 3 for part in parts)


def _looks_like_sentence_muc(body: str) -> bool:
    """Reject 'mục đích ...' sentences that are not 'Mục 1' headings."""
    lowered = body.casefold()
    return lowered.startswith("mục đích") or lowered.startswith("muc dich")


def _looks_like_integer_heading(title: str) -> bool:
    """Integer '1. Title' is a heading when the title is short / title-cased."""
    stripped = title.strip()
    if not stripped or len(stripped) > 80:
        return False
    first = stripped[0]
    return first.isupper() or not first.islower()
