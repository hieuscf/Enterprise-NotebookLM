# =============================================================================
# File: embedding.py
# Module/Service: Pipeline Worker — stage_embedding ([BE] stub / [AI] later)
# Layer: Worker
# Purpose: Embedding stage stub for pipeline orchestration (FR2 Step 2).
# Responsibilities:
#   - Accept document_version_id; return metadata for stage logs
# Dependencies:
#   - N/A (Step 2 stub — real embedding + Qdrant in later steps)
# Public Exports:
#   - stage_embedding
# Database/Table: embeddings (written in real impl later)
# Related Modules: app.workers.pipeline, app.ai.embedding (future)
# Important Notes: Replace body later; keep signature stable.
# =============================================================================

from __future__ import annotations

from typing import Any
from uuid import UUID


def stage_embedding(document_version_id: UUID) -> dict[str, Any]:
    """Embed document chunks for a version (stub).

    Args:
        document_version_id: Target ``document_versions.id``.

    Returns:
        Metadata written to ``pipeline_stage_logs.metadata``.
    """
    return {
        "stub": True,
        "document_version_id": str(document_version_id),
        "embedded_count": 1,
    }
