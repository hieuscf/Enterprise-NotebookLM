# =============================================================================
# File: indexing.py
# Module/Service: Pipeline Worker — stage_indexing ([BE] / Elasticsearch BM25)
# Layer: Worker
# Purpose: Final ingestion stage — BM25 index document_chunks into Elasticsearch.
# Responsibilities:
#   - Delete prior ES docs for the version; bulk-index each chunk
#   - Return metadata (indexed count, duration_ms, shared index name)
# Dependencies:
#   - ElasticsearchBm25Adapter, KnowledgeSyncRepository, sync session
# Public Exports:
#   - stage_indexing
# Database/Table: document_chunks (read); ES index document_chunks (write)
# Related Modules: app.workers.pipeline (marks run completed + version ready after this)
# Important Notes:
#   - Shared ES index + workspace_id filter (aligned with Qdrant shared collection).
#   - Last stage in STAGE_ORDER — orchestration sets pipeline_runs=completed and
#     document_versions=ready when this returns successfully.
# =============================================================================

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

from app.adapters.elasticsearch_bm25 import EsConnectionError, get_elasticsearch_bm25
from app.db.sync_session import get_sync_session
from app.models.documents import Document, DocumentVersion
from app.repositories.knowledge import KnowledgeSyncRepository
from app.workers.stages.errors import DataPipelineError, TransientPipelineError


def stage_indexing(document_version_id: UUID) -> dict[str, Any]:
    """Index all chunks for a document version into the shared BM25 ES index.

    Args:
        document_version_id: Target ``document_versions.id``.

    Returns:
        Metadata for ``pipeline_stage_logs``: indexed count, duration, index name.
    """
    started = time.perf_counter()
    es = get_elasticsearch_bm25()

    with get_sync_session() as session:
        version = session.get(DocumentVersion, document_version_id)
        if version is None:
            raise DataPipelineError(f"document_version not found: {document_version_id}")
        document = session.get(Document, version.document_id)
        if document is None:
            raise DataPipelineError(f"document not found for version: {document_version_id}")

        knowledge = KnowledgeSyncRepository(session)
        chunks = knowledge.list_chunks_for_version(document_version_id)
        if not chunks:
            raise DataPipelineError(
                "No document_chunks found — run chunking before indexing"
            )

        docs = [
            {
                "chunk_id": str(c.id),
                "document_version_id": str(document_version_id),
                "workspace_id": str(document.workspace_id),
                "content": c.content,
                "page_number": c.page_number,
                "section_index": c.section_index,
                "section": c.section,
                "chunk_index": c.chunk_index,
            }
            for c in chunks
        ]

        try:
            es.delete_by_document_version(document_version_id)
            indexed = es.index_chunks(docs)
        except EsConnectionError as exc:
            raise TransientPipelineError(f"Elasticsearch connection failed: {exc}") from exc
        except Exception as exc:
            msg = str(exc).lower()
            if any(
                tok in msg
                for tok in ("timeout", "connection", "temporar", "429", "502", "503", "circuit")
            ):
                raise TransientPipelineError(f"Elasticsearch indexing failed: {exc}") from exc
            raise DataPipelineError(f"Elasticsearch indexing error: {exc}") from exc

        duration_ms = int((time.perf_counter() - started) * 1000)
        return {
            "document_version_id": str(document_version_id),
            "indexed_count": indexed,
            "chunk_count": len(chunks),
            "duration_ms": duration_ms,
            "elasticsearch_index": es.index_name,
            "index_strategy": "shared_index_workspace_filter",
        }
