# =============================================================================
# File: pdf.py
# Module/Service: Pipeline Worker — Document Parsing & Cleaning ([AI])
# Layer: Service
# Purpose: Layout-aware PDF text extraction via PyMuPDF get_text("dict").
# Responsibilities:
#   - Parse PDF pages into ordered _ParsedBlock units with bbox / font meta
#   - Detect tables / headings; reconstruct paragraphs from lines
#   - Sampled median font-size helper for large documents
# Dependencies:
#   - PyMuPDF (fitz); app.ai.ocr.constants/models/heading/paragraphs/tables
# Public Exports:
#   - _parse_pdf, _PdfLineBundle, _pdf_page_to_blocks, _extract_pdf_line_bundle,
#     _emit_pdf_block, _merge_pdf_spans, _median
# Database/Table: N/A
# Related Modules: app.ai.ocr.*
# Important Notes: Empty text layer is handled by pipeline image-OCR fallback.
# =============================================================================

from __future__ import annotations

import statistics
from dataclasses import dataclass

from .constants import (
    MEDIAN_SAMPLE_MAX,
    SPAN_SPACE_GAP_PT,
    BlockType,
    _LIST_ITEM_RE,
)
from .heading import _detect_heading_from_font, _looks_like_heading_text
from .models import _ParsedBlock
from .paragraphs import _reconstruct_paragraphs_from_lines
from .tables import _detect_table_from_aligned_lines


def _parse_pdf(data: bytes) -> tuple[list[_ParsedBlock], int]:
    """Extract PDF text with block/line/span layout; rebuild reading order."""
    import fitz  # PyMuPDF

    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ValueError(f"Failed to open PDF: {exc}") from exc

    try:
        if len(doc) == 0:
            return [], 0

        # First pass: collect font sizes for median body size
        all_sizes: list[float] = []
        page_dicts: list[dict] = []
        for page in doc:
            try:
                page_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
            except Exception as exc:
                raise ValueError(f"Failed to extract PDF page layout: {exc}") from exc
            page_dicts.append(page_dict)
            for block in page_dict.get("blocks") or []:
                if block.get("type", 0) != 0:
                    continue
                for line in block.get("lines") or []:
                    for span in line.get("spans") or []:
                        size = float(span.get("size") or 0)
                        if size > 0:
                            all_sizes.append(size)

        median_size = _median(all_sizes) if all_sizes else 12.0
        blocks_out: list[_ParsedBlock] = []
        current_section: str | None = None

        for page_no, page_dict in enumerate(page_dicts, start=1):
            page_blocks = _pdf_page_to_blocks(
                page_dict,
                page_number=page_no,
                median_size=median_size,
                current_section=current_section,
            )
            for b in page_blocks:
                blocks_out.append(b)
                if b.block_type == "heading" and b.text.strip():
                    current_section = b.text.strip()

        return blocks_out, len(doc)
    finally:
        doc.close()


@dataclass(frozen=True, slots=True)
class _PdfLineBundle:
    """Extracted lines from one PDF text block."""

    texts: list[str]
    sizes: list[float]
    bboxes: list[tuple[float, float, float, float]]
    span_cols: list[tuple[str, list[tuple[float, str]]]]
    block_bbox: tuple[float, float, float, float]
    font_size: float
    font_name: str
    is_bold: bool


def _pdf_page_to_blocks(
    page_dict: dict,
    *,
    page_number: int,
    median_size: float,
    current_section: str | None,
) -> list[_ParsedBlock]:
    """Convert one PDF page dict into ordered parsed blocks."""
    result: list[_ParsedBlock] = []
    section = current_section

    for block in page_dict.get("blocks") or []:
        if block.get("type", 0) != 0:
            continue
        bundle = _extract_pdf_line_bundle(block)
        if bundle is None:
            continue
        emitted, section = _emit_pdf_block(
            bundle,
            page_number=page_number,
            median_size=median_size,
            section=section,
        )
        result.extend(emitted)
    return result


def _extract_pdf_line_bundle(block: dict) -> _PdfLineBundle | None:
    """Pull line texts / fonts / columns from a PyMuPDF text block."""
    lines_raw = block.get("lines") or []
    if not lines_raw:
        return None

    texts: list[str] = []
    sizes: list[float] = []
    bboxes: list[tuple[float, float, float, float]] = []
    span_cols: list[tuple[str, list[tuple[float, str]]]] = []
    block_bold = False
    block_font = ""
    block_size = 0.0

    for line in lines_raw:
        text, size, font, bold, spans_x = _merge_pdf_spans(line.get("spans") or [])
        if not text.strip():
            continue
        bbox = tuple(float(x) for x in (line.get("bbox") or (0, 0, 0, 0)))
        texts.append(text)
        sizes.append(size)
        bboxes.append(bbox)  # type: ignore[arg-type]
        span_cols.append((text, spans_x))
        if size >= block_size:
            block_size = size
            block_font = font
            block_bold = bold

    if not texts:
        return None

    block_bbox = tuple(float(x) for x in (block.get("bbox") or (0, 0, 0, 0)))
    return _PdfLineBundle(
        texts=texts,
        sizes=sizes,
        bboxes=bboxes,
        span_cols=span_cols,
        block_bbox=block_bbox,  # type: ignore[arg-type]
        font_size=block_size,
        font_name=block_font,
        is_bold=block_bold,
    )


def _emit_pdf_block(
    bundle: _PdfLineBundle,
    *,
    page_number: int,
    median_size: float,
    section: str | None,
) -> tuple[list[_ParsedBlock], str | None]:
    """Emit table / heading / paragraph blocks from one PDF line bundle."""
    table_detected = _detect_table_from_aligned_lines(bundle.span_cols)
    if table_detected:
        table_text, col_count = table_detected
        return (
            [
                _ParsedBlock(
                    text=table_text,
                    page_number=page_number,
                    section=section,
                    block_type="table",
                    bbox=bundle.block_bbox,
                    font_size=bundle.font_size or None,
                    font_name=bundle.font_name or None,
                    is_bold=bundle.is_bold,
                    table_col_count=col_count,
                )
            ],
            section,
        )

    probe = bundle.texts[0] if len(bundle.texts) != 1 else bundle.texts[0]
    is_heading, level = _detect_heading_from_font(
        probe,
        font_size=bundle.font_size,
        is_bold=bundle.is_bold,
        median_size=median_size,
    )
    if is_heading and (len(bundle.texts) == 1 or _looks_like_heading_text(bundle.texts[0])):
        heading_text = bundle.texts[0].strip()
        section = heading_text
        out: list[_ParsedBlock] = [
            _ParsedBlock(
                text=heading_text,
                page_number=page_number,
                section=section,
                heading_level=level,
                block_type="heading",
                bbox=bundle.bboxes[0],
                font_size=bundle.font_size or None,
                font_name=bundle.font_name or None,
                is_bold=bundle.is_bold,
            )
        ]
        if len(bundle.texts) > 1:
            for para in _reconstruct_paragraphs_from_lines(
                bundle.texts[1:], bundle.sizes[1:], bundle.bboxes[1:]
            ):
                out.append(
                    _ParsedBlock(
                        text=para,
                        page_number=page_number,
                        section=section,
                        block_type="paragraph",
                        bbox=bundle.block_bbox,
                        font_size=bundle.font_size or None,
                        font_name=bundle.font_name or None,
                        is_bold=False,
                    )
                )
        return out, section

    out = []
    for para in _reconstruct_paragraphs_from_lines(bundle.texts, bundle.sizes, bundle.bboxes):
        btype: BlockType = "list" if _LIST_ITEM_RE.match(para.strip()) else "paragraph"
        out.append(
            _ParsedBlock(
                text=para,
                page_number=page_number,
                section=section,
                block_type=btype,
                bbox=bundle.block_bbox,
                font_size=bundle.font_size or None,
                font_name=bundle.font_name or None,
                is_bold=bundle.is_bold,
            )
        )
    return out, section


def _merge_pdf_spans(
    spans: list[dict],
) -> tuple[str, float, str, bool, list[tuple[float, str]]]:
    """Merge spans on one line; return text, dominant font meta, and x-columns."""
    if not spans:
        return "", 0.0, "", False, []

    parts: list[str] = []
    cols: list[tuple[float, str]] = []
    max_size = 0.0
    font_name = ""
    is_bold = False
    prev_x1: float | None = None

    for span in spans:
        raw = span.get("text") or ""
        if not raw:
            continue
        bbox = span.get("bbox") or (0.0, 0.0, 0.0, 0.0)
        x0, _, x1, _ = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
        size = float(span.get("size") or 0.0)
        font = str(span.get("font") or "")
        flags = int(span.get("flags") or 0)
        bold = bool(flags & 2**4) or ("bold" in font.lower())

        if size >= max_size:
            max_size = size
            font_name = font
            is_bold = bold

        if parts and prev_x1 is not None:
            gap = x0 - prev_x1
            if gap > SPAN_SPACE_GAP_PT and not parts[-1].endswith(" ") and not raw.startswith(" "):
                parts.append(" ")
        parts.append(raw)
        prev_x1 = x1
        cols.append((x0, raw.strip()))

    return "".join(parts), max_size, font_name, is_bold, cols


def _median(values: list[float]) -> float:
    """Median font size with O(k log k) sampling for very large PDFs.

    Full sort of every span size on a 1000-page doc is wasteful; we keep at
    most ``MEDIAN_SAMPLE_MAX`` evenly spaced samples (deterministic).
    """
    if not values:
        return 0.0
    if len(values) <= MEDIAN_SAMPLE_MAX:
        return float(statistics.median(values))
    step = len(values) / MEDIAN_SAMPLE_MAX
    sample = [values[int(i * step)] for i in range(MEDIAN_SAMPLE_MAX)]
    return float(statistics.median(sample))
