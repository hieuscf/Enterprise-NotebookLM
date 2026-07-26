# =============================================================================
# File: __init__.py
# Module/Service: Pipeline Worker — Stages
# Layer: Worker
# Purpose: Pluggable stage handlers for document ingestion pipeline (FR2 Step 2).
# Responsibilities:
#   - Export ordered STAGE_ORDER and STAGE_HANDLERS registry
#   - Each handler: (document_version_id) -> metadata dict for pipeline_stage_logs
# Dependencies:
#   - app.workers.stages.* stub modules (real AI wired in Steps 3–6)
# Public Exports:
#   - STAGE_ORDER, STAGE_HANDLERS, StageHandler
#   - TransientPipelineError, DataPipelineError
# Database/Table: N/A (handlers may write via their own sessions later)
# Related Modules: app.workers.pipeline
# Important Notes: OCR/Chunking/Embedding are real (Steps 3–4); graph/index stubs remain.
# =============================================================================

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from app.models.enums import PipelineStage
from app.workers.stages.chunking import stage_chunking
from app.workers.stages.embedding import stage_embedding
from app.workers.stages.errors import DataPipelineError, TransientPipelineError
from app.workers.stages.graph_extraction import stage_graph_extraction
from app.workers.stages.indexing import stage_indexing
from app.workers.stages.ocr_cleaning import stage_ocr_cleaning

StageHandler = Callable[[UUID], dict[str, Any]]

STAGE_ORDER: tuple[PipelineStage, ...] = (
    PipelineStage.ocr_cleaning,
    PipelineStage.chunking,
    PipelineStage.embedding,
    PipelineStage.graph_extraction,
    PipelineStage.indexing,
)

STAGE_HANDLERS: dict[PipelineStage, StageHandler] = {
    PipelineStage.ocr_cleaning: stage_ocr_cleaning,
    PipelineStage.chunking: stage_chunking,
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
