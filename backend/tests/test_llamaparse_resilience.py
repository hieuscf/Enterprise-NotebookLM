# =============================================================================
# File: test_llamaparse_resilience.py
# Module/Service: Pipeline Worker — LlamaParse Client
# Layer: Adapter
# Purpose: End-to-end tests for LlamaParse retry policy and circuit breaker.
# Responsibilities:
#   - Cover retry, no-retry, circuit open/half-open, pipeline fail-fast, metrics
# Dependencies:
#   - pytest, httpx, tests.support.llamaparse_resilience
# Public Exports:
#   - N/A
# Database/Table: pipeline_runs (faked in TEST 7)
# Related Modules: app.clients.llamaparse_client, app.core.resilience
# Important Notes: LlamaParse breaker namespace is isolated from LLM providers.
# =============================================================================

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.clients.llamaparse_client import (
    LLAMAPARSE_CB_OPEN_MESSAGE,
    LlamaParseCircuitOpenError,
    LlamaParseRequestError,
    LlamaParseServiceError,
    build_llamaparse_circuit_breaker,
    get_llamaparse_circuit_breaker_metrics,
)
from app.core.resilience import CircuitBreakerOpenError, get_circuit_breaker_metrics
from app.core.resilience.metrics import reset_circuit_breaker_metrics_for_tests
from app.models.documents import Document, DocumentVersion
from app.models.enums import DocumentVersionStatus, FileType, PipelineStage, PipelineStatus
from app.models.pipeline import PipelineRun, PipelineStageLog
from app.services.document_understanding import DocumentUnderstandingService, LlamaParseDocumentParser
from app.workers.pipeline import execute_pipeline
from app.workers.stages import STAGE_ORDER
from app.workers.stages.document_understanding import stage_document_understanding
from app.workers.stages.errors import DataPipelineError
from tests.support.llamaparse_resilience import (
    StubLlamaParseClient,
    build_other_service_breaker,
    llamaparse_test_settings,
    success_handler,
)


@pytest.fixture(autouse=True)
def _reset_metrics() -> None:
    reset_circuit_breaker_metrics_for_tests()
    yield
    reset_circuit_breaker_metrics_for_tests()


@pytest.fixture(autouse=True)
def _disable_poll_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep retry tests fast by skipping poll/backoff sleeps."""
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)


def test_1_retry_on_http_500_retries_expected_times() -> None:
    """TEST 1: HTTP 500 is retried up to LLAMAPARSE_MAX_RETRIES."""
    attempts = {"upload": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/beta/files":
            attempts["upload"] += 1
            return httpx.Response(500, json={"detail": "internal error"})
        raise AssertionError(f"unexpected path {request.url.path}")

    settings = llamaparse_test_settings(llamaparse_max_retries=3)
    client = StubLlamaParseClient(settings, handler)

    with pytest.raises(LlamaParseServiceError, match="HTTP 500"):
        client.parse(data=b"bytes", filename="a.pdf", file_type=FileType.pdf)

    assert attempts["upload"] == 3


def test_2_http_400_is_not_retried() -> None:
    """TEST 2: HTTP 400 is not retried — exactly one API call."""
    attempts = {"upload": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["upload"] += 1
        return httpx.Response(400, json={"detail": "bad request"})

    settings = llamaparse_test_settings(llamaparse_max_retries=3)
    client = StubLlamaParseClient(settings, handler)

    with pytest.raises(LlamaParseRequestError, match="bad request") as exc_info:
        client.parse(data=b"bytes", filename="a.pdf", file_type=FileType.pdf)

    assert exc_info.value.status_code == 400
    assert attempts["upload"] == 1


def test_3_circuit_opens_after_five_consecutive_failures() -> None:
    """TEST 3: Five consecutive failures trip the circuit to OPEN."""
    attempts = {"upload": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["upload"] += 1
        return httpx.Response(503, json={"detail": "upstream busy"})

    settings = llamaparse_test_settings(
        llamaparse_max_retries=1,
        llamaparse_cb_failure_threshold=5,
    )
    client = StubLlamaParseClient(settings, handler)

    for _ in range(4):
        with pytest.raises(LlamaParseServiceError, match="HTTP 503"):
            client.parse(data=b"bytes", filename="a.pdf", file_type=FileType.pdf)
        assert client._circuit_breaker.state == "closed"

    with pytest.raises(LlamaParseCircuitOpenError, match=LLAMAPARSE_CB_OPEN_MESSAGE):
        client.parse(data=b"bytes", filename="a.pdf", file_type=FileType.pdf)

    assert client._circuit_breaker.state == "open"
    assert attempts["upload"] == 5


def test_4_fail_fast_when_circuit_open_does_not_call_api() -> None:
    """TEST 4: OPEN circuit fail-fast — no further HTTP calls."""
    attempts = {"upload": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["upload"] += 1
        return httpx.Response(503, json={"detail": "upstream busy"})

    settings = llamaparse_test_settings(
        llamaparse_max_retries=1,
        llamaparse_cb_failure_threshold=1,
    )
    client = StubLlamaParseClient(settings, handler)

    with pytest.raises(LlamaParseCircuitOpenError, match=LLAMAPARSE_CB_OPEN_MESSAGE):
        client.parse(data=b"bytes", filename="a.pdf", file_type=FileType.pdf)
    assert attempts["upload"] == 1

    with pytest.raises(LlamaParseCircuitOpenError, match=LLAMAPARSE_CB_OPEN_MESSAGE):
        client.parse(data=b"bytes", filename="b.pdf", file_type=FileType.pdf)
    assert attempts["upload"] == 1


def test_5_half_open_success_after_cooldown_closes_circuit() -> None:
    """TEST 5: After cooldown, a successful probe closes the circuit."""
    settings = llamaparse_test_settings(
        llamaparse_max_retries=1,
        llamaparse_cb_failure_threshold=1,
        llamaparse_cb_success_threshold=1,
    )
    client = StubLlamaParseClient(settings, success_handler())
    client._circuit_breaker._breaker.open()
    client._circuit_breaker._breaker.half_open()

    result = client.parse(data=b"bytes", filename="a.pdf", file_type=FileType.pdf)
    assert result.markdown == "# OK"
    assert client._circuit_breaker.state == "closed"


def test_6_half_open_failure_after_cooldown_reopens_circuit() -> None:
    """TEST 6: After cooldown, a failed probe returns the circuit to OPEN."""
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(503, json={"detail": "still down"})

    settings = llamaparse_test_settings(
        llamaparse_max_retries=1,
        llamaparse_cb_failure_threshold=1,
    )
    client = StubLlamaParseClient(settings, handler)

    with pytest.raises(LlamaParseCircuitOpenError):
        client.parse(data=b"bytes", filename="a.pdf", file_type=FileType.pdf)
    assert calls["count"] == 1

    client._circuit_breaker._breaker.half_open()

    with pytest.raises(LlamaParseCircuitOpenError):
        client.parse(data=b"bytes", filename="a.pdf", file_type=FileType.pdf)

    assert calls["count"] == 2
    assert client._circuit_breaker.state == "open"


class _PipelineFakeStore:
    def __init__(self, run: PipelineRun, version: DocumentVersion) -> None:
        self.run = run
        self.version = version
        self.stage_logs: list[PipelineStageLog] = []

    def get_run(self, pipeline_run_id: uuid.UUID) -> PipelineRun | None:
        return self.run if self.run.id == pipeline_run_id else None

    def get_version(self, version_id: uuid.UUID) -> DocumentVersion | None:
        return self.version if self.version.id == version_id else None

    def mark_run_running(self, run: PipelineRun) -> None:
        run.status = PipelineStatus.running

    def mark_run_completed(self, run: PipelineRun) -> None:
        run.status = PipelineStatus.completed

    def mark_run_failed(self, run: PipelineRun, error_message: str) -> None:
        run.status = PipelineStatus.failed
        run.error_message = error_message[:4000]

    def increment_retry_count(self, run: PipelineRun) -> int:
        run.retry_count += 1
        return run.retry_count

    def set_version_status(
        self,
        version: DocumentVersion,
        status: DocumentVersionStatus,
        *,
        page_count: int | None = None,
    ) -> None:
        version.status = status

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

    def complete_stage(self, log: PipelineStageLog, *, metadata: dict[str, Any] | None = None) -> None:
        log.status = PipelineStatus.completed
        log.metadata_ = metadata

    def fail_stage(self, log: PipelineStageLog, error_message: str) -> None:
        log.status = PipelineStatus.failed
        log.error_message = error_message


def _pipeline_rows() -> tuple[PipelineRun, DocumentVersion, Document]:
    version_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    run = PipelineRun(
        id=uuid.uuid4(),
        document_version_id=version_id,
        status=PipelineStatus.pending,
        retry_count=0,
    )
    version = DocumentVersion(
        id=version_id,
        document_id=doc_id,
        uploaded_by=uuid.uuid4(),
        version_number=1,
        storage_path="workspaces/ws/documents/doc/v1/report.pdf",
        file_size_bytes=1024,
        checksum_sha256="x",
        status=DocumentVersionStatus.processing,
        is_current=True,
        created_at=datetime.now(UTC),
    )
    document = Document(
        id=doc_id,
        workspace_id=uuid.uuid4(),
        current_version_id=version_id,
        title="Report",
        file_type=FileType.pdf,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    return run, version, document


@contextmanager
def _pipeline_session(version: DocumentVersion, document: Document):
    session = MagicMock()
    session.get.side_effect = lambda model, pk: {
        DocumentVersion: version,
        Document: document,
    }.get(model)
    session.flush = MagicMock()
    session.commit = MagicMock()
    yield session


def test_7_pipeline_run_failed_when_circuit_open() -> None:
    """TEST 7: Circuit OPEN fails pipeline_runs with the canonical error message."""
    run, version, document = _pipeline_rows()
    store = _PipelineFakeStore(run, version)
    storage = MagicMock()
    storage.download_bytes.return_value = b"%PDF-1.7"

    settings = llamaparse_test_settings(document_parser="llamaparse")
    breaker = build_llamaparse_circuit_breaker(settings)
    breaker._breaker.open()
    client = StubLlamaParseClient(settings, success_handler(), circuit_breaker=breaker)
    parser = LlamaParseDocumentParser(client, settings)
    service = DocumentUnderstandingService(storage=storage, settings=settings, parser=parser)

    module = "app.workers.stages.document_understanding"

    def _doc_stage(document_version_id: uuid.UUID) -> dict[str, Any]:
        with (
            patch(f"{module}.get_minio_storage", return_value=storage),
            patch(f"{module}.get_sync_session", lambda: _pipeline_session(version, document)),
            patch(f"{module}.get_settings", return_value=settings),
            patch(f"{module}.build_document_understanding_service", return_value=service),
        ):
            return stage_document_understanding(document_version_id)

    handlers = {stage: (lambda _vid, s=stage: {"stub": True}) for stage in STAGE_ORDER}
    handlers[PipelineStage.document_understanding] = _doc_stage

    @contextmanager
    def _session_factory():
        session = MagicMock()
        session.flush = MagicMock()
        session.commit = MagicMock()
        from app.workers import pipeline as pipeline_mod

        original = pipeline_mod.PipelineSyncRepository
        pipeline_mod.PipelineSyncRepository = lambda _s: store  # type: ignore[assignment,misc]
        try:
            yield session
        finally:
            pipeline_mod.PipelineSyncRepository = original

    with pytest.raises(DataPipelineError, match="LlamaParse circuit breaker open"):
        execute_pipeline(run.id, stage_handlers=handlers, session_factory=_session_factory)

    assert run.status == PipelineStatus.failed
    assert run.error_message == "LlamaParse circuit breaker open"
    stage_log = next(
        log for log in store.stage_logs if log.stage == PipelineStage.document_understanding
    )
    assert stage_log.error_message == "LlamaParse circuit breaker open"


def test_8_metrics_increment_trip_fail_fast_and_open_totals() -> None:
    """TEST 8: trip_total, open_total, and fail_fast_total increment correctly."""
    attempts = {"upload": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["upload"] += 1
        return httpx.Response(503, json={"detail": "upstream busy"})

    settings = llamaparse_test_settings(
        llamaparse_max_retries=1,
        llamaparse_cb_failure_threshold=1,
    )
    client = StubLlamaParseClient(settings, handler)

    with pytest.raises(LlamaParseCircuitOpenError):
        client.parse(data=b"bytes", filename="a.pdf", file_type=FileType.pdf)

    with pytest.raises(LlamaParseCircuitOpenError):
        client.parse(data=b"bytes", filename="b.pdf", file_type=FileType.pdf)

    metrics = get_llamaparse_circuit_breaker_metrics()
    assert metrics["llamaparse_cb_trip_total"] >= 1
    assert metrics["llamaparse_cb_open_total"] >= 1
    assert metrics["llamaparse_cb_fail_fast_total"] >= 1


def test_circuit_breaker_metrics_are_isolated_by_namespace() -> None:
    """LlamaParse and other services use independent breaker instances and metrics."""
    llamaparse_breaker = build_llamaparse_circuit_breaker(
        llamaparse_test_settings(llamaparse_cb_failure_threshold=2),
    )
    llm_breaker = build_other_service_breaker("anthropic_cb")

    def _fail() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        llamaparse_breaker.call(_fail)
    with pytest.raises(CircuitBreakerOpenError):
        llamaparse_breaker.call(_fail)

    with pytest.raises(RuntimeError):
        llm_breaker.call(_fail)
    with pytest.raises(CircuitBreakerOpenError):
        llm_breaker.call(_fail)

    lp_metrics = get_llamaparse_circuit_breaker_metrics()
    llm_metrics = get_circuit_breaker_metrics("anthropic_cb").snapshot()

    assert lp_metrics["llamaparse_cb_trip_total"] >= 1
    assert llm_metrics["anthropic_cb_trip_total"] >= 1
    assert llamaparse_breaker is not llm_breaker
    assert llamaparse_breaker.name == "llamaparse"
