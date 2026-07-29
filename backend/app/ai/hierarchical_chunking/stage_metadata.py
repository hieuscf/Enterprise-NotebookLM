# =============================================================================
# File: stage_metadata.py
# Module/Service: Pipeline Worker — Hierarchical Chunking ([AI])
# Layer: Service
# Purpose: Build pipeline_stage_logs metadata for hierarchical_chunking.
# Responsibilities:
#   - Map ChunkingMetrics + timing into the observability contract
# Dependencies:
#   - app.ai.hierarchical_chunking.types.ChunkingMetrics
# Public Exports:
#   - build_stage_metadata
# Database/Table: pipeline_stage_logs.metadata
# Related Modules: app.services.hierarchical_chunking
# Important Notes: Keeps legacy keys so existing dashboards/tests stay valid.
# =============================================================================

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.ai.hierarchical_chunking.types import ChunkingMetrics


def build_stage_metadata(
    metrics: ChunkingMetrics,
    *,
    document_version_id: UUID,
    processing_time_ms: int,
) -> dict[str, Any]:
    """Return the metadata dict persisted by ``PipelineSyncRepository.complete_stage``."""
    payload = metrics.to_pipeline_log(processing_time_ms)
    payload["document_version_id"] = str(document_version_id)
    return payload
