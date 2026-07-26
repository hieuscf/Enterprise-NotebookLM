# =============================================================================
# File: pipeline_sync.py
# Module/Service: Pipeline Worker / Observability Module
# Layer: Repository
# Purpose: Sync updates for pipeline_runs and pipeline_stage_logs (FR2, FR13).
# Responsibilities:
#   - Mark run running/completed/failed; write per-stage status + duration_ms
# Dependencies:
#   - SQLAlchemy Session (sync), app.models.pipeline
# Public Exports:
#   - PipelineSyncRepository
# Database/Table: pipeline_runs, pipeline_stage_logs, document_versions
# Related Modules: app.workers.pipeline
# Important Notes: Stage enum fixed to five OCR→indexing stages.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.documents import DocumentVersion
from app.models.enums import DocumentVersionStatus, PipelineStage, PipelineStatus
from app.models.pipeline import PipelineRun, PipelineStageLog


class PipelineSyncRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_run(self, pipeline_run_id: uuid.UUID) -> PipelineRun | None:
        return self._session.get(PipelineRun, pipeline_run_id)

    def get_version(self, version_id: uuid.UUID) -> DocumentVersion | None:
        return self._session.get(DocumentVersion, version_id)

    def mark_run_running(self, run: PipelineRun) -> None:
        run.status = PipelineStatus.running
        run.started_at = datetime.now(UTC)
        run.error_message = None
        self._session.flush()

    def mark_run_completed(self, run: PipelineRun) -> None:
        run.status = PipelineStatus.completed
        run.completed_at = datetime.now(UTC)
        self._session.flush()

    def mark_run_failed(self, run: PipelineRun, error_message: str) -> None:
        run.status = PipelineStatus.failed
        run.error_message = error_message[:4000]
        run.completed_at = datetime.now(UTC)
        self._session.flush()

    def set_version_status(
        self,
        version: DocumentVersion,
        status: DocumentVersionStatus,
        *,
        page_count: int | None = None,
    ) -> None:
        version.status = status
        if page_count is not None:
            version.page_count = page_count
        self._session.flush()

    def start_stage(self, pipeline_run_id: uuid.UUID, stage: PipelineStage) -> PipelineStageLog:
        log = PipelineStageLog(
            pipeline_run_id=pipeline_run_id,
            stage=stage,
            status=PipelineStatus.running,
            started_at=datetime.now(UTC),
        )
        self._session.add(log)
        self._session.flush()
        return log

    def complete_stage(
        self,
        log: PipelineStageLog,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        now = datetime.now(UTC)
        log.status = PipelineStatus.completed
        log.completed_at = now
        if log.started_at is not None:
            log.duration_ms = int((now - log.started_at).total_seconds() * 1000)
        log.metadata_ = metadata
        self._session.flush()

    def fail_stage(self, log: PipelineStageLog, error_message: str) -> None:
        now = datetime.now(UTC)
        log.status = PipelineStatus.failed
        log.completed_at = now
        if log.started_at is not None:
            log.duration_ms = int((now - log.started_at).total_seconds() * 1000)
        log.error_message = error_message[:4000]
        self._session.flush()
