# =============================================================================
# File: markdown_cleaning.py
# Module/Service: Pipeline Worker — Cleaning & Normalize ([AI])
# Layer: Service
# Purpose: Rule-based Markdown noise removal and normalization after Document
#   Understanding (FR2 v3 cleaning_normalize stage).
# Responsibilities:
#   - Remove repeated headers/footers, watermarks, stray page numbers
#   - Normalize whitespace and broken encoding characters
#   - Fix Markdown table delimiter rows for downstream chunking
#   - Preserve heading structure (# …) required by Hierarchical Chunking
# Dependencies:
#   - stdlib only
# Public Exports:
#   - CleaningStats, clean_markdown
#   - remove_repeated_headers_footers, remove_watermarks_and_page_numbers
#   - normalize_whitespace, normalize_markdown_tables, fix_broken_encoding
# Database/Table: N/A
# Related Modules: app.workers.stages.cleaning_normalize, app.ai.layout
# Important Notes: Pure functions only — no LLM, no I/O, no DB.
# =============================================================================

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_HEADING_RE = re.compile(r"^(#{1,6})\s+")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|?\s*$")
_TABLE_DELIMITER_RE = re.compile(r"^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$")

_ZERO_WIDTH_CHARS = frozenset(
    "\u200b\u200c\u200d\ufeff\u2060\u180e"
)
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_PAGE_NUMBER_RE = re.compile(
    r"^\s*(?:"
    r"\d{1,4}"
    r"|page\s+\d{1,4}"
    r"|trang\s+\d{1,4}"
    r"|-\s*\d{1,4}\s*-"
    r"|—\s*\d{1,4}\s*—"
    r")\s*$",
    re.IGNORECASE,
)
_WATERMARK_INLINE_RE = re.compile(
    r"(?:\bconfidential\b|\bdraft\b|\bwatermark\b|\binternal use only\b|\bbản nháp\b|\bmật\b)",
    re.IGNORECASE,
)

#: Default minimum occurrences before a short repeated line is treated as noise.
DEFAULT_MIN_REPEAT_COUNT = 3
#: Repeated lines longer than this are unlikely to be headers/footers.
MAX_REPEAT_LINE_LENGTH = 120


@dataclass(frozen=True, slots=True)
class CleaningStats:
    """Aggregate counts written to ``pipeline_stage_logs.metadata``."""

    chars_before: int
    chars_after: int
    lines_before: int
    lines_after: int
    lines_removed: int

    def as_dict(self) -> dict[str, int]:
        return {
            "chars_before": self.chars_before,
            "chars_after": self.chars_after,
            "lines_before": self.lines_before,
            "lines_after": self.lines_after,
            "lines_removed": self.lines_removed,
        }


def clean_markdown(
    text: str,
    *,
    min_repeat_count: int = DEFAULT_MIN_REPEAT_COUNT,
) -> tuple[str, CleaningStats]:
    """Run the full cleaning pipeline while preserving heading structure."""
    chars_before = len(text)
    lines_before = len(text.splitlines()) if text else 0

    cleaned = fix_broken_encoding(text)
    cleaned = remove_repeated_headers_footers(cleaned, min_repeat_count=min_repeat_count)
    cleaned = remove_watermarks_and_page_numbers(cleaned)
    cleaned = normalize_whitespace(cleaned)
    cleaned = normalize_markdown_tables(cleaned)

    lines_after = len(cleaned.splitlines()) if cleaned else 0
    stats = CleaningStats(
        chars_before=chars_before,
        chars_after=len(cleaned),
        lines_before=lines_before,
        lines_after=lines_after,
        lines_removed=max(0, lines_before - lines_after),
    )
    return cleaned, stats


def fix_broken_encoding(text: str) -> str:
    """Apply Unicode NFKC and strip control / zero-width characters."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", text)
    for ch in _ZERO_WIDTH_CHARS:
        if ch in normalized:
            normalized = normalized.replace(ch, "")
    normalized = normalized.replace("\u00a0", " ")
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    return _CTRL_RE.sub("", normalized)


def remove_repeated_headers_footers(
    text: str,
    *,
    min_repeat_count: int = DEFAULT_MIN_REPEAT_COUNT,
) -> str:
    """Drop short non-structural lines that repeat across many pages/sections."""
    if not text.strip():
        return text

    lines = text.splitlines()
    counts: dict[str, int] = {}
    for line in lines:
        key = _repeat_key(line)
        if key is None:
            continue
        counts[key] = counts.get(key, 0) + 1

    repeated = {
        key for key, count in counts.items() if count >= max(2, min_repeat_count)
    }
    if not repeated:
        return text

    kept: list[str] = []
    for line in lines:
        key = _repeat_key(line)
        if key is not None and key in repeated:
            continue
        kept.append(line)
    return "\n".join(kept)


def remove_watermarks_and_page_numbers(text: str) -> str:
    """Remove standalone page numbers and common watermark phrases."""
    if not text.strip():
        return text

    kept: list[str] = []
    for line in text.splitlines():
        if _is_protected_line(line):
            kept.append(line)
            continue
        stripped = line.strip()
        if not stripped:
            kept.append(line)
            continue
        if _PAGE_NUMBER_RE.match(stripped):
            continue
        if _is_watermark_line(stripped):
            continue
        kept.append(line)
    return "\n".join(kept)


def normalize_whitespace(text: str) -> str:
    """Collapse extra blank lines and trailing spaces without touching headings."""
    if not text:
        return ""

    text = fix_broken_encoding(text)
    normalized_lines: list[str] = []
    blank_run = 0

    for line in text.splitlines():
        if _HEADING_RE.match(line):
            normalized_lines.append(line.rstrip())
            blank_run = 0
            continue
        if _FENCE_RE.match(line):
            normalized_lines.append(line.rstrip())
            blank_run = 0
            continue

        trimmed = line.rstrip()
        if not trimmed:
            blank_run += 1
            if blank_run <= 1:
                normalized_lines.append("")
            continue

        blank_run = 0
        normalized_lines.append(re.sub(r"[ \t]+", " ", trimmed))

    return "\n".join(normalized_lines).strip()


def normalize_markdown_tables(text: str) -> str:
    """Ensure pipe tables include a valid ``| --- |`` delimiter row."""
    if not text.strip():
        return text

    lines = text.splitlines()
    output: list[str] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        if _is_table_start(lines, index):
            header = lines[index]
            index += 1
            if index < len(lines) and _TABLE_DELIMITER_RE.match(lines[index]):
                delimiter = _normalize_delimiter_row(header, lines[index])
                output.append(header)
                output.append(delimiter)
                index += 1
            else:
                output.append(header)
                output.append(_build_delimiter_row(header))
            while index < len(lines) and _TABLE_ROW_RE.match(lines[index]):
                output.append(lines[index].rstrip())
                index += 1
            continue

        output.append(line)
        index += 1

    return "\n".join(output)


def _repeat_key(line: str) -> str | None:
    stripped = line.strip()
    if not stripped:
        return None
    if _HEADING_RE.match(stripped):
        return None
    if _FENCE_RE.match(stripped):
        return None
    if _TABLE_ROW_RE.match(stripped):
        return None
    if len(stripped) > MAX_REPEAT_LINE_LENGTH:
        return None
    return re.sub(r"\s+", " ", stripped).casefold()


def _is_watermark_line(stripped: str) -> bool:
    if _WATERMARK_INLINE_RE.search(stripped) and len(stripped) <= MAX_REPEAT_LINE_LENGTH:
        return True
    return False


def _is_protected_line(line: str) -> bool:
    stripped = line.strip()
    return bool(
        _HEADING_RE.match(stripped)
        or _FENCE_RE.match(stripped)
        or _TABLE_ROW_RE.match(stripped)
    )


def _is_table_start(lines: list[str], index: int) -> bool:
    if not _TABLE_ROW_RE.match(lines[index]):
        return False
    if _TABLE_DELIMITER_RE.match(lines[index]):
        return False
    return True


def _build_delimiter_row(header: str) -> str:
    columns = _split_table_cells(header)
    count = max(1, len(columns))
    return "| " + " | ".join("---" for _ in range(count)) + " |"


def _normalize_delimiter_row(header: str, delimiter: str) -> str:
    header_cols = len(_split_table_cells(header))
    delimiter_cols = len(_split_table_cells(delimiter))
    if header_cols == delimiter_cols and _TABLE_DELIMITER_RE.match(delimiter):
        return delimiter.rstrip()
    return _build_delimiter_row(header)


def _split_table_cells(row: str) -> list[str]:
    body = row.strip().strip("|")
    if not body:
        return []
    return [cell.strip() for cell in body.split("|") if cell.strip() or "|" in row]
