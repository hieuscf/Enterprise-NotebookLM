# =============================================================================
# File: elasticsearch_bm25.py
# Module/Service: Pipeline Worker / Vector Retrieval (BM25 branch)
# Layer: Adapter
# Purpose: Elasticsearch BM25 indexer for document chunks (FR2 indexing stage).
# Responsibilities:
#   - Ensure index mapping; bulk-index chunk text for keyword retrieval
# Dependencies:
#   - elasticsearch client, app.core.config.Settings
# Public Exports:
#   - ElasticsearchBm25Adapter, get_elasticsearch_bm25
# Database/Table: N/A (search index; chunk text also in document_chunks)
# Related Modules: app.workers.pipeline (indexing stage)
# Important Notes: Runs in Celery alongside vector upsert — no LLM calls.
# =============================================================================

from __future__ import annotations

from functools import lru_cache
from typing import Any
from uuid import UUID

from elasticsearch import Elasticsearch, helpers

from app.core.config import Settings, get_settings


class ElasticsearchBm25Adapter:
    def __init__(self, settings: Settings) -> None:
        self._index = settings.elasticsearch_index
        self._client = Elasticsearch(settings.elasticsearch_url)

    def ensure_index(self) -> None:
        if self._client.indices.exists(index=self._index):
            return
        self._client.indices.create(
            index=self._index,
            mappings={
                "properties": {
                    "chunk_id": {"type": "keyword"},
                    "document_version_id": {"type": "keyword"},
                    "workspace_id": {"type": "keyword"},
                    "content": {"type": "text"},
                    "page_number": {"type": "integer"},
                    "chunk_index": {"type": "integer"},
                }
            },
        )

    def index_chunks(self, docs: list[dict[str, Any]]) -> int:
        if not docs:
            return 0
        self.ensure_index()
        actions = [
            {
                "_index": self._index,
                "_id": doc["chunk_id"],
                "_source": doc,
            }
            for doc in docs
        ]
        success, _errors = helpers.bulk(self._client, actions, raise_on_error=False)
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
