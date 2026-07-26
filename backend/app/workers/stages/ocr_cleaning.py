# =============================================================================
# File: ocr_cleaning.py
# Module/Service: Pipeline Worker — stage_ocr_cleaning ([BE] stub / [AI] later)
# Layer: Worker
# Purpose: OCR & Cleaning stage stub for pipeline orchestration (FR2 Step 2).
# Responsibilities:
#   - Accept document_version_id; return metadata for pipeline_stage_logs
# Dependencies:
#   - N/A (Step 2 stub — real OCR in Step 3+)
# Public Exports:
#   - stage_ocr_cleaning
# Database/Table: N/A
# Related Modules: app.workers.pipeline, app.ai.ocr (future)
# Important Notes: Replace body in Step 3; keep signature stable.
# =============================================================================

from __future__ import annotations

from typing import Any
from uuid import UUID


def stage_ocr_cleaning(document_version_id: UUID) -> dict[str, Any]:
    """Run OCR & Cleaning for a document version (stub).

    Args:
        document_version_id: Target ``document_versions.id``.

    Returns:
        Metadata written to ``pipeline_stage_logs.metadata``.
    """
    return {
        "stub": True,
        "document_version_id": str(document_version_id),
        "page_count": 0,
        "char_count": 0,
    }
