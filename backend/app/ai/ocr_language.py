# =============================================================================
# File: ocr_language.py
# Module/Service: Pipeline Worker — Document Parsing & Cleaning ([AI])
# Layer: Service
# Purpose: Compatibility shim — re-exports language helpers from app.ai.ocr.
# Responsibilities:
#   - Preserve import path app.ai.ocr_language for existing callers/tests
# Dependencies:
#   - app.ai.ocr.language
# Public Exports:
#   - annotate_segment_languages
# Database/Table: N/A
# Related Modules: app.ai.ocr.language
# Important Notes: Thin re-export only; implementation lives in app.ai.ocr.language.
# =============================================================================

from app.ai.ocr.language import annotate_segment_languages

__all__ = ["annotate_segment_languages"]
