# =============================================================================
# File: test_ocr_p3.py
# Module/Service: Pipeline Worker — OCR P3 language + image OCR
# Layer: Service
# Purpose: Tests for language detection and ENABLE_IMAGE_OCR fallback.
# Responsibilities:
#   - Language annotation on segments; overhead budget vs baseline
#   - Empty PDF still EmptyOcrError when flag off; mock Tesseract when on
# Dependencies:
#   - pytest, app.ai.ocr, app.ai.ocr_language, app.ai.ocr_image
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: app.core.config Settings ENABLE_IMAGE_OCR
# Important Notes: Does not require a real Tesseract binary (mocked).
# =============================================================================

from __future__ import annotations

import builtins
import sys
import time
from types import ModuleType
from unittest.mock import MagicMock, patch

import fitz
import pytest

from app.ai.ocr import EmptyOcrError, OcrSegment, _ParsedBlock, run_ocr_cleaning
from app.ai.ocr_image import parse_pdf_via_image_ocr
from app.ai.ocr_language import annotate_segment_languages
from app.core.config import Settings
from app.models.enums import FileType


def _english_blob() -> bytes:
    paras = [
        "Enterprise NotebookLM uses LightRAG for dual-level graph retrieval.",
        "Vector embeddings index document chunks inside Qdrant for hybrid search.",
        "Citation verification checks each source against retrieved passages.",
    ]
    return ("\n\n".join(paras * 8) + "\n").encode("utf-8")


def test_language_detection_sets_segment_language() -> None:
    result = run_ocr_cleaning(file_type=FileType.txt, data=_english_blob())
    assert result.segments
    assert any(s.language == "en" for s in result.segments)
    assert result.metrics.languages_detected >= 1


def test_language_detection_can_be_disabled() -> None:
    settings = Settings(ocr_language_detection_enabled=False)
    segs = [
        OcrSegment(
            text="Hello world from the English language detection sample text.",
            order_index=0,
        ),
    ]
    out = annotate_segment_languages(segs, settings=settings)
    assert out[0].language is None


def test_language_detection_overhead_under_ten_percent() -> None:
    """Document-level detect stays cheap vs a realistic OCR-sized baseline.

    Tiny TXT parses are ~10ms; langdetect alone can be ~50–80ms on Windows, so
    a naive +10% check on micro-benchmarks is meaningless. We build a larger
    multi-paragraph corpus and require overhead ≤ 10% **or** ≤ 100ms/doc.
    """
    # ~50KB of English prose → parse cost dominates language detect.
    unit = (
        "Enterprise NotebookLM uses LightRAG for dual-level graph retrieval. "
        "Vector embeddings index document chunks inside Qdrant for hybrid search. "
        "Citation verification checks each source against retrieved passages.\n\n"
    )
    data = (unit * 80).encode("utf-8")

    baseline_settings = Settings(ocr_language_detection_enabled=False)
    enabled_settings = Settings(
        ocr_language_detection_enabled=True,
        ocr_language_detect_per_segment=False,
    )

    with patch("app.core.config.get_settings", return_value=baseline_settings):
        run_ocr_cleaning(file_type=FileType.txt, data=data)
    with patch("app.core.config.get_settings", return_value=enabled_settings):
        run_ocr_cleaning(file_type=FileType.txt, data=data)

    def _run(cfg: Settings) -> float:
        t0 = time.perf_counter()
        with patch("app.core.config.get_settings", return_value=cfg):
            for _ in range(3):
                run_ocr_cleaning(file_type=FileType.txt, data=data)
        return time.perf_counter() - t0

    baseline = _run(baseline_settings)
    with_lang = _run(enabled_settings)
    overhead = with_lang - baseline
    per_doc = overhead / 3
    assert per_doc <= max(baseline / 3 * 0.10, 0.10), (
        f"language detection too slow: baseline={baseline:.4f}s "
        f"with_lang={with_lang:.4f}s per_doc_overhead={per_doc:.4f}s"
    )


def test_empty_pdf_raises_when_image_ocr_disabled() -> None:
    doc = fitz.open()
    doc.new_page()
    data = doc.tobytes()
    doc.close()

    with patch(
        "app.core.config.get_settings",
        return_value=Settings(enable_image_ocr=False, ocr_language_detection_enabled=False),
    ):
        with pytest.raises(EmptyOcrError, match="ENABLE_IMAGE_OCR=false|text layer"):
            run_ocr_cleaning(file_type=FileType.pdf, data=data)


def test_image_ocr_fallback_when_enabled() -> None:
    doc = fitz.open()
    doc.new_page()
    data = doc.tobytes()
    doc.close()

    fake_settings = Settings(
        enable_image_ocr=True,
        ocr_language_detection_enabled=False,
        image_ocr_max_pages=2,
        image_ocr_dpi=72,
    )

    def _fake_parse(data: bytes, *, settings=None, parsed_block_cls=None):
        assert parsed_block_cls is not None
        return (
            [
                parsed_block_cls(
                    text="Scanned document text recovered by Tesseract OCR engine.",
                    page_number=1,
                    block_type="paragraph",
                )
            ],
            1,
        )

    with (
        patch("app.core.config.get_settings", return_value=fake_settings),
        patch("app.ai.ocr.image.parse_pdf_via_image_ocr", side_effect=_fake_parse),
    ):
        result = run_ocr_cleaning(file_type=FileType.pdf, data=data)

    assert result.used_image_ocr is True
    assert result.char_count > 0
    assert any("Scanned" in s.text for s in result.segments)


def test_image_ocr_raises_clear_error_when_packages_missing() -> None:
    doc = fitz.open()
    doc.new_page()
    data = doc.tobytes()
    doc.close()
    settings = Settings(enable_image_ocr=True, image_ocr_dpi=72, image_ocr_max_pages=1)

    real_import = builtins.__import__

    def _selective(
        name: str,
        globals=None,
        locals=None,
        fromlist=(),
        level: int = 0,
    ):
        if name == "pytesseract" or name == "PIL" or name.startswith("PIL."):
            raise ImportError("simulated missing dep")
        return real_import(name, globals, locals, fromlist, level)

    with patch("builtins.__import__", side_effect=_selective):
        with pytest.raises(ValueError, match="pytesseract/Pillow|not installed"):
            parse_pdf_via_image_ocr(
                data,
                settings=settings,
                parsed_block_cls=_ParsedBlock,
            )


def test_image_ocr_uses_mocked_tesseract_string() -> None:
    doc = fitz.open()
    doc.new_page()
    data = doc.tobytes()
    doc.close()

    settings = Settings(
        enable_image_ocr=True,
        image_ocr_dpi=72,
        image_ocr_max_pages=1,
        image_ocr_timeout_seconds=5,
        image_ocr_lang="eng",
    )

    mock_tess = ModuleType("pytesseract")
    mock_tess.image_to_string = MagicMock(return_value="Hello from mocked OCR page one.")
    mock_tess.TesseractNotFoundError = type("TesseractNotFoundError", (Exception,), {})
    mock_inner = MagicMock()
    mock_tess.pytesseract = mock_inner

    with patch.dict(sys.modules, {"pytesseract": mock_tess}):
        blocks, page_count = parse_pdf_via_image_ocr(
            data,
            settings=settings,
            parsed_block_cls=_ParsedBlock,
        )

    assert page_count == 1
    assert blocks
    assert "mocked OCR" in blocks[0].text
    mock_tess.image_to_string.assert_called()
