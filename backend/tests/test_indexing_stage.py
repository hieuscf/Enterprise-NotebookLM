# =============================================================================
# File: test_indexing_stage.py
# Module/Service: Pipeline Worker — Indexing BM25 ([BE])
# Layer: Worker
# Purpose: Unit tests for FR2 Step 6 Elasticsearch indexing stage (mocked I/O).
# Responsibilities:
#   - Verify chunk→ES docs include workspace/version/section; metadata fields
# Dependencies:
#   - pytest, fakes for ES/DB
# Public Exports:
#   - N/A
# Database/Table: N/A (fakes)
# Related Modules: app.workers.stages.indexing, app.adapters.elasticsearch_bm25
# Important Notes: No live Elasticsearch in CI.
# =============================================================================

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.models.documents import Document, DocumentVersion
from app.models.enums import DocumentVersionStatus, FileType
from app.models.knowledge import DocumentChunk
from app.workers.stages.errors import DataPipelineError, TransientPipelineError
from app.workers.stages.indexing import stage_indexing


def test_stage_indexing_bulk_indexes_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    version_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    version = DocumentVersion(
        id=version_id,
        document_id=doc_id,
        uploaded_by=uuid.uuid4(),
        version_number=1,
        storage_path="workspaces/ws/documents/doc/v1/a.txt",
        file_size_bytes=10,
        checksum_sha256="x",
        page_count=1,
        status=DocumentVersionStatus.processing,
        is_current=True,
        created_at=datetime.now(UTC),
    )
    document = Document(
        id=doc_id,
        workspace_id=workspace_id,
        current_version_id=version_id,
        title="T",
        file_type=FileType.txt,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    chunk = DocumentChunk(
        id=uuid.uuid4(),
        document_version_id=version_id,
        chunk_index=0,
        content="BM25 keyword retrieval text",
        page_number=2,
        section="Intro",
        token_count=5,
        created_at=datetime.now(UTC),
    )

    class FakeKnowledge:
        def list_chunks_for_version(self, _vid: uuid.UUID) -> list[DocumentChunk]:
            return [chunk]

    es = MagicMock()
    es.index_name = "document_chunks"
    es.index_chunks.return_value = 1

    @contextmanager
    def _session():
        session = MagicMock()

        def _get(model: Any, pk: Any) -> Any:
            if model is DocumentVersion:
                return version
            if model is Document:
                return document
            return None

        session.get.side_effect = _get
        yield session

    monkeypatch.setattr("app.workers.stages.indexing.get_sync_session", _session)
    monkeypatch.setattr("app.workers.stages.indexing.get_elasticsearch_bm25", lambda: es)
    monkeypatch.setattr(
        "app.workers.stages.indexing.KnowledgeSyncRepository",
        lambda _s: FakeKnowledge(),
    )

    meta = stage_indexing(version_id)
    assert meta["indexed_count"] == 1
    assert meta["chunk_count"] == 1
    assert meta["elasticsearch_index"] == "document_chunks"
    assert meta["index_strategy"] == "shared_index_workspace_filter"
    assert isinstance(meta["duration_ms"], int)
    assert meta["duration_ms"] >= 0
    assert "stub" not in meta

    es.delete_by_document_version.assert_called_once_with(version_id)
    es.index_chunks.assert_called_once()
    docs = es.index_chunks.call_args.args[0]
    assert docs[0]["workspace_id"] == str(workspace_id)
    assert docs[0]["document_version_id"] == str(version_id)
    assert docs[0]["chunk_id"] == str(chunk.id)
    assert docs[0]["content"] == "BM25 keyword retrieval text"
    assert docs[0]["page_number"] == 2
    assert docs[0]["section"] == "Intro"
    assert docs[0]["chunk_index"] == 0


def test_stage_indexing_requires_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    version_id = uuid.uuid4()
    version = DocumentVersion(
        id=version_id,
        document_id=uuid.uuid4(),
        uploaded_by=uuid.uuid4(),
        version_number=1,
        storage_path="x",
        file_size_bytes=1,
        checksum_sha256="x",
        page_count=1,
        status=DocumentVersionStatus.processing,
        is_current=True,
        created_at=datetime.now(UTC),
    )
    document = Document(
        id=version.document_id,
        workspace_id=uuid.uuid4(),
        title="T",
        file_type=FileType.txt,
        current_version_id=version_id,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    class FakeKnowledge:
        def list_chunks_for_version(self, _vid: uuid.UUID) -> list[DocumentChunk]:
            return []

    @contextmanager
    def _session():
        session = MagicMock()

        def _get(model: Any, pk: Any) -> Any:
            if model is DocumentVersion:
                return version
            if model is Document:
                return document
            return None

        session.get.side_effect = _get
        yield session

    monkeypatch.setattr("app.workers.stages.indexing.get_sync_session", _session)
    monkeypatch.setattr(
        "app.workers.stages.indexing.KnowledgeSyncRepository",
        lambda _s: FakeKnowledge(),
    )
    monkeypatch.setattr(
        "app.workers.stages.indexing.get_elasticsearch_bm25",
        lambda: MagicMock(index_name="document_chunks"),
    )

    with pytest.raises(DataPipelineError, match="No document_chunks"):
        stage_indexing(version_id)


def test_stage_indexing_maps_connection_to_transient(monkeypatch: pytest.MonkeyPatch) -> None:
    version_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    version = DocumentVersion(
        id=version_id,
        document_id=doc_id,
        uploaded_by=uuid.uuid4(),
        version_number=1,
        storage_path="x",
        file_size_bytes=1,
        checksum_sha256="x",
        page_count=1,
        status=DocumentVersionStatus.processing,
        is_current=True,
        created_at=datetime.now(UTC),
    )
    document = Document(
        id=doc_id,
        workspace_id=uuid.uuid4(),
        title="T",
        file_type=FileType.txt,
        current_version_id=version_id,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    chunk = DocumentChunk(
        id=uuid.uuid4(),
        document_version_id=version_id,
        chunk_index=0,
        content="x",
        page_number=1,
        section=None,
        token_count=1,
        created_at=datetime.now(UTC),
    )

    class FakeKnowledge:
        def list_chunks_for_version(self, _vid: uuid.UUID) -> list[DocumentChunk]:
            return [chunk]

    es = MagicMock()
    es.index_name = "document_chunks"
    es.delete_by_document_version.side_effect = RuntimeError("connection timeout to ES")

    @contextmanager
    def _session():
        session = MagicMock()

        def _get(model: Any, pk: Any) -> Any:
            if model is DocumentVersion:
                return version
            if model is Document:
                return document
            return None

        session.get.side_effect = _get
        yield session

    monkeypatch.setattr("app.workers.stages.indexing.get_sync_session", _session)
    monkeypatch.setattr("app.workers.stages.indexing.get_elasticsearch_bm25", lambda: es)
    monkeypatch.setattr(
        "app.workers.stages.indexing.KnowledgeSyncRepository",
        lambda _s: FakeKnowledge(),
    )

    with pytest.raises(TransientPipelineError, match="Elasticsearch"):
        stage_indexing(version_id)


def test_adapter_builds_shared_index_actions() -> None:
    """Unit-test adapter bulk payload shape without a live cluster."""
    from app.adapters.elasticsearch_bm25 import ElasticsearchBm25Adapter
    from app.core.config import Settings

    adapter = ElasticsearchBm25Adapter(
        Settings(elasticsearch_url="http://localhost:9200", elasticsearch_index="document_chunks")
    )
    client = MagicMock()
    client.indices.exists.return_value = True
    adapter._client = client

    captured: list[Any] = []

    def _bulk(_client: Any, actions: Any, **_kwargs: Any) -> tuple[int, list[Any]]:
        captured.extend(list(actions))
        return (len(captured), [])

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("app.adapters.elasticsearch_bm25.helpers.bulk", _bulk)
    try:
        n = adapter.index_chunks(
            [
                {
                    "chunk_id": "c1",
                    "document_version_id": "v1",
                    "workspace_id": "w1",
                    "content": "hello",
                    "page_number": 1,
                    "section": "S",
                    "chunk_index": 0,
                }
            ]
        )
    finally:
        monkeypatch.undo()

    assert n == 1
    assert captured[0]["_id"] == "c1"
    assert captured[0]["_source"]["workspace_id"] == "w1"
    assert captured[0]["_source"]["section"] == "S"
    assert captured[0]["_index"] == "document_chunks"
