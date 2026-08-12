# =============================================================================
# File: test_document_understanding.py
# Module/Service: Pipeline Worker — Document Understanding ([AI])
# Layer: Service
# Purpose: Unit tests for the v3 LlamaParse stage: Markdown + Layout Analysis +
#   Metadata Extraction, and failure mapping (success / timeout / 4xx / 5xx).
# Responsibilities:
#   - Markdown Metadata Extraction counts (headings per level, tables, figures)
#   - Layout Analysis from the items tree (heading tree, heading_path, bbox)
#   - Stage persistence: markdown_storage_path, layout_metadata, parser
#   - Adapter error taxonomy + bounded retry via httpx.MockTransport
#   - Offline fallback to the local OCR parser
# Dependencies:
#   - pytest, httpx MockTransport; MinIO/Postgres/LlamaParse all mocked
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: app.adapters.llamaparse, app.ai.layout,
#   app.workers.stages.document_understanding
# Important Notes: No live MinIO/Postgres/LlamaParse in CI.
# =============================================================================

from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.adapters.llamaparse import (
    LlamaParseClient,
    LlamaParseRequestError,
    LlamaParseResult,
    LlamaParseServiceError,
    LlamaParseTimeoutError,
)
from app.ai.layout import (
    build_layout_analysis,
    extract_markdown_metrics,
    resolve_page_count,
)
from app.core.config import Settings
from app.models.documents import Document, DocumentVersion
from app.models.enums import DocumentVersionStatus, FileType
from app.services.document_understanding import (
    DocumentUnderstandingService,
    LlamaParseDocumentParser,
    LocalOcrDocumentParser,
    PARSER_LLAMAPARSE,
    PARSER_LOCAL_OCR,
    USER_PARSE_FAILED,
    build_document_understanding_service,
    resolve_document_parser,
    should_fallback_to_local_ocr,
)
from app.workers.stages.document_understanding import stage_document_understanding
from app.workers.stages.errors import DataPipelineError, TransientPipelineError

MARKDOWN = """# 1. Giới thiệu

Đoạn mở đầu về Enterprise NotebookLM và kiến trúc RAG.

## 1.1 Mục tiêu

Nội dung mục tiêu của hệ thống.

| Chỉ số | Giá trị |
| --- | --- |
| Độ chính xác | 92% |
| Độ trễ | 1.4s |

![Sơ đồ kiến trúc](arch.png)

## 1.2 Phạm vi

- Workspace
- Document pipeline

# 2. Kết luận

Tổng kết ngắn gọn.
"""

ITEM_PAGES: list[dict[str, Any]] = [
    {
        "page_number": 1,
        "items": [
            {
                "type": "heading",
                "lvl": 1,
                "md": "1. Giới thiệu",
                "bBox": {"x": 1, "y": 2, "w": 3, "h": 4},
            },
            {"type": "text", "md": "Đoạn mở đầu về Enterprise NotebookLM và kiến trúc RAG."},
            {"type": "heading", "lvl": 2, "md": "1.1 Mục tiêu"},
            {"type": "text", "md": "Nội dung mục tiêu của hệ thống."},
            {
                "type": "table",
                "rows": [["Chỉ số", "Giá trị"], ["Độ chính xác", "92%"], ["Độ trễ", "1.4s"]],
            },
        ],
    },
    {
        "page_number": 2,
        "items": [
            {"type": "heading", "lvl": 1, "md": "2. Kết luận"},
            {"type": "text", "md": "Tổng kết ngắn gọn."},
        ],
    },
]


# ---------------------------------------------------------------------------
# Metadata Extraction from the Markdown structure (no extra API call)
# ---------------------------------------------------------------------------


def test_markdown_metrics_counts_headings_tables_figures_words() -> None:
    metrics = extract_markdown_metrics(MARKDOWN)

    assert metrics.heading_counts_by_level == {1: 2, 2: 2}
    assert metrics.heading_count == 4
    assert metrics.table_count == 1
    assert metrics.figure_count == 1
    assert metrics.word_count > 20
    assert metrics.char_count == len(MARKDOWN)
    # JSONB keys must be strings
    assert metrics.as_dict()["heading_counts_by_level"] == {"1": 2, "2": 2}


def test_markdown_metrics_ignores_headings_inside_code_fence() -> None:
    markdown = "# Real heading\n\n```\n# not a heading\n| a | b |\n| --- | --- |\n```\n"
    metrics = extract_markdown_metrics(markdown)

    assert metrics.heading_count == 1
    assert metrics.table_count == 0


def test_markdown_metrics_on_empty_document() -> None:
    metrics = extract_markdown_metrics("")

    assert metrics.heading_count == 0
    assert metrics.word_count == 0
    assert metrics.char_count == 0


# ---------------------------------------------------------------------------
# Layout Analysis
# ---------------------------------------------------------------------------


def test_layout_from_items_builds_heading_tree_and_paths() -> None:
    analysis = build_layout_analysis(
        markdown=MARKDOWN,
        item_pages=ITEM_PAGES,
        reported_page_count=2,
    )

    assert analysis.source == "items"
    assert analysis.page_count == 2
    assert analysis.section_count == 2  # two level-1 headings

    tree = analysis.heading_tree
    assert [node["title"] for node in tree] == ["1. Giới thiệu", "2. Kết luận"]
    assert [child["title"] for child in tree[0]["children"]] == ["1.1 Mục tiêu"]

    table = next(b for b in analysis.blocks if b.block_type == "table")
    assert table.heading_path == "1. Giới thiệu > 1.1 Mục tiêu"
    assert table.row_count == 3
    assert table.col_count == 2
    assert table.page_number == 1

    heading = analysis.blocks[0]
    assert heading.bbox == [1.0, 2.0, 3.0, 4.0]
    assert heading.depth == 0


def test_layout_falls_back_to_markdown_when_items_missing() -> None:
    analysis = build_layout_analysis(markdown=MARKDOWN, item_pages=[])

    assert analysis.source == "markdown"
    assert [node["title"] for node in analysis.heading_tree] == ["1. Giới thiệu", "2. Kết luận"]
    assert any(b.block_type == "table" for b in analysis.blocks)
    assert any(b.block_type == "figure" for b in analysis.blocks)
    assert any(b.block_type == "list" for b in analysis.blocks)


def test_resolve_page_count_uses_sections_for_unpaginated_types() -> None:
    analysis = build_layout_analysis(
        markdown=MARKDOWN,
        item_pages=ITEM_PAGES,
        reported_page_count=2,
    )

    assert resolve_page_count(analysis=analysis, file_type=FileType.pdf) == 2
    assert resolve_page_count(analysis=analysis, file_type=FileType.docx) == 2  # 2 sections
    assert resolve_page_count(analysis=analysis, file_type=FileType.txt) >= 1


# ---------------------------------------------------------------------------
# Fixtures / doubles
# ---------------------------------------------------------------------------


def _settings(*, api_key: str | None = "llx-test", **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "document_parser": "llamaparse",
        "llamaparse_api_key": api_key,
        "llamaparse_base_url": "https://parse.test",
        "llamaparse_timeout_seconds": 5,
        "llamaparse_max_retries": 3,
        "llamaparse_poll_interval_seconds": 0.01,
        "llamaparse_fallback_to_local_ocr": True,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _rows(file_type: FileType = FileType.pdf) -> tuple[DocumentVersion, Document]:
    version_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    version = DocumentVersion(
        id=version_id,
        document_id=doc_id,
        uploaded_by=uuid.uuid4(),
        version_number=1,
        storage_path=f"workspaces/ws/documents/doc/v1/report.{file_type.value}",
        file_size_bytes=1024,
        checksum_sha256="x",
        page_count=None,
        status=DocumentVersionStatus.processing,
        is_current=True,
        created_at=datetime.now(UTC),
    )
    document = Document(
        id=doc_id,
        workspace_id=uuid.uuid4(),
        current_version_id=version_id,
        title="Report",
        file_type=file_type,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    return version, document


def _fake_storage(payload: bytes = b"%PDF-1.7 fake bytes") -> tuple[MagicMock, dict[str, bytes]]:
    uploaded: dict[str, bytes] = {}
    storage = MagicMock()
    storage.download_bytes.return_value = payload

    def _upload(*, object_key: str, data: bytes, content_type: str = "") -> str:
        uploaded[object_key] = data
        return object_key

    storage.upload_bytes.side_effect = _upload
    return storage, uploaded


@contextmanager
def _session_for(version: DocumentVersion, document: Document):
    session = MagicMock()
    session.get.side_effect = lambda model, pk: {
        DocumentVersion: version,
        Document: document,
    }.get(model)
    yield session


def _build_service(
    *,
    storage: MagicMock,
    settings: Settings,
    client: MagicMock | None,
) -> DocumentUnderstandingService:
    if settings.document_parser == "local":
        parser = LocalOcrDocumentParser()
        fallback = None
    else:
        assert client is not None
        parser = LlamaParseDocumentParser(client, settings)
        fallback = (
            LocalOcrDocumentParser() if settings.llamaparse_fallback_to_local_ocr else None
        )
    return DocumentUnderstandingService(
        storage=storage,
        settings=settings,
        parser=parser,
        fallback_parser=fallback,
    )


def _run_stage(
    version: DocumentVersion,
    document: Document,
    *,
    storage: MagicMock,
    client: MagicMock | None,
    settings: Settings,
) -> dict[str, Any]:
    module = "app.workers.stages.document_understanding"
    service = _build_service(storage=storage, settings=settings, client=client)
    patches = [
        patch(f"{module}.get_minio_storage", return_value=storage),
        patch(f"{module}.get_sync_session", lambda: _session_for(version, document)),
        patch(f"{module}.get_settings", return_value=settings),
        patch(f"{module}.build_document_understanding_service", return_value=service),
    ]

    with patches[0], patches[1], patches[2], patches[3]:
        return stage_document_understanding(version.id)


# ---------------------------------------------------------------------------
# Stage — case 1: success
# ---------------------------------------------------------------------------


def test_stage_success_persists_markdown_layout_and_metadata() -> None:
    version, document = _rows(FileType.pdf)
    storage, uploaded = _fake_storage()
    client = MagicMock()
    client.parse.return_value = LlamaParseResult(
        job_id="job-123",
        markdown=MARKDOWN,
        pages=ITEM_PAGES,
        page_count=2,
        tier="cost_effective",
        attempts=1,
        duration_ms=4200,
    )

    meta = _run_stage(
        version,
        document,
        storage=storage,
        client=client,
        settings=_settings(),
    )

    # Markdown stored beside the original file and referenced from the DB row
    assert version.markdown_storage_path == "workspaces/ws/documents/doc/v1/document.md"
    assert version.markdown_storage_path in uploaded
    assert uploaded[version.markdown_storage_path].decode("utf-8") == MARKDOWN
    assert version.parser == PARSER_LLAMAPARSE

    # Layout Analysis persisted as JSONB without block text (column stays small)
    layout = version.layout_metadata
    assert layout["parser"] == PARSER_LLAMAPARSE
    assert layout["job_id"] == "job-123"
    assert layout["tier"] == "cost_effective"
    assert [n["title"] for n in layout["heading_tree"]] == ["1. Giới thiệu", "2. Kết luận"]
    assert layout["metrics"]["heading_counts_by_level"] == {"1": 2, "2": 2}
    assert len(layout["tables"]) == 1
    assert all("text" not in block for block in layout["blocks"])

    # Metadata Extraction surfaced on the stage log
    assert meta["parser"] == PARSER_LLAMAPARSE
    assert meta["llamaparse_job_id"] == "job-123"
    assert meta["llamaparse_attempts"] == 1
    assert meta["heading_count"] == 4
    assert meta["heading_counts_by_level"] == {"1": 2, "2": 2}
    assert meta["table_count"] == 1
    assert meta["figure_count"] == 1
    assert meta["word_count"] > 20
    assert meta["page_count"] == 2
    assert meta["block_count"] >= 1
    assert "duration_ms" in meta

    assert meta["layout_artifact_key"].endswith(".pipeline/llamaparse_layout.json")
    assert meta["layout_artifact_key"] in uploaded

    layout_payload = json.loads(uploaded[meta["layout_artifact_key"]].decode("utf-8"))
    assert all("text" in block for block in layout_payload["blocks"])

    # No LLM Provider involvement in this stage
    client.parse.assert_called_once()
    assert client.parse.call_args.kwargs["file_type"] is FileType.pdf
    assert client.parse.call_args.kwargs["filename"] == "report.pdf"


# ---------------------------------------------------------------------------
# Stage — case 2: timeout, case 3: 4xx / 5xx
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "expected_message"),
    [
        (LlamaParseTimeoutError("budget exhausted", client_timeout=True), "polling budget expired|budget exhausted"),
        (LlamaParseServiceError("HTTP 503", status_code=503), "LlamaParse unavailable"),
        (LlamaParseRequestError("HTTP 401", status_code=401), "authentication/configuration"),
        (LlamaParseRequestError("HTTP 422", status_code=422), "LlamaParse rejected the document"),
    ],
)
def test_stage_llamaparse_failures_are_terminal_when_fallback_disabled(
    error: Exception,
    expected_message: str,
) -> None:
    """With fallback disabled, LlamaParse failures fail the run (no Celery retry)."""
    version, document = _rows()
    storage, uploaded = _fake_storage()
    client = MagicMock()
    client.parse.side_effect = error

    with pytest.raises(DataPipelineError, match=expected_message):
        _run_stage(
            version,
            document,
            storage=storage,
            client=client,
            settings=_settings(llamaparse_fallback_to_local_ocr=False),
        )

    assert uploaded == {}
    assert version.markdown_storage_path is None
    assert version.layout_metadata is None


def test_stage_empty_source_file_fails_before_calling_llamaparse() -> None:
    version, document = _rows()
    storage, _ = _fake_storage(payload=b"")
    client = MagicMock()

    with pytest.raises(DataPipelineError, match="empty"):
        _run_stage(version, document, storage=storage, client=client, settings=_settings())

    client.parse.assert_not_called()


# ---------------------------------------------------------------------------
# Stage — offline fallback (no LLAMAPARSE_API_KEY)
# ---------------------------------------------------------------------------


def test_stage_falls_back_to_local_ocr_without_api_key() -> None:
    version, document = _rows(FileType.txt)
    storage, uploaded = _fake_storage(
        payload="Giới thiệu\n\nĐoạn nội dung đầu tiên.\n\nĐoạn nội dung thứ hai.\n".encode()
    )

    meta = _run_stage(
        version,
        document,
        storage=storage,
        client=None,
        settings=_settings(api_key=None, document_parser="local"),
    )

    assert meta["parser"] == PARSER_LOCAL_OCR
    assert meta["llamaparse_job_id"] is None
    assert meta["llamaparse_attempts"] is None
    assert version.parser == PARSER_LOCAL_OCR
    assert version.markdown_storage_path in uploaded
    assert meta["block_count"] >= 1


def test_service_rejects_llamaparse_without_api_key() -> None:
    storage = MagicMock()
    settings = _settings(api_key=None, document_parser="llamaparse")

    with pytest.raises(DataPipelineError, match="configuration error"):
        resolve_document_parser(settings=settings)


def test_service_execute_storage_failure_rolls_back_partial_uploads() -> None:
    version, document = _rows(FileType.pdf)
    uploaded: dict[str, bytes] = {}
    storage = MagicMock()
    storage.download_bytes.return_value = b"%PDF-1.7 fake bytes"

    def _upload(*, object_key: str, data: bytes, content_type: str = "") -> str:
        uploaded[object_key] = data
        if object_key.endswith("llamaparse_layout.json"):
            raise OSError("disk full")
        return object_key

    storage.upload_bytes.side_effect = _upload
    storage.delete_object = MagicMock()

    client = MagicMock()
    client.parse.return_value = LlamaParseResult(
        job_id="job-rollback",
        markdown=MARKDOWN,
        pages=ITEM_PAGES,
        page_count=2,
        tier="cost_effective",
        attempts=1,
        duration_ms=100,
    )
    service = _build_service(storage=storage, settings=_settings(), client=client)

    with pytest.raises(TransientPipelineError, match="MinIO upload"):
        service.execute(
            document_version_id=version.id,
            version=version,
            document=document,
        )

    assert storage.delete_object.called
    assert any(key.endswith("document.md") for key in uploaded)


def test_stage_database_failure_rolls_back_artifacts() -> None:
    version, document = _rows(FileType.pdf)
    storage, uploaded = _fake_storage()
    client = MagicMock()
    client.parse.return_value = LlamaParseResult(
        job_id="job-db-fail",
        markdown=MARKDOWN,
        pages=ITEM_PAGES,
        page_count=2,
        tier="cost_effective",
        attempts=1,
        duration_ms=100,
    )
    service = _build_service(storage=storage, settings=_settings(), client=client)

    call_count = {"n": 0}

    @contextmanager
    def _sessions():
        call_count["n"] += 1
        if call_count["n"] == 1:
            with _session_for(version, document) as session:
                yield session
        else:
            session = MagicMock()
            session.get.return_value = None
            yield session

    module = "app.workers.stages.document_understanding"
    with (
        patch(f"{module}.get_minio_storage", return_value=storage),
        patch(f"{module}.get_sync_session", _sessions),
        patch(f"{module}.get_settings", return_value=_settings()),
        patch(f"{module}.build_document_understanding_service", return_value=service),
    ):
        with pytest.raises(DataPipelineError, match="disappeared"):
            stage_document_understanding(version.id)

    storage.delete_object.assert_called()
    assert version.markdown_storage_path is None


def test_service_skips_reparse_when_outputs_exist() -> None:
    version, document = _rows(FileType.pdf)
    version.markdown_storage_path = "workspaces/ws/documents/doc/v1/document.md"
    version.layout_metadata = {
        "parser": PARSER_LLAMAPARSE,
        "job_id": "job-existing",
        "tier": "cost_effective",
        "source": "items",
        "page_count": 2,
        "section_count": 2,
        "block_count": 5,
        "metrics": extract_markdown_metrics(MARKDOWN).as_dict(),
        "heading_tree": [],
        "blocks": [],
        "tables": [],
        "figures": [],
        "layout_artifact_key": "workspaces/ws/documents/doc/v1/.pipeline/llamaparse_layout.json",
    }
    version.parser = PARSER_LLAMAPARSE

    storage = MagicMock()
    storage.download_bytes.side_effect = AssertionError("should not download on skip")
    client = MagicMock()
    service = _build_service(storage=storage, settings=_settings(), client=client)

    result = service.execute(
        document_version_id=version.id,
        version=version,
        document=document,
    )

    client.parse.assert_not_called()
    assert result.stage_metadata["parser"] == PARSER_LLAMAPARSE
    assert result.stage_metadata["markdown_storage_path"] == version.markdown_storage_path
    assert result.artifact_keys == ()


# ---------------------------------------------------------------------------
# Adapter — REST flow, retry budget and error mapping
# ---------------------------------------------------------------------------


class _StubTransportClient(LlamaParseClient):
    """LlamaParseClient wired to an httpx MockTransport (no network)."""

    def __init__(self, settings: Settings, handler: Any) -> None:
        super().__init__(settings)
        self._handler = handler

    def _http_client(self) -> httpx.Client:
        return httpx.Client(
            transport=httpx.MockTransport(self._handler),
            base_url="https://parse.test",
            headers={"Accept": "application/json"},
        )


@pytest.fixture(autouse=True)
def _no_backoff_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep bounded-retry tests fast without changing production backoff."""
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)


def _result_payload(status: str, **extra: Any) -> dict[str, Any]:
    return {"job": {"id": "job-1", "status": status}, **extra}


def test_adapter_uploads_creates_job_and_polls_until_completed() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        calls.append(path)
        if path == "/api/v1/beta/files":
            return httpx.Response(200, json={"id": "file-1"})
        if path == "/api/v2/parse":
            return httpx.Response(200, json={"id": "job-1", "status": "PENDING"})
        if path == "/api/v2/parse/job-1":
            expand = request.url.params.get_list("expand")
            assert expand == ["markdown_full", "items"]
            if calls.count(path) == 1:
                return httpx.Response(200, json=_result_payload("RUNNING"))
            return httpx.Response(
                200,
                json=_result_payload(
                    "COMPLETED",
                    markdown_full=MARKDOWN,
                    items={"pages": ITEM_PAGES},
                    job_metadata={"page_count": 2},
                ),
            )
        raise AssertionError(f"unexpected path {path}")

    client = _StubTransportClient(_settings(), handler)
    result = client.parse(data=b"bytes", filename="report.pdf", file_type=FileType.pdf)

    assert result.job_id == "job-1"
    assert result.markdown == MARKDOWN
    assert result.page_count == 2
    assert len(result.pages) == 2
    assert result.attempts == 1
    assert calls.count("/api/v2/parse/job-1") == 2


def test_adapter_falls_back_to_per_page_markdown() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/beta/files":
            return httpx.Response(200, json={"id": "file-1"})
        if request.url.path == "/api/v2/parse":
            return httpx.Response(200, json={"id": "job-1"})
        return httpx.Response(
            200,
            json=_result_payload(
                "COMPLETED",
                markdown={"pages": [{"markdown": "# One"}, {"markdown": "# Two"}]},
            ),
        )

    client = _StubTransportClient(_settings(), handler)
    result = client.parse(data=b"bytes", filename="a.pdf", file_type=FileType.pdf)

    assert result.markdown == "# One\n\n# Two"


def test_adapter_retries_5xx_then_succeeds() -> None:
    attempts = {"parse": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/beta/files":
            return httpx.Response(200, json={"id": "file-1"})
        if request.url.path == "/api/v2/parse":
            attempts["parse"] += 1
            if attempts["parse"] < 3:
                return httpx.Response(503, json={"detail": "upstream busy"})
            return httpx.Response(200, json={"id": "job-1"})
        return httpx.Response(200, json=_result_payload("COMPLETED", markdown_full=MARKDOWN))

    client = _StubTransportClient(_settings(), handler)
    result = client.parse(data=b"bytes", filename="a.pdf", file_type=FileType.pdf)

    assert result.attempts == 1
    assert attempts["parse"] == 3


def test_adapter_gives_up_after_max_retries_on_5xx() -> None:
    attempts = {"parse": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/beta/files":
            return httpx.Response(200, json={"id": "file-1"})
        attempts["parse"] += 1
        return httpx.Response(500, json={"detail": "boom"})

    client = _StubTransportClient(_settings(llamaparse_max_retries=2), handler)

    with pytest.raises(LlamaParseServiceError, match="HTTP 500"):
        client.parse(data=b"bytes", filename="a.pdf", file_type=FileType.pdf)

    assert attempts["parse"] == 2  # bounded — no infinite retry


def test_adapter_does_not_retry_4xx() -> None:
    attempts = {"upload": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["upload"] += 1
        return httpx.Response(401, json={"detail": "invalid api key"})

    client = _StubTransportClient(_settings(), handler)

    with pytest.raises(LlamaParseRequestError, match="invalid api key") as exc_info:
        client.parse(data=b"bytes", filename="a.pdf", file_type=FileType.pdf)

    assert exc_info.value.status_code == 401
    assert attempts["upload"] == 1  # 4xx is permanent — retrying would still be billed


def test_adapter_does_not_retry_429() -> None:
    attempts = {"upload": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["upload"] += 1
        return httpx.Response(429, json={"detail": "rate limited"})

    client = _StubTransportClient(_settings(llamaparse_max_retries=3), handler)

    with pytest.raises(LlamaParseRequestError, match="rate limited") as exc_info:
        client.parse(data=b"bytes", filename="a.pdf", file_type=FileType.pdf)

    assert exc_info.value.status_code == 429
    assert attempts["upload"] == 1


def test_adapter_maps_transport_timeout_to_timeout_error() -> None:
    attempts = {"upload": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["upload"] += 1
        raise httpx.ReadTimeout("read timed out", request=request)

    client = _StubTransportClient(_settings(llamaparse_max_retries=2), handler)

    with pytest.raises(LlamaParseTimeoutError, match="timed out"):
        client.parse(data=b"bytes", filename="a.pdf", file_type=FileType.pdf)

    assert attempts["upload"] == 2


def test_adapter_times_out_when_job_never_completes() -> None:
    cancel_calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/beta/files":
            return httpx.Response(200, json={"id": "file-1"})
        if request.url.path == "/api/v2/parse":
            return httpx.Response(200, json={"id": "job-1"})
        if request.url.path.endswith("/cancel"):
            cancel_calls["n"] += 1
            return httpx.Response(200, json={"id": "job-1", "status": "CANCELLED"})
        return httpx.Response(200, json=_result_payload("RUNNING"))

    settings = _settings(llamaparse_max_retries=1, llamaparse_timeout_seconds=1)
    client = _StubTransportClient(settings, handler)

    with pytest.raises(LlamaParseTimeoutError, match="polling budget expired") as exc_info:
        client.parse(data=b"bytes", filename="a.pdf", file_type=FileType.pdf)

    err = exc_info.value
    assert err.job_id == "job-1"
    assert err.remote_status == "RUNNING"
    assert err.client_timeout is True
    assert err.budget_seconds == 1
    assert cancel_calls["n"] == 1


def test_adapter_treats_failed_job_as_permanent() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/beta/files":
            return httpx.Response(200, json={"id": "file-1"})
        if request.url.path == "/api/v2/parse":
            return httpx.Response(200, json={"id": "job-1"})
        return httpx.Response(
            200,
            json={"job": {"id": "job-1", "status": "FAILED", "error_message": "corrupt pdf"}},
        )

    client = _StubTransportClient(_settings(), handler)

    with pytest.raises(LlamaParseRequestError, match="corrupt pdf"):
        client.parse(data=b"bytes", filename="a.pdf", file_type=FileType.pdf)


def test_adapter_rejects_completed_job_without_markdown() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/beta/files":
            return httpx.Response(200, json={"id": "file-1"})
        if request.url.path == "/api/v2/parse":
            return httpx.Response(200, json={"id": "job-1"})
        return httpx.Response(200, json=_result_payload("COMPLETED", markdown_full=""))

    client = _StubTransportClient(_settings(), handler)

    with pytest.raises(LlamaParseRequestError, match="no Markdown content"):
        client.parse(data=b"bytes", filename="a.pdf", file_type=FileType.pdf)


def test_adapter_requires_api_key() -> None:
    with pytest.raises(LlamaParseRequestError, match="LLAMAPARSE_API_KEY"):
        LlamaParseClient(_settings(api_key=None))


# ---------------------------------------------------------------------------
# Fallback policy — timeout → local OCR; auth/unsupported stay terminal
# ---------------------------------------------------------------------------


def test_should_fallback_policy() -> None:
    assert should_fallback_to_local_ocr(
        LlamaParseTimeoutError("x", client_timeout=True, remote_status="RUNNING"),
        fallback_enabled=True,
    )
    assert should_fallback_to_local_ocr(
        LlamaParseServiceError("503", status_code=503),
        fallback_enabled=True,
    )
    assert not should_fallback_to_local_ocr(
        LlamaParseTimeoutError("x"),
        fallback_enabled=False,
    )
    assert not should_fallback_to_local_ocr(
        LlamaParseRequestError("bad key", status_code=401),
        fallback_enabled=True,
    )
    assert not should_fallback_to_local_ocr(
        LlamaParseRequestError("unsupported", status_code=422),
        fallback_enabled=True,
    )
    assert not should_fallback_to_local_ocr(
        LlamaParseRequestError("quota", status_code=402),
        fallback_enabled=True,
    )


def test_llamaparse_success_uses_llamaparse_parser() -> None:
    version, document = _rows(FileType.pdf)
    storage, _ = _fake_storage()
    client = MagicMock()
    client.parse.return_value = LlamaParseResult(
        job_id="job-ok",
        markdown=MARKDOWN,
        pages=ITEM_PAGES,
        page_count=2,
        tier="cost_effective",
        attempts=1,
        duration_ms=100,
    )
    meta = _run_stage(version, document, storage=storage, client=client, settings=_settings())
    assert meta["parser"] == PARSER_LLAMAPARSE
    assert meta["actual_parser"] == PARSER_LLAMAPARSE
    assert meta["fallback"] is False
    assert version.parser == PARSER_LLAMAPARSE
    client.parse.assert_called_once()


def test_timeout_with_fallback_uses_local_ocr_and_layout() -> None:
    version, document = _rows(FileType.txt)
    payload = "Giới thiệu\n\nĐoạn nội dung đầu tiên.\n\nĐoạn nội dung thứ hai.\n".encode()
    storage, uploaded = _fake_storage(payload=payload)
    client = MagicMock()
    client.parse.side_effect = LlamaParseTimeoutError(
        "LlamaParse client polling budget expired while remote job pjb-abc was still RUNNING.",
        job_id="pjb-abc",
        remote_status="RUNNING",
        client_timeout=True,
        budget_seconds=300,
    )

    meta = _run_stage(
        version,
        document,
        storage=storage,
        client=client,
        settings=_settings(llamaparse_fallback_to_local_ocr=True),
    )

    assert version.parser == PARSER_LOCAL_OCR
    assert meta["requested_parser"] == PARSER_LLAMAPARSE
    assert meta["actual_parser"] == PARSER_LOCAL_OCR
    assert meta["fallback"] is True
    assert meta["fallback_reason"] == "timeout"
    assert meta["llamaparse_job_id"] == "pjb-abc"
    assert meta["client_timeout"] is True
    assert meta["remote_status"] == "RUNNING"
    assert meta["llamaparse_timeout_seconds"] == 300
    assert meta["block_count"] >= 1
    assert version.markdown_storage_path in uploaded
    assert version.layout_metadata["parser"] == PARSER_LOCAL_OCR
    client.parse.assert_called_once()


def test_timeout_with_fallback_disabled_fails_with_diagnostics() -> None:
    version, document = _rows(FileType.txt)
    storage, uploaded = _fake_storage(
        payload="Giới thiệu\n\nNội dung.\n".encode(),
    )
    client = MagicMock()
    client.parse.side_effect = LlamaParseTimeoutError(
        "LlamaParse client polling budget expired while remote job pjb-xyz was still RUNNING.",
        job_id="pjb-xyz",
        remote_status="RUNNING",
        client_timeout=True,
        budget_seconds=300,
    )

    with pytest.raises(DataPipelineError) as exc_info:
        _run_stage(
            version,
            document,
            storage=storage,
            client=client,
            settings=_settings(llamaparse_fallback_to_local_ocr=False),
        )

    err = exc_info.value
    assert err.user_message == USER_PARSE_FAILED
    assert err.diagnostics.get("client_timeout") is True
    assert err.diagnostics.get("remote_status") == "RUNNING"
    assert err.diagnostics.get("llamaparse_job_id") == "pjb-xyz"
    assert "polling budget expired" in str(err)
    assert uploaded == {}


def test_auth_error_does_not_fallback() -> None:
    version, document = _rows(FileType.txt)
    storage, uploaded = _fake_storage(payload=b"hello\n\nworld\n")
    client = MagicMock()
    client.parse.side_effect = LlamaParseRequestError("invalid api key", status_code=401)

    with pytest.raises(DataPipelineError, match="authentication/configuration"):
        _run_stage(
            version,
            document,
            storage=storage,
            client=client,
            settings=_settings(llamaparse_fallback_to_local_ocr=True),
        )

    assert uploaded == {}
    client.parse.assert_called_once()


def test_unsupported_file_does_not_fallback() -> None:
    version, document = _rows(FileType.txt)
    storage, uploaded = _fake_storage(payload=b"hello\n\nworld\n")
    client = MagicMock()
    client.parse.side_effect = LlamaParseRequestError(
        "unsupported media type",
        status_code=422,
    )

    with pytest.raises(DataPipelineError, match="rejected the document"):
        _run_stage(
            version,
            document,
            storage=storage,
            client=client,
            settings=_settings(llamaparse_fallback_to_local_ocr=True),
        )

    assert uploaded == {}


def test_fallback_does_not_resubmit_llamaparse() -> None:
    """Handled fallback must call LlamaParse exactly once (no duplicate jobs)."""
    version, document = _rows(FileType.txt)
    storage, _ = _fake_storage(payload="Section A\n\nBody text here.\n".encode())
    client = MagicMock()
    client.parse.side_effect = LlamaParseTimeoutError(
        "budget",
        job_id="job-once",
        remote_status="RUNNING",
        client_timeout=True,
        budget_seconds=5,
    )

    _run_stage(
        version,
        document,
        storage=storage,
        client=client,
        settings=_settings(llamaparse_fallback_to_local_ocr=True),
    )
    assert client.parse.call_count == 1


def test_poll_timeout_single_job_submission_no_duplicate() -> None:
    """Adapter poll timeout: one upload + one job create; never re-submit parse job."""
    posts = {"files": 0, "parse": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/beta/files":
            posts["files"] += 1
            return httpx.Response(200, json={"id": "file-1"})
        if request.url.path == "/api/v2/parse":
            posts["parse"] += 1
            return httpx.Response(200, json={"id": "job-only"})
        if request.url.path.endswith("/cancel"):
            return httpx.Response(200, json={"status": "CANCELLED"})
        return httpx.Response(200, json=_result_payload("RUNNING"))

    client = _StubTransportClient(
        _settings(llamaparse_max_retries=3, llamaparse_timeout_seconds=1),
        handler,
    )
    with pytest.raises(LlamaParseTimeoutError):
        client.parse(data=b"bytes", filename="a.pdf", file_type=FileType.pdf)

    assert posts["files"] == 1
    assert posts["parse"] == 1
