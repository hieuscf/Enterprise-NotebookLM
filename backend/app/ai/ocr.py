# =============================================================================
# File: ocr.py
# Module/Service: Pipeline Worker — OCR & Cleaning ([AI])
# Layer: Service
# Purpose: Parse PDF/DOCX/XLSX/PPTX/TXT into cleaned page/section text (FR2).
# Responsibilities:
#   - Extract text per page/sheet/slide; normalize whitespace
# Dependencies:
#   - PyMuPDF, python-docx, openpyxl, python-pptx
# Public Exports:
#   - CleanedPage, OcrResult, run_ocr_cleaning
# Database/Table: N/A (page_count written to document_versions by worker)
# Related Modules: app.workers.pipeline (stage_ocr_cleaning)
# Important Notes: No LLM; Unstructured.io-style multi-format via native libs.
# =============================================================================

from __future__ import annotations

import io
import re
from dataclasses import dataclass

from app.models.enums import FileType


@dataclass(frozen=True, slots=True)
class CleanedPage:
    page_number: int
    text: str
    section: str | None = None


@dataclass(frozen=True, slots=True)
class OcrResult:
    pages: list[CleanedPage]
    page_count: int
    char_count: int


_WS_RE = re.compile(r"[ \t]+")
_BLANK_RE = re.compile(r"\n{3,}")


def _clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WS_RE.sub(" ", text)
    text = _BLANK_RE.sub("\n\n", text)
    return text.strip()


def run_ocr_cleaning(*, file_type: FileType, data: bytes) -> OcrResult:
    if file_type == FileType.pdf:
        pages = _parse_pdf(data)
    elif file_type == FileType.docx:
        pages = _parse_docx(data)
    elif file_type == FileType.xlsx:
        pages = _parse_xlsx(data)
    elif file_type == FileType.pptx:
        pages = _parse_pptx(data)
    elif file_type == FileType.txt:
        pages = _parse_txt(data)
    else:
        raise ValueError(f"Unsupported file_type: {file_type}")

    cleaned = [
        CleanedPage(page_number=p.page_number, text=_clean_text(p.text), section=p.section)
        for p in pages
        if _clean_text(p.text)
    ]
    char_count = sum(len(p.text) for p in cleaned)
    return OcrResult(pages=cleaned, page_count=len(cleaned), char_count=char_count)


def _parse_pdf(data: bytes) -> list[CleanedPage]:
    import fitz  # PyMuPDF

    doc = fitz.open(stream=data, filetype="pdf")
    try:
        pages: list[CleanedPage] = []
        for i, page in enumerate(doc, start=1):
            pages.append(CleanedPage(page_number=i, text=page.get_text("text") or ""))
        return pages
    finally:
        doc.close()


def _parse_docx(data: bytes) -> list[CleanedPage]:
    from docx import Document

    document = Document(io.BytesIO(data))
    blocks: list[str] = []
    current_section: str | None = None
    pages: list[CleanedPage] = []
    page_no = 1

    for para in document.paragraphs:
        style_name = (para.style.name or "").lower() if para.style else ""
        text = para.text or ""
        if not text.strip():
            continue
        if "heading" in style_name:
            if blocks:
                pages.append(
                    CleanedPage(
                        page_number=page_no,
                        text="\n".join(blocks),
                        section=current_section,
                    )
                )
                page_no += 1
                blocks = []
            current_section = text.strip()
            blocks.append(text)
        else:
            blocks.append(text)

    if blocks:
        pages.append(
            CleanedPage(page_number=page_no, text="\n".join(blocks), section=current_section)
        )
    if not pages:
        pages = [CleanedPage(page_number=1, text="")]
    return pages


def _parse_xlsx(data: bytes) -> list[CleanedPage]:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    pages: list[CleanedPage] = []
    try:
        for idx, sheet in enumerate(wb.worksheets, start=1):
            lines: list[str] = []
            for row in sheet.iter_rows(values_only=True):
                cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
                if cells:
                    lines.append(" | ".join(cells))
            pages.append(
                CleanedPage(
                    page_number=idx,
                    text="\n".join(lines),
                    section=sheet.title,
                )
            )
    finally:
        wb.close()
    return pages


def _parse_pptx(data: bytes) -> list[CleanedPage]:
    from pptx import Presentation

    prs = Presentation(io.BytesIO(data))
    pages: list[CleanedPage] = []
    for idx, slide in enumerate(prs.slides, start=1):
        texts: list[str] = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text:
                texts.append(shape.text)
        pages.append(CleanedPage(page_number=idx, text="\n".join(texts)))
    return pages


def _parse_txt(data: bytes) -> list[CleanedPage]:
    text = data.decode("utf-8", errors="replace")
    # Split large plaintext into ~3k-char pages for stable page_number metadata.
    chunk_size = 3000
    pages: list[CleanedPage] = []
    if not text.strip():
        return [CleanedPage(page_number=1, text="")]
    for i in range(0, len(text), chunk_size):
        pages.append(CleanedPage(page_number=len(pages) + 1, text=text[i : i + chunk_size]))
    return pages
