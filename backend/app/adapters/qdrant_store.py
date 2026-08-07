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
#   - Vector search uses query_points (Client.search removed in qdrant-client
#     1.16+); falls back to search when present for older clients.
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
        # check_compatibility=False: server image may lag pinned client minor;
        # adapter uses query_points (search removed in qdrant-client >=1.16).
        self._client = QdrantClient(
            url=settings.qdrant_url,
            prefer_grpc=False,
            check_compatibility=False,
        )

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

    def search_similar(
        self,
        *,
        workspace_id: UUID,
        query_vector: list[float],
        top_k: int = 20,
        kind: str = "chunk",
    ) -> list[dict[str, Any]]:
        """Cosine similarity search filtered by ``workspace_id`` (and optional kind).

        Returns:
            List of dicts including ``score``, ``payload``, and common id fields
            (``chunk_id``, ``cache_id``, …) when present in the payload.
        """
        self.ensure_collection()
        must: list[qmodels.FieldCondition] = [
            qmodels.FieldCondition(
                key="workspace_id",
                match=qmodels.MatchValue(value=str(workspace_id)),
            )
        ]
        if kind:
            must.append(
                qmodels.FieldCondition(
                    key="kind",
                    match=qmodels.MatchValue(value=kind),
                )
            )
        query_filter = qmodels.Filter(must=must)
        limit = max(1, top_k)
        # qdrant-client >=1.16 removed Client.search in favor of query_points.
        if hasattr(self._client, "query_points"):
            response = self._client.query_points(
                collection_name=self._collection,
                query=query_vector,
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
            )
            hits = list(response.points or [])
        else:
            hits = list(
                self._client.search(  # type: ignore[attr-defined]
                    collection_name=self._collection,
                    query_vector=query_vector,
                    query_filter=query_filter,
                    limit=limit,
                    with_payload=True,
                )
            )
        results: list[dict[str, Any]] = []
        for hit in hits:
            payload = dict(hit.payload or {})
            chunk_id = payload.get("chunk_id") or (
                str(hit.id) if kind == "chunk" else None
            )
            results.append(
                {
                    "point_id": str(hit.id),
                    "chunk_id": str(chunk_id) if chunk_id else None,
                    "cache_id": payload.get("cache_id"),
                    "document_version_id": payload.get("document_version_id"),
                    "document_id": payload.get("document_id"),
                    "score": float(hit.score or 0.0),
                    "payload": payload,
                }
            )
        return results

    @property
    def collection_name(self) -> str:
        return self._collection


@lru_cache
def get_qdrant_store() -> QdrantStoreAdapter:
    return QdrantStoreAdapter(get_settings())
