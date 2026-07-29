# =============================================================================
# File: pipeline.py
# Module/Service: Pipeline Worker — Document Parsing & Cleaning ([AI])
# Layer: Service
# Purpose: Public OCR entry point — parse, clean, and segment documents.
# Responsibilities:
#   - Dispatch by FileType to format parsers; merge tables; strip chrome
#   - Convert blocks → OcrSegment; optional image OCR + language annotation
# Dependencies:
#   - app.core.config.get_settings; app.ai.ocr parsers / cleaning / tables /
#     headers_footers / image / language
# Public Exports:
#   - run_ocr_cleaning, _blocks_to_segments
# Database/Table: N/A
# Related Modules: app.ai.ocr.*, app.services.document_understanding
# Important Notes: No LLM. Image OCR only when ENABLE_IMAGE_OCR=true.
# =============================================================================

from __future__ import annotations

from typing import Iterator

from app.models.enums import FileType

from .cleaning import _clean_text, _infer_block_type, _split_paragraphs
from .docx_parser import _parse_docx
from .headers_footers import _strip_repeated_headers_footers
from .models import EmptyOcrError, OcrResult, OcrSegment, _ParsedBlock
from .paragraphs import _join_soft_lines
from .pdf import _parse_pdf
from .pptx_parser import _parse_pptx
from .tables import _count_unmerged_table_candidates, _merge_cross_page_tables
from .txt_parser import _parse_txt
from .xlsx_parser import _parse_xlsx


def run_ocr_cleaning(*, file_type: FileType, data: bytes) -> OcrResult:
    """Parse and clean a document into normalized OCR segments.

    Args:
        file_type: Declared document type from ``documents.file_type``.
        data: Raw file bytes from object storage.

    Returns:
        ``OcrResult`` with segments, physical/logical ``page_count``, and
        aggregate ``char_count``. Use ``.metrics`` for pipeline observability.

    Raises:
        EmptyOcrError: No non-empty text after cleaning (and image OCR if tried).
        ValueError: Unsupported ``file_type`` or image-OCR misconfiguration.
        Exception: Propagated from format parsers (corrupt files).
    """
    from app.core.config import get_settings

    settings = get_settings()
    unmerged_table_candidates = 0
    used_image_ocr = False

    if file_type == FileType.pdf:
        blocks, page_count = _parse_pdf(data)
        unmerged_table_candidates = _count_unmerged_table_candidates(blocks)
        blocks = _merge_cross_page_tables(blocks)
    elif file_type == FileType.docx:
        blocks, page_count = _parse_docx(data)
    elif file_type == FileType.xlsx:
        blocks, page_count = _parse_xlsx(data)
    elif file_type == FileType.pptx:
        blocks, page_count = _parse_pptx(data)
    elif file_type == FileType.txt:
        blocks, page_count = _parse_txt(data)
    else:
        raise ValueError(f"Unsupported file_type: {file_type}")

    stripped = _strip_repeated_headers_footers(blocks)
    segments = list(_blocks_to_segments(stripped))
    char_count = sum(len(s.text) for s in segments)

    if (not segments or char_count == 0) and file_type == FileType.pdf and settings.enable_image_ocr:
        from .image import parse_pdf_via_image_ocr

        image_blocks, page_count = parse_pdf_via_image_ocr(
            data,
            settings=settings,
            parsed_block_cls=_ParsedBlock,
        )
        used_image_ocr = True
        stripped = _strip_repeated_headers_footers(image_blocks)
        segments = list(_blocks_to_segments(stripped))
        char_count = sum(len(s.text) for s in segments)

    if not segments or char_count == 0:
        if file_type == FileType.pdf and not settings.enable_image_ocr:
            raise EmptyOcrError(
                "No extractable text after OCR/cleaning. If this is a scanned PDF, "
                "it has no text layer — image OCR is disabled (ENABLE_IMAGE_OCR=false). "
                "Enable ENABLE_IMAGE_OCR and install Tesseract, or re-upload a PDF "
                "with an embedded text layer."
            )
        if used_image_ocr:
            raise EmptyOcrError(
                "No extractable text after image OCR (ENABLE_IMAGE_OCR=true). "
                "Tesseract returned empty text for all pages — check DPI/lang "
                "settings or document quality."
            )
        raise EmptyOcrError(
            "No extractable text after OCR/cleaning. If this is a scanned PDF, "
            "it has no text layer — image OCR is not enabled in this stage. "
            "Re-upload a text-based document or a PDF with an embedded text layer."
        )

    from .language import annotate_segment_languages

    segments = annotate_segment_languages(segments, settings=settings)
    char_count = sum(len(s.text) for s in segments)

    return OcrResult(
        segments=segments,
        page_count=page_count,
        char_count=char_count,
        unmerged_table_candidates=unmerged_table_candidates,
        used_image_ocr=used_image_ocr,
    )


def _blocks_to_segments(blocks: list[_ParsedBlock]) -> Iterator[OcrSegment]:
    """Clean blocks and assign stable ``order_index`` values."""
    order = 0
    for block in blocks:
        cleaned = _clean_text(block.text)
        if not cleaned:
            continue
        # Tables / headings already emitted as semantic units — keep structure.
        if block.block_type in {"table", "heading", "title", "subtitle", "notes", "caption"}:
            yield OcrSegment(
                text=cleaned,
                order_index=order,
                page_number=block.page_number,
                section=block.section,
                heading_level=block.heading_level,
                block_type=block.block_type,
                bbox=block.bbox,
                font_size=block.font_size,
                font_name=block.font_name,
                is_bold=block.is_bold,
                section_index=block.section_index,
            )
            order += 1
            continue

        # Soft wraps → spaces; blank lines remain hard paragraph breaks.
        cleaned = _join_soft_lines(cleaned.split("\n"))
        for para in _split_paragraphs(cleaned):
            yield OcrSegment(
                text=para,
                order_index=order,
                page_number=block.page_number,
                section=block.section,
                heading_level=block.heading_level,
                block_type=block.block_type or _infer_block_type(para),
                bbox=block.bbox,
                font_size=block.font_size,
                font_name=block.font_name,
                is_bold=block.is_bold,
                section_index=block.section_index,
            )
            order += 1
