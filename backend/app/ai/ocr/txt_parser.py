# =============================================================================
# File: txt_parser.py
# Module/Service: Pipeline Worker — Document Parsing & Cleaning ([AI])
# Layer: Service
# Purpose: Plain-text decoding and paragraph/heading block emission.
# Responsibilities:
#   - Decode UTF-8 TXT; split paragraphs; mark heading/list blocks
# Dependencies:
#   - app.ai.ocr.constants/models/cleaning/heading
# Public Exports:
#   - _parse_txt
# Database/Table: N/A
# Related Modules: app.ai.ocr.*
# Important Notes: page_count=1; page_number=1 for all blocks.
# =============================================================================

from __future__ import annotations

from .cleaning import _split_paragraphs
from .constants import BlockType, _LIST_ITEM_RE
from .heading import _heading_level_from_text, _looks_like_heading_text
from .models import _ParsedBlock


def _parse_txt(data: bytes) -> tuple[list[_ParsedBlock], int]:
    """Decode TXT and keep paragraph structure (cleaning applied later)."""
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception as exc:
        raise ValueError(f"Failed to decode TXT: {exc}") from exc

    paragraphs = _split_paragraphs(text)
    if not paragraphs:
        return [_ParsedBlock(text="", page_number=1, block_type="paragraph")], 0

    current_section: str | None = None
    blocks: list[_ParsedBlock] = []
    for para in paragraphs:
        if _looks_like_heading_text(para):
            current_section = para.strip()
            blocks.append(
                _ParsedBlock(
                    text=para,
                    page_number=1,
                    section=current_section,
                    heading_level=_heading_level_from_text(para),
                    block_type="heading",
                )
            )
        else:
            btype: BlockType = "list" if _LIST_ITEM_RE.match(para.strip()) else "paragraph"
            blocks.append(
                _ParsedBlock(
                    text=para,
                    page_number=1,
                    section=current_section,
                    block_type=btype,
                )
            )
    return blocks, 1
