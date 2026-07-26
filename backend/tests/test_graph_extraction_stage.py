# =============================================================================
# File: test_graph_extraction_stage.py
# Module/Service: Pipeline Worker — Graph & Topic Extraction ([AI])
# Layer: Worker
# Purpose: Unit tests for FR2 Step 5 graph_extraction stage (mocked I/O).
# Responsibilities:
#   - Heuristic LightRAG path persists entities/topics; metadata includes cost fields
# Dependencies:
#   - pytest, fakes for Qdrant/Neo4j/DB
# Public Exports:
#   - N/A
# Database/Table: N/A (fakes)
# Related Modules: app.workers.stages.graph_extraction, app.ai.lightrag_extraction
# Important Notes: GRAPH_LLM disabled — no Anthropic calls in CI.
# =============================================================================

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.ai.lightrag_extraction import extract_lightrag_knowledge
from app.ai.chunking import TextChunk
from app.core.config import Settings
from app.models.documents import Document, DocumentVersion
from app.models.enums import DocumentVersionStatus, FileType
from app.models.knowledge import DocumentChunk, Embedding, Entity, EntityRelation, Topic
from app.workers.stages.errors import DataPipelineError
from app.workers.stages.graph_extraction import stage_graph_extraction


def _chunk(
    *,
    version_id: uuid.UUID,
    index: int,
    content: str,
    section: str | None = None,
) -> DocumentChunk:
    return DocumentChunk(
        id=uuid.uuid4(),
        document_version_id=version_id,
        chunk_index=index,
        content=content,
        page_number=1,
        section=section,
        token_count=20,
        created_at=datetime.now(UTC),
    )


def test_heuristic_lightrag_extract_without_llm() -> None:
    chunks = [
        TextChunk(
            chunk_index=0,
            content="Acme Corporation partners with LightRAG Core Engine.",
            page_number=1,
            section="Overview",
            heading="Overview",
            paragraph_index=0,
            start_offset=0,
            end_offset=50,
            token_count=10,
            metadata={},
        )
    ]
    settings = Settings(graph_llm_enabled=False, anthropic_api_key=None)
    result = extract_lightrag_knowledge(chunks, settings=settings)
    assert result.llm_used is False
    assert result.estimated_cost_usd == 0.0
    assert isinstance(result.entities, list)
    assert len(result.topics) >= 1


def test_stage_graph_extraction_persists_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    version_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    doc_id = uuid.uuid4()
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
        title="Doc",
        file_type=FileType.txt,
        current_version_id=version_id,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    chunks = [
        _chunk(
            version_id=version_id,
            index=0,
            content="Acme Corporation uses LightRAG for Dual-level Graph retrieval.",
            section="Overview",
        ),
        _chunk(
            version_id=version_id,
            index=1,
            content="Vector Retrieval indexes Document Chunks in Qdrant.",
            section="Retrieval",
        ),
    ]

    entities: list[Entity] = []
    relations: list[EntityRelation] = []
    topics: list[Topic] = []
    topic_links: list[tuple[uuid.UUID, uuid.UUID]] = []

    class FakeKnowledge:
        def list_chunks_for_version(self, _vid: uuid.UUID) -> list[DocumentChunk]:
            return chunks

        def clear_version_graph_artifacts(self, _vid: uuid.UUID) -> None:
            return None

        def create_entity(self, **kwargs: Any) -> Entity:
            row = Entity(
                id=uuid.uuid4(),
                workspace_id=kwargs["workspace_id"],
                source_version_id=kwargs["source_version_id"],
                name=kwargs["name"],
                type=kwargs["type_"],
                description=kwargs.get("description"),
                created_at=datetime.now(UTC),
            )
            entities.append(row)
            return row

        def create_relation(self, **kwargs: Any) -> EntityRelation:
            row = EntityRelation(
                id=uuid.uuid4(),
                source_entity_id=kwargs["source_entity_id"],
                target_entity_id=kwargs["target_entity_id"],
                relation_type=kwargs["relation_type"],
                description=kwargs.get("description"),
                weight=kwargs.get("weight"),
            )
            relations.append(row)
            return row

        def create_embedding(self, **kwargs: Any) -> Embedding:
            return Embedding(
                id=uuid.uuid4(),
                model_name=kwargs["model_name"],
                dimension=kwargs["dimension"],
                vector_store=kwargs["vector_store"],
                vector_id=kwargs["vector_id"],
                index_name=kwargs["index_name"],
                created_at=datetime.now(UTC),
            )

        def create_topic(self, **kwargs: Any) -> Topic:
            row = Topic(
                id=uuid.uuid4(),
                workspace_id=kwargs["workspace_id"],
                name=kwargs["name"],
                level=kwargs["level"],
                summary=kwargs.get("summary"),
                parent_topic_id=kwargs.get("parent_topic_id"),
                embedding_id=kwargs.get("embedding_id"),
            )
            topics.append(row)
            return row

        def link_topic_chunk(self, topic_id: uuid.UUID, chunk_id: uuid.UUID) -> None:
            topic_links.append((topic_id, chunk_id))

    qdrant = MagicMock()
    qdrant.collection_name = "document_chunks"
    qdrant.upsert_chunk_vectors.return_value = 1
    neo4j = MagicMock()

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

    monkeypatch.setattr("app.workers.stages.graph_extraction.get_sync_session", _session)
    monkeypatch.setattr("app.workers.stages.graph_extraction.get_qdrant_store", lambda: qdrant)
    monkeypatch.setattr("app.workers.stages.graph_extraction.get_neo4j_graph", lambda: neo4j)
    monkeypatch.setattr(
        "app.workers.stages.graph_extraction.KnowledgeSyncRepository",
        lambda _s: FakeKnowledge(),
    )
    monkeypatch.setattr(
        "app.workers.stages.graph_extraction.get_settings",
        lambda: Settings(
            graph_llm_enabled=False,
            anthropic_api_key=None,
            embedding_provider="local",
            embedding_model_name="local-hash-embedding-v1",
            embedding_dimension=384,
        ),
    )

    meta = stage_graph_extraction(version_id)
    assert meta["llm_used"] is False
    assert meta["estimated_cost_usd"] == 0.0
    assert "llm_cost_note" in meta
    assert meta["entity_count"] == len(entities)
    assert meta["topic_count"] == len(topics)
    assert meta["topic_count"] >= 1
    assert topics[0].embedding_id is not None
    assert any(t.level == 0 for t in topics)
    assert topic_links
    qdrant.delete_by_document_version.assert_called_once_with(version_id, kind="topic")
    qdrant.upsert_chunk_vectors.assert_called_once()
    payload = qdrant.upsert_chunk_vectors.call_args.args[0][0]["payload"]
    assert payload["kind"] == "topic"
    assert payload["workspace_id"] == str(workspace_id)
    neo4j.upsert_entities_and_relations.assert_called()


def test_stage_graph_extraction_requires_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
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
        title="Doc",
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

    monkeypatch.setattr("app.workers.stages.graph_extraction.get_sync_session", _session)
    monkeypatch.setattr(
        "app.workers.stages.graph_extraction.KnowledgeSyncRepository",
        lambda _s: FakeKnowledge(),
    )
    monkeypatch.setattr(
        "app.workers.stages.graph_extraction.get_qdrant_store",
        lambda: MagicMock(),
    )

    with pytest.raises(DataPipelineError, match="No document_chunks"):
        stage_graph_extraction(version_id)
