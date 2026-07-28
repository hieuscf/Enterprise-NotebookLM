# =============================================================================
# File: ocr_image.py
# Module/Service: Pipeline Worker — Document Parsing & Cleaning ([AI])
# Layer: Service
# Purpose: Compatibility shim — re-exports image OCR helpers from app.ai.ocr.
# Responsibilities:
#   - Preserve import path app.ai.ocr_image for existing callers/tests
# Dependencies:
#   - app.ai.ocr.image
# Public Exports:
#   - parse_pdf_via_image_ocr, image_ocr_available, configure_tesseract
# Database/Table: N/A
# Related Modules: app.ai.ocr.image
# Important Notes: Thin re-export only; implementation lives in app.ai.ocr.image.
# =============================================================================

from app.ai.ocr.image import (
    configure_tesseract,
    image_ocr_available,
    parse_pdf_via_image_ocr,
)

__all__ = [
    "parse_pdf_via_image_ocr",
    "image_ocr_available",
    "configure_tesseract",
]
