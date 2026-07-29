# =============================================================================
# File: __init__.py
# Module/Service: Pipeline Worker — Stages
# Layer: Worker
# Purpose: Pluggable stage handlers for document ingestion pipeline (FR2 Step 2).
# Responsibilities:
#   - Export ordered STAGE_ORDER and STAGE_HANDLERS registry
#   - Each handler: (document_version_id) -> metadata dict for pipeline_stage_logs
# Dependencies:
#   - app.workers.stages.* handler modules
# Public Exports:
#   - STAGE_ORDER, STAGE_HANDLERS, StageHandler
#   - TransientPipelineError, DataPipelineError
# Database/Table: N/A (handlers may write via their own sessions later)
# Related Modules: app.workers.pipeline
# Important Notes:
#   - All five stages are real (Parse→Chunk→Embed→Graph→ES BM25).
#   - `cleaning_normalize` exists in the enum but is not in STAGE_ORDER yet.
# =============================================================================

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from app.models.enums import PipelineStage
from app.workers.stages.chunking import stage_chunking
from app.workers.stages.document_understanding import stage_document_understanding
from app.workers.stages.embedding import stage_embedding
from app.workers.stages.errors import DataPipelineError, TransientPipelineError
from app.workers.stages.graph_extraction import stage_graph_extraction
from app.workers.stages.indexing import stage_indexing

StageHandler = Callable[[UUID], dict[str, Any]]

STAGE_ORDER: tuple[PipelineStage, ...] = (
    PipelineStage.document_understanding,
    PipelineStage.hierarchical_chunking,
    PipelineStage.embedding,
    PipelineStage.graph_extraction,
    PipelineStage.indexing,
)

STAGE_HANDLERS: dict[PipelineStage, StageHandler] = {
    # v3 Document Understanding — parser selected via DOCUMENT_PARSER (llamaparse | local).
    PipelineStage.document_understanding: stage_document_understanding,
    # Still the v2 interim chunker — reads the ocr_segments.json artifact that
    # document_understanding keeps emitting until Hierarchical Chunking lands.
    PipelineStage.hierarchical_chunking: stage_chunking,
    PipelineStage.embedding: stage_embedding,
    PipelineStage.graph_extraction: stage_graph_extraction,
    PipelineStage.indexing: stage_indexing,
}

__all__ = [
    "STAGE_HANDLERS",
    "STAGE_ORDER",
    "DataPipelineError",
    "StageHandler",
    "TransientPipelineError",
]
