# =============================================================================
# File: docx_parser.py
# Module/Service: Pipeline Worker — Document Parsing & Cleaning ([AI])
# Layer: Service
# Purpose: DOCX body extraction into layout-aware _ParsedBlock units.
# Responsibilities:
#   - Map paragraphs (heading/list/caption/body) and tables to blocks
#   - Use section_index (logical) with page_number=None for Citation / FR5
# Dependencies:
#   - python-docx; app.ai.ocr.constants/models/tables
# Public Exports:
#   - _parse_docx, _docx_paragraph_block, _docx_heading_level,
#     _docx_paragraph_is_bold, _docx_table_to_text, _docx_table_to_text_with_cols
# Database/Table: N/A
# Related Modules: app.ai.ocr.*
# Important Notes: Named docx_parser (not docx) to avoid confusion with python-docx.
# =============================================================================

from __future__ import annotations

import io
import re

from .constants import BlockType, _CAPTION_RE, _LIST_ITEM_RE
from .models import _ParsedBlock
from .tables import _format_kv_fallback, _format_table_semantic


def _parse_docx(data: bytes) -> tuple[list[_ParsedBlock], int]:
    """Extract DOCX body: headings, paragraphs, lists, tables, captions.

    DOCX has no reliable physical page breaks in the XML text model. Segments
    use ``page_number=None`` and ``section_index`` (1-based logical section).
    ``page_count`` returned here is the number of logical sections — not a
    physical page count (see OcrSegment docstring for Citation / FR5).
    """
    from docx import Document
    from docx.oxml.ns import qn
    from docx.table import Table as DocxTable
    from docx.text.paragraph import Paragraph

    try:
        document = Document(io.BytesIO(data))
    except Exception as exc:
        raise ValueError(f"Failed to open DOCX: {exc}") from exc

    blocks: list[_ParsedBlock] = []
    current_section: str | None = None
    section_index = 1
    section_started = False

    for child in document.element.body:
        tag = child.tag
        if tag == qn("w:p"):
            para = Paragraph(child, document)
            parsed = _docx_paragraph_block(para, current_section)
            if parsed is None:
                continue
            if parsed.block_type in {"heading", "title"}:
                if section_started:
                    section_index += 1
                section_started = True
                current_section = parsed.text.strip()
            else:
                section_started = True
            blocks.append(
                _ParsedBlock(
                    text=parsed.text,
                    page_number=None,
                    section=(
                        current_section
                        if parsed.block_type not in {"heading", "title"}
                        else parsed.text.strip()
                    ),
                    heading_level=parsed.heading_level,
                    block_type=parsed.block_type,
                    is_bold=parsed.is_bold,
                    section_index=section_index,
                )
            )
            if parsed.block_type in {"heading", "title"}:
                current_section = parsed.text.strip()
        elif tag == qn("w:tbl"):
            table = DocxTable(child, document)
            text, col_count = _docx_table_to_text_with_cols(table)
            if text.strip():
                section_started = True
                blocks.append(
                    _ParsedBlock(
                        text=text,
                        page_number=None,
                        section=current_section,
                        block_type="table",
                        section_index=section_index,
                        table_col_count=col_count,
                    )
                )

    page_count = max((b.section_index or 1 for b in blocks), default=0)
    return blocks, page_count


def _docx_paragraph_block(
    para: object,
    current_section: str | None,
) -> _ParsedBlock | None:
    """Map one DOCX paragraph to a parsed block (heading/list/caption/body)."""
    text = getattr(para, "text", None) or ""
    if not text.strip():
        return None

    style = getattr(para, "style", None)
    style_name = ((style.name or "") if style else "").lower()
    is_bold = _docx_paragraph_is_bold(para)

    if "heading" in style_name or style_name.startswith("title"):
        level = _docx_heading_level(style_name)
        btype: BlockType = "title" if style_name == "title" else "heading"
        return _ParsedBlock(
            text=text.strip(),
            page_number=None,
            section=text.strip(),
            heading_level=level,
            block_type=btype,
            is_bold=True,
        )

    if "caption" in style_name or _CAPTION_RE.match(text.strip()):
        return _ParsedBlock(
            text=text.strip(),
            page_number=None,
            section=current_section,
            block_type="caption",
            is_bold=is_bold,
        )

    if "list" in style_name or _LIST_ITEM_RE.match(text.strip()):
        return _ParsedBlock(
            text=text.strip(),
            page_number=None,
            section=current_section,
            block_type="list",
            is_bold=is_bold,
        )

    return _ParsedBlock(
        text=text.strip(),
        page_number=None,
        section=current_section,
        block_type="paragraph",
        is_bold=is_bold,
    )


def _docx_heading_level(style_name: str) -> int:
    match = re.search(r"(\d+)", style_name)
    if match:
        return min(max(int(match.group(1)), 1), 6)
    if style_name == "title":
        return 1
    return 1


def _docx_paragraph_is_bold(para: object) -> bool | None:
    runs = getattr(para, "runs", None) or []
    if not runs:
        return None
    bold_flags = [bool(getattr(r, "bold", False)) for r in runs if (getattr(r, "text", None) or "").strip()]
    if not bold_flags:
        return None
    return all(bold_flags)


def _docx_table_to_text(table: object) -> str:
    text, _cols = _docx_table_to_text_with_cols(table)
    return text


def _docx_table_to_text_with_cols(table: object) -> tuple[str, int | None]:
    rows_data: list[list[str]] = []
    for row in getattr(table, "rows", []) or []:
        cells = []
        for cell in getattr(row, "cells", []) or []:
            cells.append((getattr(cell, "text", None) or "").strip())
        if any(cells):
            rows_data.append(cells)
    if not rows_data:
        return "", None
    if len(rows_data) >= 2:
        return _format_table_semantic(rows_data[0], rows_data[1:]), len(rows_data[0])
    return _format_kv_fallback(rows_data), len(rows_data[0])
