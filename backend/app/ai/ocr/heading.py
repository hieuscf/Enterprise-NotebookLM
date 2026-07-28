# =============================================================================
# File: heading.py
# Module/Service: Pipeline Worker — Document Parsing & Cleaning ([AI])
# Layer: Service
# Purpose: Heading detection heuristics from plain text and font metadata.
# Responsibilities:
#   - Detect heading-like text; infer heading level from numbered prefixes
#   - Combine font size / bold with text heuristics for PDF layout
# Dependencies:
#   - app.ai.ocr.constants
# Public Exports:
#   - _looks_like_heading_text, _heading_level_from_text, _detect_heading_from_font
# Database/Table: N/A
# Related Modules: app.ai.ocr.*
# Important Notes: No LLM; pure heuristics.
# =============================================================================

from __future__ import annotations

import re

from .constants import (
    HEADING_MAX_CHARS,
    HEADING_SIZE_RATIO,
    _ALL_CAPS_WORD_RE,
    _NUMBERED_HEADING_RE,
)


def _looks_like_heading_text(text: str) -> bool:
    """Heuristic heading detection from plain text (no font metadata)."""
    candidate = text.strip()
    if not candidate or len(candidate) > HEADING_MAX_CHARS:
        return False
    if "\n" in candidate:
        return False
    if _NUMBERED_HEADING_RE.match(candidate):
        return True
    letters = [c for c in candidate if c.isalpha()]
    if letters and _ALL_CAPS_WORD_RE.match(candidate) and len(letters) >= 3:
        return True
    return False


def _heading_level_from_text(text: str) -> int:
    """Infer heading depth from numbered prefixes (1 → 1, 1.1 → 2)."""
    match = re.match(r"^(\d+(?:\.\d+)*)", text.strip())
    if match:
        return min(match.group(1).count(".") + 1, 6)
    upper = text.strip().upper()
    if upper.startswith(("CHAPTER", "PART", "APPENDIX")):
        return 1
    if upper.startswith("SECTION"):
        return 2
    return 1


def _detect_heading_from_font(
    text: str,
    *,
    font_size: float | None,
    is_bold: bool | None,
    median_size: float,
) -> tuple[bool, int | None]:
    """Detect heading using font size / weight plus text heuristics."""
    candidate = text.strip()
    if not candidate or len(candidate) > HEADING_MAX_CHARS:
        return False, None

    size_boost = False
    if font_size is not None and median_size > 0:
        size_boost = font_size >= median_size * HEADING_SIZE_RATIO

    text_hit = _looks_like_heading_text(candidate)
    bold_short = bool(is_bold) and len(candidate) <= 120 and not candidate.endswith(".")

    if size_boost or text_hit or bold_short:
        level = _heading_level_from_text(candidate)
        if size_boost and font_size is not None and median_size > 0:
            ratio = font_size / median_size
            if ratio >= 1.6:
                level = 1
            elif ratio >= 1.35:
                level = min(level, 2)
        return True, level
    return False, None
