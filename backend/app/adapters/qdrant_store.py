# =============================================================================
# File: qdrant_store.py
# Module/Service: Pipeline Worker / Vector Retrieval
# Layer: Adapter
# Purpose: Qdrant client for chunk vectors — shared collection + workspace filter.
# Responsibilities:
#   - Ensure one shared collection; upsert points with workspace_id payload
#   - Batch upsert; delete by document_version_id
# Dependencies:
#   - qdrant-client, app.core.config.Settings
# Public Exports:
#   - QdrantStoreAdapter, get_qdrant_store
# Database/Table: embeddings (metadata only — vectors live here)
# Related Modules: app.workers.stages.embedding
# Important Notes:
#   - Ops choice: ONE shared collection (settings.qdrant_collection) for all
#     workspaces. Multi-tenant isolation uses payload.workspace_id filter at
#     query time — simpler than per-workspace collections.
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
        # Shared collection for all tenants; filter by payload.workspace_id.
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
        self.upsert_chunk_vectors(
            [
                {"point_id": point_id, "vector": vector, "payload": payload},
            ]
        )
        return point_id

    def upsert_chunk_vectors(self, points: list[dict[str, Any]]) -> int:
        """Batch upsert points into the shared collection.

        Each item: ``{point_id, vector, payload}``. Payload SHOULD include
        ``workspace_id`` and ``document_version_id`` for tenant filters.
        """
        if not points:
            return 0
        self.ensure_collection()
        self._client.upsert(
            collection_name=self._collection,
            points=[
                qmodels.PointStruct(
                    id=p["point_id"],
                    vector=p["vector"],
                    payload=p.get("payload") or {},
                )
                for p in points
            ],
        )
        return len(points)

    def delete_by_document_version(
        self,
        document_version_id: UUID,
        *,
        kind: str | None = None,
    ) -> None:
        """Delete points for a version; optionally restrict by payload ``kind``.

        Use ``kind="chunk"`` when re-embedding so topic vectors (kind=topic)
        written by graph_extraction are preserved.
        """
        self.ensure_collection()
        must: list[qmodels.FieldCondition] = [
            qmodels.FieldCondition(
                key="document_version_id",
                match=qmodels.MatchValue(value=str(document_version_id)),
            )
        ]
        if kind is not None:
            must.append(
                qmodels.FieldCondition(
                    key="kind",
                    match=qmodels.MatchValue(value=kind),
                )
            )
        self._client.delete(
            collection_name=self._collection,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(must=must)
            ),
        )

    @property
    def collection_name(self) -> str:
        return self._collection


@lru_cache
def get_qdrant_store() -> QdrantStoreAdapter:
    return QdrantStoreAdapter(get_settings())
