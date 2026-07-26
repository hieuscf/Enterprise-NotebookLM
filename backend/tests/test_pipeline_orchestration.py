# =============================================================================
# File: test_pipeline_orchestration.py
# Module/Service: Pipeline Worker
# Layer: Worker
# Purpose: Unit tests for FR2 Step 2 pipeline orchestration skeleton.
# Responsibilities:
#   - Stub E2E: 5 stage logs completed, run completed, version ready
#   - Stage failure stops pipeline; later stages skipped; version failed
#   - Transient vs data error retry classification helpers
# Dependencies:
#   - pytest, in-memory fake PipelineSyncRepository store
# Public Exports:
#   - N/A
# Database/Table: N/A (fakes — no Postgres/Celery broker in CI)
# Related Modules: app.workers.pipeline, app.workers.stages
# Important Notes: Stage handlers are stubs/overrides; AI content is out of scope.
# =============================================================================

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.models.documents import DocumentVersion
from app.models.enums import DocumentVersionStatus, PipelineStage, PipelineStatus
from app.models.pipeline import PipelineRun, PipelineStageLog
from app.workers.pipeline import execute_pipeline
from app.workers.stages import STAGE_ORDER
from app.workers.stages.errors import DataPipelineError, TransientPipelineError


class _FakeStore:
    """Minimal sync store mimicking PipelineSyncRepository behaviour."""

    def __init__(self, run: PipelineRun, version: DocumentVersion) -> None:
        self.run = run
        self.version = version
        self.stage_logs: list[PipelineStageLog] = []
        self.committed = False

    def get_run(self, pipeline_run_id: uuid.UUID) -> PipelineRun | None:
        return self.run if self.run.id == pipeline_run_id else None

    def get_version(self, version_id: uuid.UUID) -> DocumentVersion | None:
        return self.version if self.version.id == version_id else None

    def mark_run_running(self, run: PipelineRun) -> None:
        run.status = PipelineStatus.running
        run.started_at = datetime.now(UTC)
        run.error_message = None

    def mark_run_completed(self, run: PipelineRun) -> None:
        run.status = PipelineStatus.completed
        run.completed_at = datetime.now(UTC)

    def mark_run_failed(self, run: PipelineRun, error_message: str) -> None:
        run.status = PipelineStatus.failed
        run.error_message = error_message[:4000]
        run.completed_at = datetime.now(UTC)

    def increment_retry_count(self, run: PipelineRun) -> int:
        run.retry_count = int(run.retry_count or 0) + 1
        return run.retry_count

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

    def start_stage(self, pipeline_run_id: uuid.UUID, stage: PipelineStage) -> PipelineStageLog:
        log = PipelineStageLog(
            id=uuid.uuid4(),
            pipeline_run_id=pipeline_run_id,
            stage=stage,
            status=PipelineStatus.running,
            started_at=datetime.now(UTC),
        )
        self.stage_logs.append(log)
        return log

    def complete_stage(
        self,
        log: PipelineStageLog,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        log.status = PipelineStatus.completed
        log.completed_at = datetime.now(UTC)
        log.duration_ms = 1
        log.metadata_ = metadata

    def fail_stage(self, log: PipelineStageLog, error_message: str) -> None:
        log.status = PipelineStatus.failed
        log.completed_at = datetime.now(UTC)
        log.duration_ms = 1
        log.error_message = error_message


def _make_run_and_version() -> tuple[PipelineRun, DocumentVersion]:
    version_id = uuid.uuid4()
    run = PipelineRun(
        id=uuid.uuid4(),
        document_version_id=version_id,
        status=PipelineStatus.pending,
        retry_count=0,
    )
    version = DocumentVersion(
        id=version_id,
        document_id=uuid.uuid4(),
        uploaded_by=uuid.uuid4(),
        version_number=1,
        storage_path="workspaces/x/documents/y/v1/a.txt",
        file_size_bytes=10,
        checksum_sha256="abc",
        page_count=None,
        status=DocumentVersionStatus.processing,
        is_current=True,
        created_at=datetime.now(UTC),
    )
    return run, version


def _session_factory_for(store: _FakeStore):
    @contextmanager
    def _factory():
        session = MagicMock()
        session.flush = MagicMock()
        session.commit = MagicMock(side_effect=lambda: setattr(store, "committed", True))

        # Patch PipelineSyncRepository construction inside execute_pipeline
        from app.workers import pipeline as pipeline_mod

        original = pipeline_mod.PipelineSyncRepository

        def _repo_factory(_session: Any) -> _FakeStore:
            return store

        pipeline_mod.PipelineSyncRepository = _repo_factory  # type: ignore[assignment]
        try:
            yield session
        finally:
            pipeline_mod.PipelineSyncRepository = original

    return _factory


def _stub_handlers() -> dict[PipelineStage, Any]:
    return {
        stage: (lambda _vid, s=stage: {"stub": True, "stage": s.value}) for stage in STAGE_ORDER
    }


def test_stub_pipeline_completes_all_five_stages() -> None:
    run, version = _make_run_and_version()
    store = _FakeStore(run, version)

    result = execute_pipeline(
        run.id,
        stage_handlers=_stub_handlers(),
        session_factory=_session_factory_for(store),
    )

    assert result["status"] == "completed"
    assert result["stages"] == [s.value for s in STAGE_ORDER]
    assert run.status == PipelineStatus.completed
    assert version.status == DocumentVersionStatus.ready
    assert len(store.stage_logs) == 5
    assert all(log.status == PipelineStatus.completed for log in store.stage_logs)
    assert [log.stage for log in store.stage_logs] == list(STAGE_ORDER)


def test_stage_failure_stops_pipeline_and_skips_later_stages() -> None:
    run, version = _make_run_and_version()
    store = _FakeStore(run, version)
    call_log: list[str] = []

    def _ok(vid: uuid.UUID, *, name: str) -> dict[str, Any]:
        call_log.append(name)
        return {"stub": True, "stage": name}

    def _boom(_vid: uuid.UUID) -> dict[str, Any]:
        call_log.append("embedding")
        raise DataPipelineError("simulated embedding failure")

    handlers = {
        PipelineStage.ocr_cleaning: lambda v: _ok(v, name="ocr_cleaning"),
        PipelineStage.chunking: lambda v: _ok(v, name="chunking"),
        PipelineStage.embedding: _boom,
        PipelineStage.graph_extraction: lambda v: _ok(v, name="graph_extraction"),
        PipelineStage.indexing: lambda v: _ok(v, name="indexing"),
    }

    with pytest.raises(DataPipelineError, match="simulated embedding failure"):
        execute_pipeline(
            run.id,
            stage_handlers=handlers,
            session_factory=_session_factory_for(store),
        )

    assert call_log == ["ocr_cleaning", "chunking", "embedding"]
    assert "graph_extraction" not in call_log
    assert "indexing" not in call_log
    assert run.status == PipelineStatus.failed
    assert version.status == DocumentVersionStatus.failed
    assert run.error_message == "simulated embedding failure"

    assert len(store.stage_logs) == 3
    assert store.stage_logs[0].status == PipelineStatus.completed
    assert store.stage_logs[1].status == PipelineStatus.completed
    assert store.stage_logs[2].stage == PipelineStage.embedding
    assert store.stage_logs[2].status == PipelineStatus.failed


def test_transient_error_fails_stage_but_does_not_mark_version_failed() -> None:
    """Orchestrator leaves terminal marking to Celery retry exhaustion."""
    run, version = _make_run_and_version()
    store = _FakeStore(run, version)

    def _timeout(_vid: uuid.UUID) -> dict[str, Any]:
        raise TransientPipelineError("qdrant timeout")

    handlers = {
        PipelineStage.ocr_cleaning: _timeout,
        PipelineStage.chunking: lambda _v: {"stub": True},
        PipelineStage.embedding: lambda _v: {"stub": True},
        PipelineStage.graph_extraction: lambda _v: {"stub": True},
        PipelineStage.indexing: lambda _v: {"stub": True},
    }

    with pytest.raises(TransientPipelineError):
        execute_pipeline(
            run.id,
            stage_handlers=handlers,
            session_factory=_session_factory_for(store),
        )

    assert store.stage_logs[0].status == PipelineStatus.failed
    # Version stays processing so a retry can continue; Celery marks failed at end.
    assert version.status == DocumentVersionStatus.processing
    assert run.status == PipelineStatus.running
    assert len(store.stage_logs) == 1


def test_remaining_stub_handlers_are_callable() -> None:
    """Indexing remains a stub until Step 6; graph_extraction is real."""
    from app.workers.stages import STAGE_HANDLERS

    vid = uuid.uuid4()
    meta = STAGE_HANDLERS[PipelineStage.indexing](vid)
    assert isinstance(meta, dict)
    assert meta.get("stub") is True
