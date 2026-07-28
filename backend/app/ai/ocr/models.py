# =============================================================================
# File: models.py
# Module/Service: Pipeline Worker — Document Parsing & Cleaning ([AI])
# Layer: Service
# Purpose: Public OCR dataclasses / exceptions and internal parse-block helpers.
# Responsibilities:
#   - Define EmptyOcrError, OcrSegment, CleanedPage, OcrMetrics, OcrResult
#   - Define _ParsedBlock intermediate unit and field-replace helpers
# Dependencies:
#   - app.ai.ocr.constants.BlockType
# Public Exports:
#   - EmptyOcrError, OcrSegment, CleanedPage, OcrMetrics, OcrResult,
#     _ParsedBlock, _segment_display_locator, _replace_block
# Database/Table: N/A
# Related Modules: app.ai.ocr.*
# Important Notes: No LLM. Layout metadata fields are optional / backward-compat.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass

from .constants import BlockType


class EmptyOcrError(ValueError):
    """Raised when a file yields no extractable text after cleaning.

    Typical cause: scanned PDF without a text layer. When ``ENABLE_IMAGE_OCR``
    is false (default), image OCR is skipped and this error is raised. When
    enabled, image OCR is attempted first; this error means OCR also failed.
    """


@dataclass(frozen=True, slots=True)
class OcrSegment:
    """Normalized text unit shared by all input formats.

    Core fields are required by existing consumers. Layout metadata fields are
    optional and backward-compatible (default ``None``).

    Page vs section (Citation / FR5):
        * ``page_number`` — **physical** page/slide/sheet index when the format
          has one (PDF page, PPTX slide, XLSX sheet). ``None`` for DOCX/TXT
          because those formats have no reliable text-layer page break.
        * ``section_index`` — **logical** section counter (1-based), primarily
          for DOCX where headings define sections. Prefer this (+ ``section``)
          over inventing a fake ``page_number`` for DOCX citations.
    """

    text: str
    order_index: int
    page_number: int | None = None
    section: str | None = None
    heading_level: int | None = None
    block_type: BlockType | None = None
    bbox: tuple[float, float, float, float] | None = None
    language: str | None = None
    font_size: float | None = None
    font_name: str | None = None
    is_bold: bool | None = None
    section_index: int | None = None


@dataclass(frozen=True, slots=True)
class CleanedPage:
    """Legacy page view for structure-aware chunking (derived from segments)."""

    page_number: int
    text: str
    section: str | None = None


@dataclass(frozen=True, slots=True)
class OcrMetrics:
    """Pipeline observability counters (not persisted unless a stage chooses to)."""

    page_count: int
    char_count: int
    segment_count: int
    heading_count: int
    table_count: int
    unmerged_table_candidates: int = 0
    used_image_ocr: bool = False
    languages_detected: int = 0


@dataclass(frozen=True, slots=True)
class OcrResult:
    """OCR/cleaning output for one document version.

    ``page_count`` meaning by format:
        * PDF — physical page count
        * PPTX — slide count
        * XLSX — sheet count
        * DOCX — logical section count (``section_index`` max); not Word pages
        * TXT — ``1`` (single flow)
    """

    segments: list[OcrSegment]
    page_count: int
    char_count: int
    unmerged_table_candidates: int = 0
    used_image_ocr: bool = False

    @property
    def pages(self) -> list[CleanedPage]:
        """Adapt segments to ``CleanedPage`` for the chunking module.

        Locator priority: physical ``page_number`` → ``section_index`` →
        ``order_index + 1``. DOCX intentionally has no physical page.
        """
        return [
            CleanedPage(
                page_number=_segment_display_locator(seg),
                text=seg.text,
                section=seg.section,
            )
            for seg in self.segments
        ]

    @property
    def segment_count(self) -> int:
        return len(self.segments)

    @property
    def heading_count(self) -> int:
        return sum(
            1
            for s in self.segments
            if s.block_type == "heading" or (s.heading_level is not None and s.heading_level > 0)
        )

    @property
    def table_count(self) -> int:
        return sum(1 for s in self.segments if s.block_type == "table")

    @property
    def languages_detected(self) -> int:
        return sum(1 for s in self.segments if s.language)

    @property
    def metrics(self) -> OcrMetrics:
        return OcrMetrics(
            page_count=self.page_count,
            char_count=self.char_count,
            segment_count=self.segment_count,
            heading_count=self.heading_count,
            table_count=self.table_count,
            unmerged_table_candidates=self.unmerged_table_candidates,
            used_image_ocr=self.used_image_ocr,
            languages_detected=self.languages_detected,
        )


@dataclass(frozen=True, slots=True)
class _ParsedBlock:
    """Intermediate parse unit before final cleaning / indexing."""

    text: str
    page_number: int | None = None
    section: str | None = None
    heading_level: int | None = None
    block_type: BlockType = "paragraph"
    bbox: tuple[float, float, float, float] | None = None
    font_size: float | None = None
    font_name: str | None = None
    is_bold: bool | None = None
    section_index: int | None = None
    table_col_count: int | None = None


def _segment_display_locator(seg: OcrSegment) -> int:
    """Best-effort locator for legacy ``CleanedPage.page_number``."""
    if seg.page_number is not None:
        return seg.page_number
    if seg.section_index is not None:
        return seg.section_index
    return seg.order_index + 1


def _replace_block(block: _ParsedBlock, **changes: object) -> _ParsedBlock:
    """Return a copy of ``block`` with selected fields replaced."""
    return _ParsedBlock(
        text=str(changes["text"]) if "text" in changes else block.text,
        page_number=(
            changes["page_number"]  # type: ignore[assignment]
            if "page_number" in changes
            else block.page_number
        ),
        section=changes["section"] if "section" in changes else block.section,  # type: ignore[arg-type]
        heading_level=(
            changes["heading_level"]  # type: ignore[assignment]
            if "heading_level" in changes
            else block.heading_level
        ),
        block_type=(
            changes["block_type"]  # type: ignore[assignment]
            if "block_type" in changes
            else block.block_type
        ),
        bbox=changes["bbox"] if "bbox" in changes else block.bbox,  # type: ignore[arg-type]
        font_size=changes["font_size"] if "font_size" in changes else block.font_size,  # type: ignore[arg-type]
        font_name=changes["font_name"] if "font_name" in changes else block.font_name,  # type: ignore[arg-type]
        is_bold=changes["is_bold"] if "is_bold" in changes else block.is_bold,  # type: ignore[arg-type]
        section_index=(
            changes["section_index"]  # type: ignore[assignment]
            if "section_index" in changes
            else block.section_index
        ),
        table_col_count=(
            changes["table_col_count"]  # type: ignore[assignment]
            if "table_col_count" in changes
            else block.table_col_count
        ),
    )
