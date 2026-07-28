# =============================================================================
# File: headers_footers.py
# Module/Service: Pipeline Worker — Document Parsing & Cleaning ([AI])
# Layer: Service
# Purpose: Fuzzy repeated header/footer detection and stripping across pages.
# Responsibilities:
#   - Normalize and fuzzy-match chrome lines; protect TOC / numbered headings
#   - Strip majority-repeated edge lines from parsed blocks
# Dependencies:
#   - app.ai.ocr.constants, app.ai.ocr.models, app.ai.ocr.heading
# Public Exports:
#   - _normalize_header_footer_key, _is_boilerplate_line,
#     _is_protected_content_line, _fuzzy_match, _majority_fuzzy_line,
#     _line_matches_drop, _strip_repeated_headers_footers
# Database/Table: N/A
# Related Modules: app.ai.ocr.*
# Important Notes: Requires ≥ HEADER_FOOTER_MIN_PAGES; never strips tables/headings.
# =============================================================================

from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher

from .constants import (
    HEADER_FOOTER_EDGE_LINES,
    HEADER_FOOTER_FUZZY_RATIO,
    HEADER_FOOTER_MAX_LEN,
    HEADER_FOOTER_MIN_LEN,
    HEADER_FOOTER_MIN_PAGES,
    HEADER_FOOTER_THRESHOLD,
    _CONFIDENTIAL_RE,
    _DATE_RE,
    _LIST_ITEM_RE,
    _MULTI_SPACE_RE,
    _NUMBERED_HEADING_RE,
    _PAGE_NUM_RE,
    _SECTION_MARKER_RE,
    _STANDALONE_PAGE_RE,
)
from .heading import _looks_like_heading_text
from .models import _ParsedBlock, _replace_block


def _normalize_header_footer_key(text: str) -> str:
    """Normalize a line for fuzzy header/footer comparison."""
    key = text.strip().lower()
    key = _PAGE_NUM_RE.sub("page #", key)
    key = _DATE_RE.sub("DATE", key)
    key = _CONFIDENTIAL_RE.sub("CONFIDENTIAL", key)
    key = re.sub(r"\d+", "#", key)
    key = _MULTI_SPACE_RE.sub(" ", key).strip()
    return key


def _is_boilerplate_line(text: str) -> bool:
    """Likely page chrome (page numbers, confidentiality, short dates)."""
    t = text.strip()
    if not t:
        return False
    if _PAGE_NUM_RE.match(t) or _STANDALONE_PAGE_RE.match(t):
        return True
    if _CONFIDENTIAL_RE.search(t) and len(t) <= 80:
        return True
    if _DATE_RE.fullmatch(t):
        return True
    return False


def _is_protected_content_line(text: str) -> bool:
    """True for TOC / numbered headings that must not be stripped as chrome.

    Protects lines like ``1. Giới thiệu`` near page edges. Bare page digits
    (``12``) and ``Page N`` remain strippable.
    """
    t = text.strip()
    if not t:
        return False
    # Explicit page chrome is never protected.
    if _PAGE_NUM_RE.match(t) or _STANDALONE_PAGE_RE.match(t):
        return False
    if _SECTION_MARKER_RE.match(t):
        return True
    has_letter = bool(re.search(r"[A-Za-zÀ-ỹÁÉÍÓÚĂÂÊÔƠƯáéíóú]", t))
    if not has_letter:
        return False
    if _NUMBERED_HEADING_RE.match(t):
        return True
    if _LIST_ITEM_RE.match(t):
        return True
    if _looks_like_heading_text(t):
        return True
    return False


def _fuzzy_match(a: str, b: str, *, threshold: float = HEADER_FOOTER_FUZZY_RATIO) -> bool:
    if a == b:
        return True
    na, nb = _normalize_header_footer_key(a), _normalize_header_footer_key(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    return SequenceMatcher(None, na, nb).ratio() >= threshold


def _majority_fuzzy_line(candidates: list[str], *, threshold: float) -> str | None:
    """Return a representative line present (fuzzily) on ≥ threshold of pages."""
    usable = [
        c.strip()
        for c in candidates
        if not _is_protected_content_line(c)
        and (
            HEADER_FOOTER_MIN_LEN <= len(c.strip()) <= HEADER_FOOTER_MAX_LEN
            or _is_boilerplate_line(c)
        )
    ]
    if not usable:
        return None

    clusters: list[list[str]] = []
    for line in usable:
        placed = False
        for cluster in clusters:
            if _fuzzy_match(cluster[0], line):
                cluster.append(line)
                placed = True
                break
        if not placed:
            clusters.append([line])

    best = max(clusters, key=len)
    # Denominator = number of candidate slots (one per page that had a line)
    if len(best) / max(len(candidates), 1) >= threshold:
        # Prefer the most common exact form inside the cluster
        return Counter(best).most_common(1)[0][0]
    return None


def _line_matches_drop(line: str, drop: str | None) -> bool:
    if drop is None:
        return False
    candidate = line.strip()
    if not candidate:
        return False
    if _is_protected_content_line(candidate):
        return False
    if _is_boilerplate_line(candidate) and _is_boilerplate_line(drop):
        return _fuzzy_match(candidate, drop, threshold=0.75)
    return _fuzzy_match(candidate, drop)


def _strip_repeated_headers_footers(blocks: list[_ParsedBlock]) -> list[_ParsedBlock]:
    """Remove fuzzy-repeated header/footer lines across a majority of pages."""
    page_lines: dict[int, list[str]] = {}
    page_order: list[int] = []
    for block in blocks:
        if block.page_number is None:
            continue
        if block.page_number not in page_lines:
            page_order.append(block.page_number)
            page_lines[block.page_number] = []
        for ln in block.text.splitlines():
            if ln.strip():
                page_lines[block.page_number].append(ln.strip())

    if len(page_order) < HEADER_FOOTER_MIN_PAGES:
        return blocks

    headers: list[str] = []
    footers: list[str] = []
    for pn in page_order:
        lines = page_lines.get(pn) or []
        if not lines:
            continue
        headers.append(lines[0])
        footers.append(lines[-1])

    drop_header = _majority_fuzzy_line(headers, threshold=HEADER_FOOTER_THRESHOLD)
    drop_footer = _majority_fuzzy_line(footers, threshold=HEADER_FOOTER_THRESHOLD)

    cleaned: list[_ParsedBlock] = []
    for block in blocks:
        if block.page_number is None or block.block_type in {"table", "heading", "title"}:
            cleaned.append(block)
            continue
        lines = block.text.splitlines()
        if not lines:
            cleaned.append(block)
            continue
        kept: list[str] = []
        n = len(lines)
        for i, ln in enumerate(lines):
            at_top = i < HEADER_FOOTER_EDGE_LINES
            at_bottom = i >= n - HEADER_FOOTER_EDGE_LINES
            if at_top and _line_matches_drop(ln, drop_header):
                continue
            if at_bottom and _line_matches_drop(ln, drop_footer):
                continue
            if (
                (at_top or at_bottom)
                and _is_boilerplate_line(ln)
                and not _is_protected_content_line(ln)
                and len(page_order) >= HEADER_FOOTER_MIN_PAGES
            ):
                continue
            kept.append(ln)
        text = "\n".join(kept)
        if text.strip() == block.text.strip():
            cleaned.append(block)
        else:
            cleaned.append(_replace_block(block, text=text))
    return cleaned
