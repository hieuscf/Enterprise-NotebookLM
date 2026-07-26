# =============================================================================
# File: qdrant_store.py
# Module/Service: Pipeline Worker / Vector Retrieval
# Layer: Adapter
# Purpose: Qdrant client for chunk vector upsert (FR2 Dual-level Vector Index).
# Responsibilities:
#   - Ensure collection exists with configured dimension
#   - Upsert chunk vectors; return vector point ids for embeddings.vector_id
# Dependencies:
#   - qdrant-client, app.core.config.Settings
# Public Exports:
#   - QdrantStoreAdapter, get_qdrant_store
# Database/Table: embeddings (metadata only — vectors live here)
# Related Modules: app.ai.embedding, app.workers.pipeline
# Important Notes: embeddings table must not store raw vectors.
# =============================================================================

from __future__ import annotations

from functools import lru_cache
from typing import Any
from uuid import UUID

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.core.config import Settings, get_settings


class QdrantStoreAdapter:
    def __init__(self, settings: Settings) -> None:
        self._collection = settings.qdrant_collection
        self._dimension = settings.embedding_dimension
        self._client = QdrantClient(url=settings.qdrant_url, prefer_grpc=False)

    def ensure_collection(self) -> None:
        names = {c.name for c in self._client.get_collections().collections}
        if self._collection in names:
            return
        self._client.create_collection(
            collection_name=self._collection,
            vectors_config=qmodels.VectorParams(
                size=self._dimension,
                distance=qmodels.Distance.COSINE,
            ),
        )

    def upsert_chunk_vector(
        self,
        *,
        point_id: str,
        vector: list[float],
        payload: dict[str, Any],
    ) -> str:
        self.ensure_collection()
        self._client.upsert(
            collection_name=self._collection,
            points=[
                qmodels.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload,
                )
            ],
        )
        return point_id

    def delete_by_document_version(self, document_version_id: UUID) -> None:
        self.ensure_collection()
        self._client.delete(
            collection_name=self._collection,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="document_version_id",
                            match=qmodels.MatchValue(value=str(document_version_id)),
                        )
                    ]
                )
            ),
        )

    @property
    def collection_name(self) -> str:
        return self._collection


@lru_cache
def get_qdrant_store() -> QdrantStoreAdapter:
    return QdrantStoreAdapter(get_settings())
