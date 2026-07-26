# =============================================================================
# File: chunking.py
# Module/Service: Pipeline Worker — stage_chunking ([BE] stub / [AI] later)
# Layer: Worker
# Purpose: Chunking stage stub for pipeline orchestration (FR2 Step 2).
# Responsibilities:
#   - Accept document_version_id; return metadata (fake chunk_count=1)
# Dependencies:
#   - N/A (Step 2 stub — real structure-aware chunking in later AI steps)
# Public Exports:
#   - stage_chunking
# Database/Table: document_chunks (written in real impl later)
# Related Modules: app.workers.pipeline, app.ai.chunking (future)
# Important Notes: Replace body later; keep signature stable.
# =============================================================================

from __future__ import annotations

from typing import Any
from uuid import UUID


def stage_chunking(document_version_id: UUID) -> dict[str, Any]:
    """Chunk cleaned text for a document version (stub).

    Args:
        document_version_id: Target ``document_versions.id``.

    Returns:
        Metadata written to ``pipeline_stage_logs.metadata``.
    """
    return {
        "stub": True,
        "document_version_id": str(document_version_id),
        "chunk_count": 1,
    }
