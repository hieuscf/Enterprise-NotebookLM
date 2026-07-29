# =============================================================================
# File: errors.py
# Module/Service: Pipeline Worker — Stages
# Layer: Worker
# Purpose: Backward-compatible re-export of pipeline stage error types.
# Responsibilities:
#   - Re-export PipelineStageError, TransientPipelineError, DataPipelineError
# Dependencies:
#   - app.workers.pipeline_errors
# Public Exports:
#   - PipelineStageError, TransientPipelineError, DataPipelineError
# Database/Table: N/A
# Related Modules: app.workers.pipeline_errors
# Important Notes: Import from app.workers.pipeline_errors in new service code.
# =============================================================================

from app.workers.pipeline_errors import (
    DataPipelineError,
    PipelineStageError,
    TransientPipelineError,
)

__all__ = [
    "DataPipelineError",
    "PipelineStageError",
    "TransientPipelineError",
]
