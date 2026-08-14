# =============================================================================
# File: section_parser.py
# Module/Service: Pipeline Worker — Hierarchical Chunking ([AI])
# Layer: Service
# Purpose: Parse numbered document headings into section_number + title.
# Responsibilities:
#   - Extract "4" / "4.1" from titles like "4. SỰ KIỆN QUAN TRỌNG TRONG KỲ"
#   - Detect parent/child number relationships (4 → 4.1, 4.2)
# Dependencies:
#   - stdlib re / unicodedata
# Public Exports:
#   - ParsedHeading, parse_numbered_heading, heading_number_parent,
#     is_direct_child_number, normalize_heading_text
# Database/Table: N/A (derived from document_chunks.section / content)
# Related Modules: chunk_planner, query_router section extraction
# Important Notes: Deterministic — no LLM. Does not rewrite source headings.
# =============================================================================

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_NUMBERED_HEADING_RE = re.compile(
    r"^(?P<number>\d+(?:\.\d+)*)[.)]?\s+(?P<title>.+)$",
    re.UNICODE,
)
_BARE_NUMBER_RE = re.compile(r"^(?P<number>\d+(?:\.\d+)*)[.)]?$", re.UNICODE)
_SPACE_RE = re.compile(r"\s+", re.UNICODE)
_PUNCT_RE = re.compile(r"[^\w\s]+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class ParsedHeading:
    """Structured view of a heading title (source text is never rewritten)."""

    number: str | None
    title: str
    raw: str


def normalize_heading_text(text: str) -> str:
    """Lowercase NFKC heading/query text with punctuation stripped."""
    value = unicodedata.normalize("NFKC", text or "")
    value = value.lower().strip()
    value = _PUNCT_RE.sub(" ", value)
    value = _SPACE_RE.sub(" ", value).strip()
    return value


def parse_numbered_heading(text: str) -> ParsedHeading:
    """Split a heading into optional dotted number + remaining title.

    Examples:
        ``"4. SỰ KIỆN QUAN TRỌNG TRONG KỲ"`` → number=``"4"``
        ``"4.1 Thành lập Công ty con..."`` → number=``"4.1"``
        ``"Introduction"`` → number=None
    """
    raw = unicodedata.normalize("NFKC", (text or "").strip())
    if not raw:
        return ParsedHeading(number=None, title="", raw="")
    match = _NUMBERED_HEADING_RE.match(raw)
    if match:
        return ParsedHeading(
            number=match.group("number"),
            title=match.group("title").strip(),
            raw=raw,
        )
    bare = _BARE_NUMBER_RE.match(raw)
    if bare:
        return ParsedHeading(number=bare.group("number"), title="", raw=raw)
    return ParsedHeading(number=None, title=raw, raw=raw)


def heading_number_parent(number: str | None) -> str | None:
    """Return the immediate parent number (``4.1`` → ``4``; ``4`` → None)."""
    if not number or "." not in number:
        return None
    return number.rsplit(".", 1)[0]


def is_direct_child_number(parent_number: str, child_number: str) -> bool:
    """True when ``child_number`` is one level under ``parent_number``."""
    if not parent_number or not child_number:
        return False
    prefix = f"{parent_number}."
    if not child_number.startswith(prefix):
        return False
    rest = child_number[len(prefix) :]
    return bool(rest) and "." not in rest
