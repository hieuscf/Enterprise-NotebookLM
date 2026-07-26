# =============================================================================
# File: ocr.py
# Module/Service: Pipeline Worker — OCR & Cleaning ([AI])
# Layer: Service
# Purpose: Multi-format OCR/parse + cleaning into normalized segments (FR2 Step 3).
# Responsibilities:
#   - PDF/DOCX/XLSX/PPTX/TXT → segments {text, page_number, section, order_index}
#   - Clean whitespace/encoding; strip simple repeated headers/footers
# Dependencies:
#   - PyMuPDF, python-docx, openpyxl, python-pptx (stdlib cleaning only)
# Public Exports:
#   - OcrSegment, CleanedPage, OcrResult, run_ocr_cleaning, EmptyOcrError
# Database/Table: N/A (page_count updated by stage via document_versions)
# Related Modules: app.workers.stages.ocr_cleaning, app.ai.chunking
# Important Notes: No image OCR; empty text layer → EmptyOcrError (fail stage).
# =============================================================================

from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass

from app.models.enums import FileType


class EmptyOcrError(ValueError):
    """Raised when a file yields no extractable text after cleaning.

    Typical cause: scanned PDF without a text layer (image OCR is out of scope
    for this stage).
    """


@dataclass(frozen=True, slots=True)
class OcrSegment:
    """Normalized text unit shared by all input formats.

    Attributes:
        text: Cleaned segment body.
        order_index: Zero-based reading order across the document.
        page_number: Page/sheet/slide number when applicable.
        section: Heading or sheet title when available.
    """

    text: str
    order_index: int
    page_number: int | None = None
    section: str | None = None


@dataclass(frozen=True, slots=True)
class CleanedPage:
    """Legacy page view for structure-aware chunking (derived from segments)."""

    page_number: int
    text: str
    section: str | None = None


@dataclass(frozen=True, slots=True)
class OcrResult:
    """OCR/cleaning output for one document version."""

    segments: list[OcrSegment]
    page_count: int
    char_count: int

    @property
    def pages(self) -> list[CleanedPage]:
        """Adapt segments to ``CleanedPage`` for the chunking module."""
        pages: list[CleanedPage] = []
        for seg in self.segments:
            pages.append(
                CleanedPage(
                    page_number=(
                        seg.page_number if seg.page_number is not None else seg.order_index + 1
                    ),
                    text=seg.text,
                    section=seg.section,
                )
            )
        return pages


_WS_RE = re.compile(r"[ \t]+")
_BLANK_RE = re.compile(r"\n{3,}")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def run_ocr_cleaning(*, file_type: FileType, data: bytes) -> OcrResult:
    """Parse and clean a document into normalized OCR segments.

    Args:
        file_type: Declared document type from ``documents.file_type``.
        data: Raw file bytes from object storage.

    Returns:
        ``OcrResult`` with segments, physical/logical ``page_count``, and
        aggregate ``char_count``.

    Raises:
        EmptyOcrError: No non-empty text after cleaning.
        ValueError: Unsupported ``file_type``.
        Exception: Propagated from format parsers (corrupt files).
    """
    if file_type == FileType.pdf:
        raw_pages, page_count = _parse_pdf(data)
    elif file_type == FileType.docx:
        raw_pages, page_count = _parse_docx(data)
    elif file_type == FileType.xlsx:
        raw_pages, page_count = _parse_xlsx(data)
    elif file_type == FileType.pptx:
        raw_pages, page_count = _parse_pptx(data)
    elif file_type == FileType.txt:
        raw_pages, page_count = _parse_txt(data)
    else:
        raise ValueError(f"Unsupported file_type: {file_type}")

    stripped = _strip_repeated_headers_footers(raw_pages)
    segments: list[OcrSegment] = []
    order = 0
    for page_number, section, body in stripped:
        for para in _split_paragraphs(body):
            cleaned = _clean_text(para)
            if not cleaned:
                continue
            segments.append(
                OcrSegment(
                    text=cleaned,
                    order_index=order,
                    page_number=page_number,
                    section=section,
                )
            )
            order += 1

    char_count = sum(len(s.text) for s in segments)
    if not segments or char_count == 0:
        raise EmptyOcrError(
            "No extractable text after OCR/cleaning. If this is a scanned PDF, "
            "it has no text layer — image OCR is not enabled in this stage. "
            "Re-upload a text-based document or a PDF with an embedded text layer."
        )

    return OcrResult(segments=segments, page_count=page_count, char_count=char_count)


def _clean_text(text: str) -> str:
    """Normalize encoding artefacts and collapse excess whitespace."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\ufeff", "").replace("\u00a0", " ")
    text = _CTRL_RE.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WS_RE.sub(" ", text)
    text = _BLANK_RE.sub("\n\n", text)
    return text.strip()


def _split_paragraphs(text: str) -> list[str]:
    """Split a block into paragraph-sized pieces."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []
    parts = re.split(r"\n\s*\n+", text)
    return [p.strip() for p in parts if p.strip()]


# ---------------------------------------------------------------------------
# Format parsers → list of (page_number | None, section | None, raw_text)
# ---------------------------------------------------------------------------

RawBlock = tuple[int | None, str | None, str]


def _parse_pdf(data: bytes) -> tuple[list[RawBlock], int]:
    """Extract text per PDF page (PyMuPDF); keep physical page numbers."""
    import fitz  # PyMuPDF

    doc = fitz.open(stream=data, filetype="pdf")
    try:
        blocks: list[RawBlock] = []
        for i, page in enumerate(doc, start=1):
            blocks.append((i, None, page.get_text("text") or ""))
        return blocks, len(doc)
    finally:
        doc.close()


def _parse_docx(data: bytes) -> tuple[list[RawBlock], int]:
    """Extract DOCX paragraphs; track heading styles as ``section``."""
    from docx import Document

    document = Document(io.BytesIO(data))
    blocks: list[RawBlock] = []
    current_section: str | None = None
    logical_page = 1

    for para in document.paragraphs:
        style_name = (para.style.name or "").lower() if para.style else ""
        text = para.text or ""
        if not text.strip():
            continue
        if "heading" in style_name:
            current_section = text.strip()
            blocks.append((logical_page, current_section, text))
            logical_page += 1
        else:
            blocks.append((logical_page, current_section, text))

    page_count = max((b[0] or 1 for b in blocks), default=0)
    return blocks, page_count


def _parse_xlsx(data: bytes) -> tuple[list[RawBlock], int]:
    """Extract XLSX rows per sheet; ``section`` = sheet title."""
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    blocks: list[RawBlock] = []
    try:
        for idx, sheet in enumerate(wb.worksheets, start=1):
            lines: list[str] = []
            for row in sheet.iter_rows(values_only=True):
                cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
                if cells:
                    lines.append(" | ".join(cells))
            blocks.append((idx, sheet.title, "\n".join(lines)))
        return blocks, len(wb.worksheets)
    finally:
        wb.close()


def _parse_pptx(data: bytes) -> tuple[list[RawBlock], int]:
    """Extract PPTX text per slide; ``page_number`` = slide index."""
    from pptx import Presentation

    prs = Presentation(io.BytesIO(data))
    blocks: list[RawBlock] = []
    for idx, slide in enumerate(prs.slides, start=1):
        texts: list[str] = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text:
                texts.append(shape.text)
        blocks.append((idx, f"Slide {idx}", "\n".join(texts)))
    return blocks, len(blocks)


def _parse_txt(data: bytes) -> tuple[list[RawBlock], int]:
    """Decode TXT and keep paragraph structure (no synthetic page split)."""
    text = data.decode("utf-8", errors="replace")
    paragraphs = _split_paragraphs(text)
    if not paragraphs:
        return [(1, None, "")], 0
    blocks: list[RawBlock] = [(1, None, p) for p in paragraphs]
    return blocks, 1


# ---------------------------------------------------------------------------
# Simple repeated header/footer stripping (multi-page only)
# ---------------------------------------------------------------------------


def _strip_repeated_headers_footers(blocks: list[RawBlock]) -> list[RawBlock]:
    """Remove lines that repeat as header/footer across most pages.

    Heuristic only: requires ≥3 pages with line-oriented text. Safe no-op for
    DOCX/TXT single-flow content.
    """
    by_page: dict[int, list[str]] = {}
    for page_number, _section, body in blocks:
        if page_number is None:
            continue
        lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
        if lines:
            by_page.setdefault(page_number, [])
            # Keep first occurrence text for voting; merge later via rebuild.
            if page_number not in by_page or not by_page[page_number]:
                by_page[page_number] = lines

    # Rebuild page map from original blocks (concatenate same page).
    page_texts: dict[int, str] = {}
    page_section: dict[int, str | None] = {}
    order_pages: list[int] = []
    for page_number, section, body in blocks:
        if page_number is None:
            continue
        if page_number not in page_texts:
            order_pages.append(page_number)
            page_texts[page_number] = body
            page_section[page_number] = section
        else:
            page_texts[page_number] = page_texts[page_number] + "\n" + body

    if len(order_pages) < 3:
        return blocks

    headers: list[str] = []
    footers: list[str] = []
    for pn in order_pages:
        lines = [ln.strip() for ln in page_texts[pn].splitlines() if ln.strip()]
        if not lines:
            continue
        headers.append(lines[0])
        footers.append(lines[-1])

    drop_header = _majority_line(headers, threshold=0.6)
    drop_footer = _majority_line(footers, threshold=0.6)
    if drop_header is None and drop_footer is None:
        return blocks

    cleaned: list[RawBlock] = []
    for pn in order_pages:
        lines = [ln for ln in page_texts[pn].splitlines()]
        stripped: list[str] = []
        for i, ln in enumerate(lines):
            candidate = ln.strip()
            if i == 0 and drop_header and candidate == drop_header:
                continue
            if i == len(lines) - 1 and drop_footer and candidate == drop_footer:
                continue
            stripped.append(ln)
        cleaned.append((pn, page_section.get(pn), "\n".join(stripped)))
    return cleaned


def _majority_line(lines: list[str], *, threshold: float) -> str | None:
    """Return a line present on ≥ threshold fraction of pages (len ≥ 4)."""
    if not lines:
        return None
    counts: dict[str, int] = {}
    for line in lines:
        if len(line) < 4 or len(line) > 120:
            continue
        counts[line] = counts.get(line, 0) + 1
    if not counts:
        return None
    best, count = max(counts.items(), key=lambda kv: kv[1])
    if count / len(lines) >= threshold:
        return best
    return None
