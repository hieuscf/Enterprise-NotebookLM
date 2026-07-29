# =============================================================================
# File: test_chunk_embed_stages.py
# Module/Service: Pipeline Worker — Chunking & Embedding ([AI])
# Layer: Worker
# Purpose: Unit tests for FR2 Step 4 chunking + embedding stages (mocked I/O).
# Responsibilities:
#   - Segment→chunk insert metadata; embedding batch + Qdrant payloads
# Dependencies:
#   - pytest, fakes for MinIO/Qdrant/DB
# Public Exports:
#   - N/A
# Database/Table: N/A (fakes)
# Related Modules: app.workers.stages.embedding
# Important Notes: Uses local hash embedding provider (no remote API in CI).
# =============================================================================

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.ai.chunking import run_chunking_from_segments
from app.ai.tokens import count_tokens, split_text_by_tokens
from app.models.documents import Document, DocumentVersion
from app.models.enums import DocumentVersionStatus, FileType, VectorStore
from app.models.knowledge import DocumentChunk, Embedding
from app.workers.stages.embedding import stage_embedding


def test_split_text_by_tokens_applies_overlap() -> None:
    text = " ".join(f"word{i}" for i in range(200))
    parts = split_text_by_tokens(text, max_tokens=40, overlap_ratio=0.15)
    assert len(parts) > 1
    # Overlap: some content from end of first window appears in second.
    assert any(tok in parts[1] for tok in parts[0].split()[-5:])


def test_run_chunking_from_segments_preserves_section_boundary() -> None:
    segments = [
        {"text": "Intro paragraph one.", "page_number": 1, "section": "Intro", "order_index": 0},
        {"text": "Intro paragraph two.", "page_number": 1, "section": "Intro", "order_index": 1},
        {"text": "Body paragraph.", "page_number": 2, "section": "Body", "order_index": 2},
    ]
    chunks = run_chunking_from_segments(segments, max_tokens=512, overlap_ratio=0.12)
    assert len(chunks) >= 2
    sections = {c.section for c in chunks}
    assert "Intro" in sections
    assert "Body" in sections
    # No chunk mixes Intro + Body text across section boundary packing.
    for c in chunks:
        if c.section == "Intro":
            assert "Body paragraph" not in c.content


def test_stage_embedding_batch_updates_embedding_id(monkeypatch: pytest.MonkeyPatch) -> None:
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
        content="Hello embedding world",
        page_number=1,
        section="S",
        token_count=count_tokens("Hello embedding world"),
        embedding_id=None,
        created_at=datetime.now(UTC),
    )

    class FakeKnowledge:
        def list_chunks_for_version(self, _vid: uuid.UUID) -> list[DocumentChunk]:
            return [chunk]

        def create_embedding(self, **kwargs: Any) -> Embedding:
            assert kwargs["vector_store"] == VectorStore.qdrant
            return Embedding(
                id=uuid.uuid4(),
                model_name=kwargs["model_name"],
                dimension=kwargs["dimension"],
                vector_store=kwargs["vector_store"],
                vector_id=kwargs["vector_id"],
                index_name=kwargs["index_name"],
                created_at=datetime.now(UTC),
            )

        def attach_chunk_embedding(self, c: DocumentChunk, embedding_id: uuid.UUID) -> None:
            c.embedding_id = embedding_id

    qdrant = MagicMock()
    qdrant.collection_name = "document_chunks"
    qdrant.upsert_chunk_vectors.return_value = 1

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

    monkeypatch.setattr("app.workers.stages.embedding.get_sync_session", _session)
    monkeypatch.setattr("app.workers.stages.embedding.get_qdrant_store", lambda: qdrant)
    monkeypatch.setattr(
        "app.workers.stages.embedding.KnowledgeSyncRepository",
        lambda _s: FakeKnowledge(),
    )

    meta = stage_embedding(version_id)
    assert meta["embedded_count"] == 1
    assert meta["qdrant_collection"] == "document_chunks"
    assert chunk.embedding_id is not None
    qdrant.upsert_chunk_vectors.assert_called_once()
    payload = qdrant.upsert_chunk_vectors.call_args.args[0][0]["payload"]
    assert payload["workspace_id"] == str(workspace_id)
    assert payload["section"] == "S"
    assert payload["kind"] == "chunk"
    qdrant.delete_by_document_version.assert_called_once_with(version_id, kind="chunk")
