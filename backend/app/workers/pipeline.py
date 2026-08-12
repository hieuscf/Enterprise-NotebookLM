# =============================================================================
# File: pipeline.py
# Module/Service: Pipeline Worker
# Layer: Worker
# Purpose: Celery orchestration for 6 ingestion stages (FR2 Step 2).
# Responsibilities:
#   - run_pipeline: mark running → sequential stages → completed/failed
#   - Per-stage pipeline_stage_logs (running → completed/failed + duration_ms)
#   - Transient errors → Celery autoretry + retry_count; data errors → fail now
# Dependencies:
#   - Celery, app.workers.stages.*, app.repositories.pipeline_sync
# Public Exports:
#   - run_pipeline, execute_pipeline, process_document_pipeline
# Database/Table: pipeline_runs, pipeline_stage_logs, document_versions
# Related Modules: Document Ingestion Service, app.workers.stages
# Important Notes:
#   - Stage bodies live in app.workers.stages.* (Steps 3–6).
#   - After stage_indexing succeeds, this module sets pipeline_runs=completed
#     and document_versions=ready.
# =============================================================================

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.sync_session import get_sync_session
from app.models.enums import DocumentVersionStatus, PipelineStage, PipelineStatus
from app.repositories.pipeline_sync import PipelineSyncRepository
from app.workers.celery_app import celery_app
from app.workers.stages import STAGE_HANDLERS, STAGE_ORDER, StageHandler
from app.workers.stages.errors import DataPipelineError, TransientPipelineError

logger = get_logger(__name__)

SessionFactory = Callable[[], AbstractContextManager[Session]]


@celery_app.task(
    name="run_pipeline",
    bind=True,
    autoretry_for=(TransientPipelineError,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
    max_retries=3,
)
def run_pipeline(self, pipeline_run_id: str) -> dict[str, Any]:
    """Celery entrypoint enqueued by Document Ingestion Service.

    Transient failures are retried by Celery; data failures fail immediately.
    """
    run_id = uuid.UUID(pipeline_run_id)
    try:
        return execute_pipeline(run_id)
    except TransientPipelineError as exc:
        _bump_retry_count(run_id)
        # After final retry Celery will not re-queue — mark terminal failure.
        if self.request.retries >= (self.max_retries or 0):
            _mark_terminal_failure(run_id, str(exc))
        raise
    except DataPipelineError:
        # execute_pipeline already persisted failed status.
        raise
    except Exception as exc:
        # Unexpected errors: treat as terminal data-like failure (no retry).
        logger.exception("pipeline_unexpected_error", pipeline_run_id=pipeline_run_id)
        _mark_terminal_failure(run_id, str(exc))
        raise


# Backward-compatible alias.
process_document_pipeline = run_pipeline


def execute_pipeline(
    pipeline_run_id: uuid.UUID,
    *,
    stage_handlers: Mapping[PipelineStage, StageHandler] | None = None,
    session_factory: SessionFactory = get_sync_session,
) -> dict[str, Any]:
    """Run the 6-stage ingestion pipeline synchronously (orchestration only).

    Args:
        pipeline_run_id: ``pipeline_runs.id`` created at upload time.
        stage_handlers: Optional override map (tests / Step 3–6 swaps).
        session_factory: Sync DB session context manager.

    Returns:
        Summary dict with final status and completed stage names.

    Raises:
        TransientPipelineError: Stage asked for Celery retry (run not terminal).
        DataPipelineError: Permanent failure; run + version marked ``failed``.
        ValueError: Missing pipeline_run / document_version rows.
    """
    handlers = dict(stage_handlers or STAGE_HANDLERS)
    completed_stages: list[str] = []

    with session_factory() as session:
        pipe = PipelineSyncRepository(session)
        run = pipe.get_run(pipeline_run_id)
        if run is None:
            raise ValueError(f"pipeline_run not found: {pipeline_run_id}")

        version = pipe.get_version(run.document_version_id)
        if version is None:
            raise ValueError(f"document_version not found: {run.document_version_id}")

        document_version_id = version.id
        pipe.mark_run_running(run)
        # Keep version in processing while stages run.
        pipe.set_version_status(version, DocumentVersionStatus.processing)
        session.flush()

        try:
            for stage in STAGE_ORDER:
                handler = handlers.get(stage)
                if handler is None:
                    raise DataPipelineError(f"No handler registered for stage '{stage.value}'")

                log = pipe.start_stage(run.id, stage)
                session.flush()
                try:
                    metadata = handler(document_version_id)
                    if not isinstance(metadata, dict):
                        raise DataPipelineError(
                            f"Stage '{stage.value}' must return a metadata dict"
                        )
                    pipe.complete_stage(log, metadata=metadata)
                    if stage == PipelineStage.document_understanding:
                        page_count = metadata.get("page_count")
                        if isinstance(page_count, int):
                            pipe.set_version_status(
                                version,
                                DocumentVersionStatus.processing,
                                page_count=page_count,
                            )
                    completed_stages.append(stage.value)
                    session.flush()
                except TransientPipelineError as exc:
                    pipe.fail_stage(log, str(exc))
                    session.commit()
                    raise
                except DataPipelineError as exc:
                    user_message = getattr(exc, "user_message", None) or str(exc)
                    diagnostics = getattr(exc, "diagnostics", None) or None
                    pipe.fail_stage(
                        log,
                        user_message,
                        metadata=diagnostics if diagnostics else None,
                    )
                    pipe.mark_run_failed(run, user_message)
                    pipe.set_version_status(version, DocumentVersionStatus.failed)
                    session.commit()
                    raise
                except Exception as exc:
                    # Unknown errors from a stage → permanent fail (no retry).
                    message = str(exc)
                    pipe.fail_stage(log, message)
                    pipe.mark_run_failed(run, message)
                    pipe.set_version_status(version, DocumentVersionStatus.failed)
                    session.commit()
                    raise DataPipelineError(message) from exc

            pipe.mark_run_completed(run)
            pipe.set_version_status(version, DocumentVersionStatus.ready)
            logger.info(
                "pipeline_completed",
                pipeline_run_id=str(run.id),
                document_version_id=str(document_version_id),
                stages=completed_stages,
            )
            return {
                "pipeline_run_id": str(run.id),
                "document_version_id": str(document_version_id),
                "status": PipelineStatus.completed.value,
                "stages": completed_stages,
            }
        except (TransientPipelineError, DataPipelineError, ValueError):
            raise
        except Exception as exc:
            pipe.mark_run_failed(run, str(exc))
            pipe.set_version_status(version, DocumentVersionStatus.failed)
            session.commit()
            raise


def _bump_retry_count(pipeline_run_id: uuid.UUID) -> None:
    with get_sync_session() as session:
        pipe = PipelineSyncRepository(session)
        run = pipe.get_run(pipeline_run_id)
        if run is not None:
            pipe.increment_retry_count(run)


def _mark_terminal_failure(pipeline_run_id: uuid.UUID, error_message: str) -> None:
    with get_sync_session() as session:
        pipe = PipelineSyncRepository(session)
        run = pipe.get_run(pipeline_run_id)
        if run is None:
            return
        if run.status != PipelineStatus.failed:
            pipe.mark_run_failed(run, error_message)
        version = pipe.get_version(run.document_version_id)
        if version is not None and version.status != DocumentVersionStatus.failed:
            pipe.set_version_status(version, DocumentVersionStatus.failed)
