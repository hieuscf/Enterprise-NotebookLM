# =============================================================================
# File: graph_extraction.py
# Module/Service: Pipeline Worker — stage_graph_extraction ([BE] stub / [AI])
# Layer: Worker
# Purpose: Graph extraction stage stub for pipeline orchestration (FR2 Step 2).
# Responsibilities:
#   - Accept document_version_id; return metadata for stage logs
# Dependencies:
#   - N/A (Step 2 stub — LightRAG entities/topics in later AI steps)
# Public Exports:
#   - stage_graph_extraction
# Database/Table: entities, entity_relations, topics (later)
# Related Modules: app.workers.pipeline, app.ai.graph_extraction (future)
# Important Notes: Replace body later; keep signature stable.
# =============================================================================

from __future__ import annotations

from typing import Any
from uuid import UUID


def stage_graph_extraction(document_version_id: UUID) -> dict[str, Any]:
    """Extract entities/topics for a document version (stub).

    Args:
        document_version_id: Target ``document_versions.id``.

    Returns:
        Metadata written to ``pipeline_stage_logs.metadata``.
    """
    return {
        "stub": True,
        "document_version_id": str(document_version_id),
        "entity_count": 0,
        "topic_count": 0,
    }
