# =============================================================================
# File: test_ocr.py
# Module/Service: Pipeline Worker — OCR & Cleaning ([AI])
# Layer: Service
# Purpose: Unit tests for FR2 Step 3 OCR segments, cleaning, empty-text fail.
# Responsibilities:
#   - TXT/DOCX-like segments; EmptyOcrError; stage metadata + artifact save
# Dependencies:
#   - pytest, app.ai.ocr, app.workers.stages.ocr_cleaning (mocked I/O)
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: app.ai.ocr, app.workers.artifacts
# Important Notes: No live MinIO/Postgres in CI.
# =============================================================================

from __future__ import annotations

import io
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from app.ai.ocr import EmptyOcrError, run_ocr_cleaning
from app.models.documents import Document, DocumentVersion
from app.models.enums import DocumentVersionStatus, FileType
from app.workers.artifacts import OCR_SEGMENTS_ARTIFACT, pipeline_artifact_key
from app.workers.stages.errors import DataPipelineError
from app.workers.stages.ocr_cleaning import stage_ocr_cleaning


def test_txt_produces_ordered_segments() -> None:
    data = b"First paragraph about NotebookLM.\n\nSecond paragraph about LightRAG.\n"
    result = run_ocr_cleaning(file_type=FileType.txt, data=data)
    assert result.page_count == 1
    assert result.char_count > 0
    assert len(result.segments) >= 2
    assert result.segments[0].order_index == 0
    assert result.segments[1].order_index == 1
    assert "NotebookLM" in result.segments[0].text
    # Legacy adapter for chunking
    assert len(result.pages) == len(result.segments)


def test_empty_text_raises_empty_ocr_error() -> None:
    with pytest.raises(EmptyOcrError, match="scanned PDF|text layer"):
        run_ocr_cleaning(file_type=FileType.txt, data=b"   \n\n\t  ")


def test_whitespace_and_encoding_cleaned() -> None:
    raw = "Hello\u00a0World\ufeff\n\n\nNext   line".encode("utf-8")
    result = run_ocr_cleaning(file_type=FileType.txt, data=raw)
    joined = " ".join(s.text for s in result.segments)
    assert "\ufeff" not in joined
    assert "  " not in joined
    assert "Hello World" in joined


def test_pipeline_artifact_key() -> None:
    key = pipeline_artifact_key(
        "workspaces/ws/documents/doc/v1/report.pdf",
        OCR_SEGMENTS_ARTIFACT,
    )
    assert key == "workspaces/ws/documents/doc/v1/.pipeline/ocr_segments.json"


def test_stage_ocr_cleaning_persists_artifact_and_metadata() -> None:
    version_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    version = DocumentVersion(
        id=version_id,
        document_id=doc_id,
        uploaded_by=uuid.uuid4(),
        version_number=1,
        storage_path="workspaces/ws/documents/doc/v1/a.txt",
        file_size_bytes=20,
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
        title="A",
        file_type=FileType.txt,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    fake_storage = MagicMock()
    fake_storage.download_bytes.return_value = b"Enterprise NotebookLM segment one.\n\nTwo."
    uploaded: dict[str, bytes] = {}

    def _upload(*, object_key: str, data: bytes, content_type: str = "") -> str:
        uploaded[object_key] = data
        return object_key

    fake_storage.upload_bytes.side_effect = _upload

    @contextmanager
    def _session():
        session = MagicMock()
        session.get.side_effect = lambda model, pk: {
            DocumentVersion: version,
            Document: document,
        }.get(model)
        yield session

    with (
        patch("app.workers.stages.ocr_cleaning.get_minio_storage", return_value=fake_storage),
        patch("app.workers.stages.ocr_cleaning.get_sync_session", _session),
    ):
        meta = stage_ocr_cleaning(version_id)

    assert meta["page_count"] == 1
    assert meta["segment_count"] >= 1
    assert meta["char_count"] > 0
    assert meta["output_bytes"] > 0
    assert "duration_ms" in meta
    assert meta["artifact_key"].endswith(".pipeline/ocr_segments.json")
    assert meta["artifact_key"] in uploaded


def test_stage_ocr_empty_file_fails_with_data_error() -> None:
    version_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    version = DocumentVersion(
        id=version_id,
        document_id=doc_id,
        uploaded_by=uuid.uuid4(),
        version_number=1,
        storage_path="workspaces/ws/documents/doc/v1/empty.txt",
        file_size_bytes=0,
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
        title="Empty",
        file_type=FileType.txt,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    fake_storage = MagicMock()
    fake_storage.download_bytes.return_value = b"\n\n   "

    @contextmanager
    def _session():
        session = MagicMock()
        session.get.side_effect = lambda model, pk: {
            DocumentVersion: version,
            Document: document,
        }.get(model)
        yield session

    with (
        patch("app.workers.stages.ocr_cleaning.get_minio_storage", return_value=fake_storage),
        patch("app.workers.stages.ocr_cleaning.get_sync_session", _session),
        pytest.raises(DataPipelineError, match="text layer|No extractable text"),
    ):
        stage_ocr_cleaning(version_id)


def test_docx_keeps_heading_as_section() -> None:
    from docx import Document as DocxDocument

    buf = io.BytesIO()
    doc = DocxDocument()
    doc.add_heading("Introduction", level=1)
    doc.add_paragraph("Body under introduction.")
    doc.save(buf)
    result = run_ocr_cleaning(file_type=FileType.docx, data=buf.getvalue())
    assert any(s.section == "Introduction" for s in result.segments)
    assert any("Body under introduction" in s.text for s in result.segments)
