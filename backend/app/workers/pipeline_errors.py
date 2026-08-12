# =============================================================================
# File: pipeline_errors.py
# Module/Service: Pipeline Worker
# Layer: Worker
# Purpose: Classify stage failures for Celery retry vs immediate fail (FR2).
# Responsibilities:
#   - TransientPipelineError → timeout/network → Celery autoretry
#   - DataPipelineError → corrupt/unreadable input → fail immediately
# Dependencies:
#   - N/A
# Public Exports:
#   - PipelineStageError, TransientPipelineError, DataPipelineError
# Database/Table: N/A
# Related Modules: app.workers.pipeline, app.workers.stages.*, app.services.*
# Important Notes: Only Transient* is listed in Celery autoretry_for.
# =============================================================================

from __future__ import annotations

from typing import Any


class PipelineStageError(Exception):
    """Base error raised by a pipeline stage handler."""


class TransientPipelineError(PipelineStageError):
    """Temporary infrastructure failure (timeout, network, broker).

    Celery may retry the whole ``run_pipeline`` task and bump
    ``pipeline_runs.retry_count``.
    """


class DataPipelineError(PipelineStageError):
    """Permanent data/content failure (corrupt file, unsupported/unreadable).

    Must fail the pipeline immediately — do not Celery-retry.

    Attributes:
        user_message: Safe string for ``pipeline_runs`` / stage ``error_message``
            shown to workspace users (never LlamaParse internals).
        diagnostics: Structured details for ``pipeline_stage_logs.metadata``.
    """

    def __init__(
        self,
        message: str,
        *,
        user_message: str | None = None,
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.user_message = user_message or message
        self.diagnostics = diagnostics or {}
