# =============================================================================
# File: test_cleaning_normalize_stage.py
# Module/Service: Pipeline Worker — Cleaning & Normalize ([AI])
# Layer: Worker
# Purpose: Unit tests for stage_cleaning_normalize orchestration.
# Responsibilities:
#   - Load markdown from MinIO, clean, overwrite, refresh segments artifact
# Dependencies:
#   - pytest, unittest.mock
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: app.workers.stages.cleaning_normalize
# Important Notes: No live MinIO/Postgres in CI.
# =============================================================================

from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.models.documents import Document, DocumentVersion
from app.models.enums import DocumentVersionStatus, FileType
from app.workers.pipeline_errors import DataPipelineError
from app.workers.stages.cleaning_normalize import stage_cleaning_normalize

NOISY_MARKDOWN = """CONFIDENTIAL

# 1. Intro

Body paragraph.

Footer 2024
1

Footer 2024
2
"""


def _rows() -> tuple[DocumentVersion, Document]:
    version_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    version = DocumentVersion(
        id=version_id,
        document_id=doc_id,
        uploaded_by=uuid.uuid4(),
        version_number=1,
        storage_path="workspaces/ws/documents/doc/v1/report.pdf",
        markdown_storage_path="workspaces/ws/documents/doc/v1/document.md",
        file_size_bytes=1024,
        checksum_sha256="x",
        page_count=None,
        parser="llamaparse",
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
    return version, document


@contextmanager
def _session_for(version: DocumentVersion, document: Document):
    session = MagicMock()
    session.get.side_effect = lambda model, pk: {
        DocumentVersion: version,
        Document: document,
    }.get(model)
    yield session


def test_stage_cleans_markdown_and_refreshes_segments() -> None:
    version, document = _rows()
    uploaded: dict[str, bytes] = {}
    storage = MagicMock()
    storage.download_bytes.return_value = NOISY_MARKDOWN.encode("utf-8")

    def _upload(*, object_key: str, data: bytes, content_type: str = "") -> str:
        uploaded[object_key] = data
        return object_key

    storage.upload_bytes.side_effect = _upload

    module = "app.workers.stages.cleaning_normalize"
    with (
        patch(f"{module}.get_minio_storage", return_value=storage),
        patch(f"{module}.get_sync_session", lambda: _session_for(version, document)),
    ):
        meta = stage_cleaning_normalize(version.id)

    cleaned = uploaded[version.markdown_storage_path].decode("utf-8")
    assert "CONFIDENTIAL" not in cleaned
    assert "# 1. Intro" in cleaned
    assert meta["chars_before"] > meta["chars_after"]
    assert meta["lines_removed"] >= 1
    assert meta["markdown_storage_path"] == version.markdown_storage_path

    segments_key = "workspaces/ws/documents/doc/v1/.pipeline/ocr_segments.json"
    assert segments_key in uploaded
    payload = json.loads(uploaded[segments_key].decode("utf-8"))
    assert payload["segment_count"] == meta["segment_count"]
    assert payload["segments"]


def test_stage_fails_without_markdown_path() -> None:
    version, document = _rows()
    version.markdown_storage_path = None
    storage = MagicMock()

    module = "app.workers.stages.cleaning_normalize"
    with (
        patch(f"{module}.get_minio_storage", return_value=storage),
        patch(f"{module}.get_sync_session", lambda: _session_for(version, document)),
    ):
        with pytest.raises(DataPipelineError, match="markdown_storage_path missing"):
            stage_cleaning_normalize(version.id)

    storage.download_bytes.assert_not_called()
