# =============================================================================
# File: indexing.py
# Module/Service: Pipeline Worker — stage_indexing ([BE] stub)
# Layer: Worker
# Purpose: Indexing stage stub for pipeline orchestration (FR2 Step 2).
# Responsibilities:
#   - Accept document_version_id; return metadata for stage logs
# Dependencies:
#   - N/A (Step 2 stub — Elasticsearch BM25 + vector finalize later)
# Public Exports:
#   - stage_indexing
# Database/Table: N/A (ES/Qdrant written in real impl later)
# Related Modules: app.workers.pipeline, app.adapters.elasticsearch_bm25 (future)
# Important Notes: Replace body later; keep signature stable.
# =============================================================================

from __future__ import annotations

from typing import Any
from uuid import UUID


def stage_indexing(document_version_id: UUID) -> dict[str, Any]:
    """Index chunks for BM25 / vector retrieval (stub).

    Args:
        document_version_id: Target ``document_versions.id``.

    Returns:
        Metadata written to ``pipeline_stage_logs.metadata``.
    """
    return {
        "stub": True,
        "document_version_id": str(document_version_id),
        "bm25_indexed": 1,
    }
