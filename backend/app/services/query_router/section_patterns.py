# =============================================================================
# File: section_patterns.py
# Module/Service: Query Router — Section Extraction (FR11)
# Layer: Service
# Purpose: Rule-based detection of structure-aware section queries (0 LLM).
# Responsibilities:
#   - Detect listing / TOC / heading-title / numbered-section intent
#   - Extract section number + candidate title from the query
# Dependencies:
#   - section_parser, query normalizer
# Public Exports:
#   - SectionIntent, SectionIntentMatch, detect_section_intent
# Database/Table: N/A
# Related Modules: rule_classifier, section_extraction_handler
# Important Notes: Runs before metadata patterns so "liệt kê các mục" is not
#   classified as a workspace document listing.
# =============================================================================

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from app.ai.hierarchical_chunking.section_parser import (
    parse_numbered_heading,
)
from app.services.query_router.normalizer import normalize_query

_SECTION_NUMBER_RE = re.compile(
    r"(?:mục|phần|chương|điều|section|chapter|part|item)\s+"
    r"(?P<number>\d+(?:\.\d+)*)",
    re.IGNORECASE | re.UNICODE,
)
_BARE_SECTION_NUMBER_RE = re.compile(
    r"^(?:mục|phần|chương|điều|section|chapter|part)?\s*"
    r"(?P<number>\d+(?:\.\d+)*)[.)]?\s*$",
    re.IGNORECASE | re.UNICODE,
)
_LEADING_WRAPPER_RE = re.compile(
    r"^(?:"
    r"liệt\s+kê(?:\s+các|\s+những)?|"
    r"list(?:\s+the|\s+all)?|"
    r"show(?:\s+me|\s+the)?|"
    r"các\s+mục\s+con(?:\s+của)?|"
    r"mục\s+con(?:\s+của)?|"
    r"subsections?(?:\s+of)?|"
    r"các\s+nội\s+dung(?:\s+trong)?|"
    r"các\s+phần(?:\s+trong)?|"
    r"những\s+phần(?:\s+trong)?|"
    r"các\s+nội\s+dung|"
    r"những|"
    r"các|"
    r"the"
    r")\s+",
    re.IGNORECASE | re.UNICODE,
)
_TRAILING_QUESTION_RE = re.compile(
    r"\s+(?:"
    r"là\s+gì|là\s+ai|ở\s+đâu|khi\s+nào|"
    r"gồm\s+những\s+gì|gồm\s+gì|gồm\s+những\s+phần\s+nào|"
    r"nói\s+về(?:\s+vấn\s+đề)?\s+gì|có\s+những\s+gì|"
    r"có\s+những\s+phần\s+nào|là\s+những\s+gì|"
    r"nào\s+xảy\s+ra(?:\s+trong\s+kỳ)?|xảy\s+ra(?:\s+trong\s+kỳ)?|"
    r"what\s+is|what\s+are|who\s+is|where\s+is|when\s+was|"
    r"what\s+does.+say"
    r")\s*\??$",
    re.IGNORECASE | re.UNICODE,
)
_STRUCTURE_LISTING_RE = re.compile(
    r"("
    r"gồm\s+những\s+gì|gồm\s+gì|"
    r"liệt\s+kê.+(?:mục|phần|chương|subsection|sự\s+kiện|nội\s+dung)|"
    r"các\s+mục\s+con|mục\s+con|"
    r"subsections?|"
    r"các\s+phần(?:\s+trong|\s+của)?|"
    r"những\s+phần(?:\s+trong|\s+của)?|"
    r"các\s+nội\s+dung|"
    r"trong\s+chương\s+này|"
    r"in\s+this\s+(?:chapter|section)|"
    r"nói\s+về(?:\s+vấn\s+đề)?\s+gì"
    r")",
    re.IGNORECASE | re.UNICODE,
)
_DOCUMENT_LISTING_RE = re.compile(
    r"\b(tài\s+liệu|documents?|files?|pdfs?|workspace|hóa\s+đơn|invoices?)\b",
    re.IGNORECASE | re.UNICODE,
)
_SECTION_OBJECT_RE = re.compile(
    r"(mục|phần|chương|subsection|heading|sự\s+kiện|nội\s+dung)",
    re.IGNORECASE | re.UNICODE,
)
_FACTOID_STARTER_RE = re.compile(
    r"^(what|who|when|where|why|how|khi\s+nào|ai\s+|where\s+is|who\s+is|"
    r"what\s+is|tác\s+giả|địa\s+chỉ)",
    re.IGNORECASE | re.UNICODE,
)
_COMPLEX_MARKERS_RE = re.compile(
    r"("
    r"so\s+sánh|phân\s+tích|tóm\s+tắt|giải\s+thích|tại\s+sao|"
    r"compare|analyze|summarize|explain|why|difference"
    r")",
    re.IGNORECASE | re.UNICODE,
)


class SectionIntent(StrEnum):
    """How the extractor should answer a matched section query."""

    list_children = "list_children"
    section_content = "section_content"
    outline = "outline"


@dataclass(frozen=True, slots=True)
class SectionIntentMatch:
    """Result of section-intent detection on a user query."""

    matched: bool
    intent: SectionIntent | None = None
    rule_name: str | None = None
    section_number: str | None = None
    candidate_title: str | None = None
    original: str = ""
    normalized: str = ""


def detect_section_intent(query_text: str) -> SectionIntentMatch:
    """Detect structure-aware section extraction intent (0 LLM).

    Args:
        query_text: Raw user question.

    Returns:
        Match with extracted section number / candidate title when applicable.
        ``matched=False`` when the query is not a section/listing question.
    """
    original = unicodedata.normalize("NFKC", query_text or "").strip()
    if not original:
        return SectionIntentMatch(matched=False)

    normalized = normalize_query(original)
    if not normalized:
        return SectionIntentMatch(matched=False)

    if _DOCUMENT_LISTING_RE.search(normalized) and not _SECTION_OBJECT_RE.search(
        normalized
    ):
        return SectionIntentMatch(
            matched=False, original=original, normalized=normalized
        )

    number = _extract_section_number(original, normalized)
    title = _extract_candidate_title(original, normalized, number)
    parsed_query = parse_numbered_heading(original)

    if number and _looks_like_leaf_content_query(normalized):
        return SectionIntentMatch(
            matched=True,
            intent=SectionIntent.section_content,
            rule_name="numbered_section_content",
            section_number=number,
            candidate_title=title,
            original=original,
            normalized=normalized,
        )

    if _is_outline_query(normalized):
        return SectionIntentMatch(
            matched=True,
            intent=SectionIntent.outline,
            rule_name="chapter_outline",
            section_number=number,
            candidate_title=title,
            original=original,
            normalized=normalized,
        )

    if number or _STRUCTURE_LISTING_RE.search(normalized):
        return SectionIntentMatch(
            matched=True,
            intent=SectionIntent.list_children,
            rule_name="structure_listing",
            section_number=number,
            candidate_title=title,
            original=original,
            normalized=normalized,
        )

    if parsed_query.number and parsed_query.title:
        return SectionIntentMatch(
            matched=True,
            intent=SectionIntent.list_children,
            rule_name="numbered_heading_query",
            section_number=parsed_query.number,
            candidate_title=normalize_query(parsed_query.title) or title,
            original=original,
            normalized=normalized,
        )

    if _looks_like_heading_title(original, normalized):
        intent = (
            SectionIntent.section_content
            if _looks_like_leaf_content_query(normalized)
            else SectionIntent.list_children
        )
        return SectionIntentMatch(
            matched=True,
            intent=intent,
            rule_name="heading_title_query",
            section_number=number,
            candidate_title=title,
            original=original,
            normalized=normalized,
        )

    return SectionIntentMatch(
        matched=False, original=original, normalized=normalized
    )


def _extract_section_number(original: str, normalized: str) -> str | None:
    for pattern in (_SECTION_NUMBER_RE, _BARE_SECTION_NUMBER_RE):
        match = pattern.search(original) or pattern.search(normalized)
        if match:
            return match.group("number")
    parsed = parse_numbered_heading(original)
    return parsed.number


def _extract_candidate_title(
    original: str,
    normalized: str,
    section_number: str | None,
) -> str | None:
    text = normalized
    text = _LEADING_WRAPPER_RE.sub("", text).strip()
    text = _TRAILING_QUESTION_RE.sub("", text).strip()
    if section_number:
        text = re.sub(
            rf"^(?:mục|phần|chương|điều|section|chapter|part)\s+"
            rf"{re.escape(section_number)}\s*",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip()
        text = re.sub(
            rf"^{re.escape(section_number)}\s*",
            "",
            text,
        ).strip()
    text = re.sub(
        r"\b(nào|gì|what|which|subsection|subsections|mục|phần|chương)\b",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        parsed = parse_numbered_heading(original)
        text = normalize_query(parsed.title)
    return text or None


def _looks_like_leaf_content_query(normalized: str) -> bool:
    return bool(
        re.search(
            r"(nói\s+về|what\s+does|.+\s+là\s+gì$)",
            normalized,
            flags=re.IGNORECASE,
        )
    ) and bool(
        re.search(
            r"(mục|phần|chương|section|chapter)\s+\d+(?:\.\d+)+",
            normalized,
            flags=re.IGNORECASE,
        )
    )


def _is_outline_query(normalized: str) -> bool:
    return bool(
        re.search(
            r"(các\s+phần\s+trong\s+chương\s+này|"
            r"chương\s+này\s+có\s+những\s+phần|"
            r"parts?\s+in\s+this\s+chapter|"
            r"sections?\s+in\s+this\s+(?:chapter|document))",
            normalized,
            flags=re.IGNORECASE,
        )
    )


def _looks_like_heading_title(original: str, normalized: str) -> bool:
    if _COMPLEX_MARKERS_RE.search(normalized) or _DOCUMENT_LISTING_RE.search(normalized):
        return False
    tokens = normalized.split()
    letters = [c for c in original if c.isalpha()]
    mostly_upper = bool(letters) and (
        sum(1 for c in letters if c.isupper()) / len(letters) >= 0.7
    )
    if (
        mostly_upper
        and len(tokens) >= 3
        and not _FACTOID_STARTER_RE.search(normalized)
    ):
        return True
    if tokens and tokens[0] in {"các", "những"} and len(tokens) >= 4:
        return True
    if _FACTOID_STARTER_RE.search(normalized):
        return False
    remainder = _TRAILING_QUESTION_RE.sub("", normalized).strip()
    remainder = _LEADING_WRAPPER_RE.sub("", remainder).strip()
    if len(remainder.split()) < 4:
        return False
    return bool(
        _TRAILING_QUESTION_RE.search(normalized) or _has_vietnamese(normalized)
    )


def _has_vietnamese(text: str) -> bool:
    lowered = (text or "").lower()
    if any(ch in lowered for ch in "ăâêôơưđ"):
        return True
    return any(
        token in lowered
        for token in ("sự kiện", "mục", "phần", "chương", "liệt kê")
    )
