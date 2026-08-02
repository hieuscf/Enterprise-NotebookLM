# =============================================================================
# File: test_preview_generator.py
# Module/Service: Preview Generator
# Layer: Tests
# Purpose: Unit tests for PDF identity + text-fallback preview rendering.
# =============================================================================

from __future__ import annotations

import fitz

from app.models.enums import FileType
from app.services.preview_generator import (
    PreviewGeneratorService,
    _render_text_pdf,
    _try_libreoffice_convert,
)


def test_render_text_pdf_produces_valid_pdf() -> None:
    data = _render_text_pdf(["Hello preview", "Page two content"])
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        assert doc.page_count == 2
        assert "Hello" in doc.load_page(0).get_text()
    finally:
        doc.close()


def test_pdf_identity_via_to_pdf_bytes() -> None:
    src = fitz.open()
    src.new_page()
    pdf_bytes = src.tobytes()
    src.close()

    service = PreviewGeneratorService(storage=None)  # type: ignore[arg-type]
    out, engine = service._to_pdf_bytes(
        pdf_bytes, file_type=FileType.pdf, filename="a.pdf"
    )
    assert engine == "identity"
    assert out == pdf_bytes


def test_txt_fallback_pdf() -> None:
    service = PreviewGeneratorService(storage=None)  # type: ignore[arg-type]
    out, engine = service._to_pdf_bytes(
        b"Line one\n\nLine two",
        file_type=FileType.txt,
        filename="note.txt",
    )
    assert engine == "text_fallback"
    doc = fitz.open(stream=out, filetype="pdf")
    try:
        assert doc.page_count >= 1
        assert "Line one" in doc.load_page(0).get_text()
    finally:
        doc.close()


def test_libreoffice_returns_none_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.preview_generator._find_soffice",
        lambda: None,
    )
    assert _try_libreoffice_convert(b"x", suffix=".docx") is None
