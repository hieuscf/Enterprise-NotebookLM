# =============================================================================
# File: canonical_locator.py
# Module/Service: Document Intelligence / Citation
# Layer: Service
# Purpose: Deterministic Canonical Markdown block identity + citation locator.
# Responsibilities:
#   - Assign stable block_id (b0000…) and markdown_start/end spans
#   - Resolve citation text_snippet → block ranges (sub-span, not whole chunk)
#   - Backfill spans for legacy layout artifacts lacking offsets
# Dependencies:
#   - stdlib only (no LLM, no PDF)
# Public Exports:
#   - make_block_id, attach_markdown_spans, normalize_layout_blocks
#   - find_snippet_span, resolve_canonical_locator, blocks_for_chunk_content
# Database/Table: N/A (operates on markdown + layout artifact dicts)
# Related Modules: app.ai.layout, CitationResponse.locator, Knowledge View
# Important Notes:
#   - Never invent page numbers; provenance page/bbox copied from blocks only.
#   - Prefer exact match; normalized match only when whitespace/case differs.
#   - If confidence is none → empty ranges (navigate without fake highlight).
# =============================================================================

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal


Confidence = Literal["exact", "normalized", "none"]


@dataclass(frozen=True, slots=True)
class BlockRange:
    block_id: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class CanonicalLocatorResult:
    type: Literal["canonical"]
    view: Literal["knowledge"]
    markdown_start: int | None
    markdown_end: int | None
    ranges: tuple[BlockRange, ...]
    confidence: Confidence
    page_number: int | None = None
    section_index: int | None = None
    bbox: tuple[float, ...] | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": self.type,
            "view": self.view,
            "confidence": self.confidence,
            "markdown_start": self.markdown_start,
            "markdown_end": self.markdown_end,
            "ranges": [
                {"block_id": r.block_id, "start": r.start, "end": r.end}
                for r in self.ranges
            ],
        }
        if self.page_number is not None:
            payload["page_number"] = self.page_number
        if self.section_index is not None:
            payload["section_index"] = self.section_index
        if self.bbox is not None:
            payload["bbox"] = list(self.bbox)
        return payload


_WS_RE = re.compile(r"\s+", re.UNICODE)
_QUOTE_MAP = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u00a0": " ",
    }
)


def make_block_id(order_index: int) -> str:
    """Stable id within a document_version: b0000, b0001, …"""
    return f"b{max(0, int(order_index)):04d}"


def normalize_for_match(text: str) -> str:
    """Conservative normalization — must not map to a different semantic span."""
    folded = unicodedata.normalize("NFKC", text or "")
    folded = folded.translate(_QUOTE_MAP)
    return _WS_RE.sub(" ", folded).strip().lower()


def attach_markdown_spans(
    markdown: str,
    blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Assign ``id`` + ``markdown_start``/``markdown_end`` walking the markdown once.

    Blocks without a confident text match keep ``None`` offsets (no guessing).
    """
    cursor = 0
    enriched: list[dict[str, Any]] = []
    # Build NFKC map once — per-block rebuild is O(blocks × |md|) and can peg
    # a single uvicorn worker for minutes on large financial reports.
    full_norm_cache = _normalized_with_map(markdown) if blocks else None
    for index, raw in enumerate(blocks):
        block = dict(raw)
        order = int(block.get("order_index", index))
        block["id"] = str(block.get("id") or make_block_id(order))
        text = str(block.get("text") or block.get("content") or "").strip()
        if not text:
            block.setdefault("markdown_start", None)
            block.setdefault("markdown_end", None)
            enriched.append(block)
            continue

        start, end = _find_text_span(
            markdown, text, cursor, full_norm_cache=full_norm_cache
        )
        if start is None or end is None:
            # Retry from document start once (out-of-order / cleaned text).
            start, end = _find_text_span(
                markdown, text, 0, full_norm_cache=full_norm_cache
            )
        if start is not None and end is not None:
            block["markdown_start"] = start
            block["markdown_end"] = end
            cursor = end
        else:
            block["markdown_start"] = block.get("markdown_start")
            block["markdown_end"] = block.get("markdown_end")
        enriched.append(block)
    return enriched


def normalize_layout_blocks(
    markdown: str,
    blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Ensure ids + spans for Knowledge View / citation (backfill-friendly)."""
    if not blocks:
        return []
    return attach_markdown_spans(markdown, blocks)


def find_snippet_span(
    markdown: str,
    snippet: str,
) -> tuple[int, int, Confidence] | None:
    """Locate citation snippet in canonical markdown."""
    needle = (snippet or "").strip()
    if not needle:
        return None
    idx = markdown.find(needle)
    if idx >= 0:
        return idx, idx + len(needle), "exact"

    norm_md, index_map = _normalized_with_map(markdown)
    norm_needle = normalize_for_match(needle)
    if not norm_needle or len(norm_needle) < 8:
        return None
    nidx = norm_md.find(norm_needle)
    if nidx < 0:
        return None
    end_n = nidx + len(norm_needle) - 1
    if end_n >= len(index_map):
        return None
    start = index_map[nidx]
    end = index_map[end_n] + 1
    if end <= start:
        return None
    return start, end, "normalized"


def resolve_canonical_locator(
    *,
    markdown: str,
    blocks: list[dict[str, Any]],
    text_snippet: str,
    chunk_content: str | None = None,
    blocks_normalized: bool = False,
) -> CanonicalLocatorResult:
    """Resolve deterministic Knowledge View locator for a citation snippet.

    Prefers ``text_snippet`` (may be a sub-span of ``chunk_content``).

    Args:
        blocks_normalized: When True, ``blocks`` already have ids/spans — skip
            ``normalize_layout_blocks`` (critical for batch citation resolve;
            re-walking large docs per citation freezes the API event loop).
    """
    empty = CanonicalLocatorResult(
        type="canonical",
        view="knowledge",
        markdown_start=None,
        markdown_end=None,
        ranges=(),
        confidence="none",
    )
    snippet = (text_snippet or "").strip()
    if not snippet or not markdown:
        return empty

    span = find_snippet_span(markdown, snippet)
    if span is None and chunk_content:
        # Snippet may be slightly edited; try locating within chunk then map.
        chunk = chunk_content.strip()
        local = find_snippet_span(chunk, snippet)
        if local is not None:
            c_start, _, _ = find_snippet_span(markdown, chunk) or (None, None, None)
            if c_start is not None:
                abs_start = c_start + local[0]
                abs_end = c_start + local[1]
                span = (abs_start, abs_end, local[2])
    if span is None:
        return empty

    md_start, md_end, confidence = span
    norm_blocks = (
        blocks if blocks_normalized else normalize_layout_blocks(markdown, blocks)
    )
    ranges = _ranges_for_span(norm_blocks, md_start, md_end, snippet)
    page, section, bbox = _provenance_from_ranges(norm_blocks, ranges)

    return CanonicalLocatorResult(
        type="canonical",
        view="knowledge",
        markdown_start=md_start,
        markdown_end=md_end,
        ranges=tuple(ranges),
        confidence=confidence,
        page_number=page,
        section_index=section,
        bbox=bbox,
    )


def blocks_for_chunk_content(
    *,
    markdown: str,
    blocks: list[dict[str, Any]],
    chunk_content: str,
) -> tuple[list[str], int | None, int | None]:
    """Map a persisted chunk to overlapping block ids + markdown span."""
    content = (chunk_content or "").strip()
    if not content:
        return [], None, None
    span = find_snippet_span(markdown, content)
    if span is None:
        # Chunk may be heading-only or truncated; try first 120 chars.
        head = content[:120].strip()
        if head:
            span = find_snippet_span(markdown, head)
    if span is None:
        return [], None, None
    start, end, _ = span
    norm_blocks = normalize_layout_blocks(markdown, blocks)
    ranges = _ranges_for_span(norm_blocks, start, end, content)
    ids = [r.block_id for r in ranges]
    return ids, start, end


def _find_text_span(
    markdown: str,
    text: str,
    start_from: int,
    *,
    full_norm_cache: tuple[str, list[int]] | None = None,
) -> tuple[int | None, int | None]:
    idx = markdown.find(text, start_from)
    if idx >= 0:
        return idx, idx + len(text)
    # Heading titles are stored without leading hashes.
    for line_match in re.finditer(
        r"(?m)^(#{1,6}\s+)(.+?)\s*$",
        markdown[start_from:],
    ):
        title = line_match.group(2).strip()
        if title == text or normalize_for_match(title) == normalize_for_match(text):
            abs_start = start_from + line_match.start()
            abs_end = start_from + line_match.end()
            return abs_start, abs_end

    norm_needle = normalize_for_match(text)
    if not norm_needle or len(norm_needle) < 12:
        return None, None

    if full_norm_cache is not None:
        norm_hay, index_map = full_norm_cache
        # Restrict search to characters whose original index >= start_from.
        search_from = 0
        if start_from > 0:
            lo, hi = 0, len(index_map)
            while lo < hi:
                mid = (lo + hi) // 2
                if index_map[mid] < start_from:
                    lo = mid + 1
                else:
                    hi = mid
            search_from = lo
        nidx = norm_hay.find(norm_needle, search_from)
        if nidx < 0:
            return None, None
        end_n = nidx + len(norm_needle) - 1
        if end_n >= len(index_map):
            return None, None
        return index_map[nidx], index_map[end_n] + 1

    slice_md = markdown[start_from:]
    norm_hay, index_map = _normalized_with_map(slice_md)
    nidx = norm_hay.find(norm_needle)
    if nidx < 0:
        return None, None
    end_n = nidx + len(norm_needle) - 1
    if end_n >= len(index_map):
        return None, None
    return start_from + index_map[nidx], start_from + index_map[end_n] + 1


def _normalized_with_map(text: str) -> tuple[str, list[int]]:
    """NFKC + quote fold + WS collapse, with map from norm index → original index."""
    folded = unicodedata.normalize("NFKC", text or "").translate(_QUOTE_MAP)
    out: list[str] = []
    index_map: list[int] = []
    prev_space = False
    for i, ch in enumerate(folded):
        if ch.isspace():
            if out and not prev_space:
                out.append(" ")
                index_map.append(i)
                prev_space = True
            continue
        prev_space = False
        lower = ch.lower()
        out.append(lower)
        index_map.append(i)
    # Trim trailing space
    while out and out[-1] == " ":
        out.pop()
        index_map.pop()
    # Trim leading space
    while out and out[0] == " ":
        out.pop(0)
        index_map.pop(0)
    return "".join(out), index_map


def _ranges_for_span(
    blocks: list[dict[str, Any]],
    md_start: int,
    md_end: int,
    snippet: str,
) -> list[BlockRange]:
    ranges: list[BlockRange] = []
    for block in blocks:
        b_start = block.get("markdown_start")
        b_end = block.get("markdown_end")
        if not isinstance(b_start, int) or not isinstance(b_end, int):
            continue
        if b_end <= md_start or b_start >= md_end:
            continue
        block_id = str(block.get("id") or make_block_id(int(block.get("order_index") or 0)))
        # Offsets relative to block text (best effort via markdown slice).
        rel_start = max(0, md_start - b_start)
        rel_end = min(b_end - b_start, md_end - b_start)
        text = str(block.get("text") or "")
        if text and snippet:
            # Prefer offsets inside block.text when snippet is a sub-span.
            local = text.find(snippet)
            if local >= 0:
                rel_start = local
                rel_end = local + len(snippet)
            elif normalize_for_match(snippet) in normalize_for_match(text):
                # Keep markdown-derived relative offsets.
                pass
        if rel_end <= rel_start:
            continue
        ranges.append(BlockRange(block_id=block_id, start=rel_start, end=rel_end))
    return ranges


def _provenance_from_ranges(
    blocks: list[dict[str, Any]],
    ranges: list[BlockRange],
) -> tuple[int | None, int | None, tuple[float, ...] | None]:
    if not ranges:
        return None, None, None
    by_id = {str(b.get("id")): b for b in blocks if b.get("id")}
    first = by_id.get(ranges[0].block_id)
    if not first:
        return None, None, None
    page = first.get("page_number")
    section = first.get("section_index")
    bbox_raw = first.get("bbox")
    bbox: tuple[float, ...] | None = None
    if isinstance(bbox_raw, list) and len(bbox_raw) >= 4:
        try:
            bbox = tuple(float(x) for x in bbox_raw[:4])
        except (TypeError, ValueError):
            bbox = None
    page_i = int(page) if isinstance(page, int) else None
    section_i = int(section) if isinstance(section, int) else None
    return page_i, section_i, bbox
