# =============================================================================
# File: elasticsearch_bm25.py
# Module/Service: Pipeline Worker / Vector Retrieval (BM25 branch)
# Layer: Adapter
# Purpose: Elasticsearch BM25 indexer for document chunks (FR2 indexing stage).
# Responsibilities:
#   - Ensure shared index mapping; bulk-index chunk text for keyword retrieval
#   - Delete prior version docs before re-index (idempotent re-runs)
# Dependencies:
#   - elasticsearch client, app.core.config.Settings
# Public Exports:
#   - ElasticsearchBm25Adapter, get_elasticsearch_bm25
# Database/Table: N/A (search index; chunk text also in document_chunks)
# Related Modules: app.workers.stages.indexing, app.adapters.qdrant_store
# Important Notes:
#   - ONE shared index (settings.elasticsearch_index) for all workspaces —
#     same ops choice as Qdrant shared collection. Filter by workspace_id.
#   - No LLM calls from this adapter.
# =============================================================================

from __future__ import annotations

from functools import lru_cache
from typing import Any
from uuid import UUID

from elasticsearch import Elasticsearch, helpers
from elasticsearch.exceptions import ApiError, ConnectionError as EsConnectionError, TransportError

from app.core.config import Settings, get_settings

_INDEX_MAPPINGS: dict[str, Any] = {
    "properties": {
        "chunk_id": {"type": "keyword"},
        "document_version_id": {"type": "keyword"},
        "workspace_id": {"type": "keyword"},
        "content": {"type": "text"},
        "page_number": {"type": "integer"},
        "section": {"type": "keyword"},
        "chunk_index": {"type": "integer"},
    }
}


class ElasticsearchBm25Adapter:
    def __init__(self, settings: Settings) -> None:
        # Shared index for all tenants; filter by payload/field workspace_id.
        self._index = settings.elasticsearch_index
        self._client = Elasticsearch(settings.elasticsearch_url)

    def ensure_index(self) -> None:
        if self._client.indices.exists(index=self._index):
            # Best-effort add newer fields (e.g. section) on existing indexes.
            try:
                self._client.indices.put_mapping(index=self._index, properties=_INDEX_MAPPINGS["properties"])
            except (ApiError, TransportError):
                pass
            return
        self._client.indices.create(
            index=self._index,
            mappings=_INDEX_MAPPINGS,
        )

    def index_chunks(self, docs: list[dict[str, Any]]) -> int:
        """Bulk-index chunk documents. ``_id`` = ``chunk_id`` for idempotent upserts.

        Each doc SHOULD include: chunk_id, document_version_id, workspace_id,
        content, page_number, section, chunk_index.
        """
        if not docs:
            return 0
        self.ensure_index()
        actions = [
            {
                "_index": self._index,
                "_id": str(doc["chunk_id"]),
                "_source": {
                    "chunk_id": str(doc["chunk_id"]),
                    "document_version_id": str(doc["document_version_id"]),
                    "workspace_id": str(doc["workspace_id"]),
                    "content": doc.get("content") or "",
                    "page_number": doc.get("page_number"),
                    "section": doc.get("section"),
                    "chunk_index": doc.get("chunk_index"),
                },
            }
            for doc in docs
        ]
        success, errors = helpers.bulk(
            self._client,
            actions,
            raise_on_error=False,
            refresh=True,
        )
        if errors:
            # Surface first error so the stage can classify transient vs data.
            first = errors[0] if isinstance(errors, list) else errors
            raise RuntimeError(f"Elasticsearch bulk indexing errors: {first}")
        return int(success)

    def delete_by_document_version(self, document_version_id: UUID) -> None:
        self.ensure_index()
        self._client.delete_by_query(
            index=self._index,
            query={"term": {"document_version_id": str(document_version_id)}},
            refresh=True,
            conflicts="proceed",
        )

    @property
    def index_name(self) -> str:
        return self._index


@lru_cache
def get_elasticsearch_bm25() -> ElasticsearchBm25Adapter:
    return ElasticsearchBm25Adapter(get_settings())


# Re-export connection errors for stage classification.
__all__ = [
    "ElasticsearchBm25Adapter",
    "EsConnectionError",
    "get_elasticsearch_bm25",
]
