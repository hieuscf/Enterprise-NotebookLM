# =============================================================================
# File: __init__.py
# Module/Service: Pipeline Worker — Document Parsing & Cleaning ([AI])
# Layer: Service
# Purpose: Public package surface for multi-format OCR parse + cleaning.
# Responsibilities:
#   - Re-export public API and test-needed private helpers
# Dependencies:
#   - app.ai.ocr.models, pipeline, tables, headers_footers, pdf, constants
# Public Exports:
#   - EmptyOcrError, OcrSegment, CleanedPage, OcrResult, OcrMetrics,
#     run_ocr_cleaning, _ParsedBlock, _merge_cross_page_tables,
#     _format_table_semantic, _strip_repeated_headers_footers,
#     _is_protected_content_line, _is_boilerplate_line, _median,
#     MEDIAN_SAMPLE_MAX, _count_unmerged_table_candidates
# Database/Table: N/A
# Related Modules: app.ai.ocr.*, app.workers.stages.ocr_cleaning, app.ai.chunking
# Important Notes: Replaces former monolithic app.ai.ocr module.
# =============================================================================

from __future__ import annotations

from .constants import MEDIAN_SAMPLE_MAX
from .headers_footers import (
    _is_boilerplate_line,
    _is_protected_content_line,
    _strip_repeated_headers_footers,
)
from .models import (
    CleanedPage,
    EmptyOcrError,
    OcrMetrics,
    OcrResult,
    OcrSegment,
    _ParsedBlock,
)
from .pdf import _median
from .pipeline import run_ocr_cleaning
from .tables import (
    _count_unmerged_table_candidates,
    _format_table_semantic,
    _merge_cross_page_tables,
)

__all__ = [
    "EmptyOcrError",
    "OcrSegment",
    "CleanedPage",
    "OcrResult",
    "OcrMetrics",
    "run_ocr_cleaning",
    "_ParsedBlock",
    "_merge_cross_page_tables",
    "_format_table_semantic",
    "_strip_repeated_headers_footers",
    "_is_protected_content_line",
    "_is_boilerplate_line",
    "_median",
    "MEDIAN_SAMPLE_MAX",
    "_count_unmerged_table_candidates",
]
