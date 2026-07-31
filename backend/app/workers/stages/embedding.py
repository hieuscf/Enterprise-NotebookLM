# =============================================================================
# File: embedding.py
# Module/Service: Pipeline Worker — stage_embedding ([AI])
# Layer: Worker
# Purpose: Batch-embed document_chunks → Qdrant + embeddings metadata (FR2 Step 4).
# Responsibilities:
#   - Batch embed via configured provider; upsert shared Qdrant collection
#   - Insert embeddings rows; set document_chunks.embedding_id
# Dependencies:
#   - app.ai.embedding, QdrantStoreAdapter, KnowledgeSyncRepository, Settings
# Public Exports:
#   - stage_embedding
# Database/Table: embeddings, document_chunks
# Related Modules: app.workers.pipeline, app.adapters.qdrant_store
# Important Notes:
#   - Shared Qdrant collection + payload.workspace_id (not per-workspace collections).
#   - Celery may call Voyage/OpenAI embedding HTTP APIs; never Anthropic LLM.
# =============================================================================

from __future__ import annotations

from typing import Any
from uuid import UUID

from qdrant_client.http.exceptions import UnexpectedResponse

from app.adapters.qdrant_store import get_qdrant_store
from app.ai.embedding import embed_texts_batch
from app.core.config import get_settings
from app.db.sync_session import get_sync_session
from app.models.documents import Document, DocumentVersion
from app.models.enums import VectorStore
from app.repositories.knowledge import KnowledgeSyncRepository
from app.workers.stages.errors import DataPipelineError, TransientPipelineError


def stage_embedding(document_version_id: UUID) -> dict[str, Any]:
    """Embed all chunks for a document version into Qdrant + Postgres metadata.

    Args:
        document_version_id: Target version id.

    Returns:
        Metadata: embedded_count, model_name, dimension, collection, provider.
    """
    settings = get_settings()
    qdrant = get_qdrant_store()

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
            raise DataPipelineError("No document_chunks found — run hierarchical_chunking before embedding")

        texts = [c.content for c in chunks]
        try:
            vectors = embed_texts_batch(
                texts,
                model_name=settings.embedding_model_name,
                dimension=settings.embedding_dimension,
                provider=settings.embedding_provider,
                api_key=settings.embedding_api_key,
                batch_size=settings.embedding_batch_size,
            )
        except Exception as exc:
            # Network / 5xx → transient; auth / bad request → data.
            msg = str(exc).lower()
            if any(
                tok in msg for tok in ("timeout", "connection", "temporar", "429", "502", "503")
            ):
                raise TransientPipelineError(f"Embedding provider error: {exc}") from exc
            raise DataPipelineError(f"Embedding failed: {exc}") from exc

        if len(vectors) != len(chunks):
            raise DataPipelineError("Embedding provider returned unexpected vector count")

        try:
            # Only remove chunk vectors — preserve topic embeddings (kind=topic).
            qdrant.delete_by_document_version(document_version_id, kind="chunk")
        except Exception as exc:
            raise TransientPipelineError(f"Qdrant delete failed: {exc}") from exc

        points: list[dict[str, Any]] = []
        for chunk, vec in zip(chunks, vectors, strict=True):
            point_id = str(chunk.id)
            points.append(
                {
                    "point_id": point_id,
                    "vector": vec.values,
                    "payload": {
                        # Shared collection: filter retrieval by workspace_id.
                        "workspace_id": str(document.workspace_id),
                        "document_id": str(document.id),
                        "document_version_id": str(document_version_id),
                        "kind": "chunk",
                        "chunk_id": str(chunk.id),
                        "chunk_index": chunk.chunk_index,
                        "page_number": chunk.page_number,
                        "section_index": chunk.section_index,
                        "section": chunk.section,
                    },
                }
            )

        try:
            qdrant.upsert_chunk_vectors(points)
        except UnexpectedResponse as exc:
            raise TransientPipelineError(f"Qdrant upsert failed: {exc}") from exc
        except Exception as exc:
            msg = str(exc).lower()
            if any(tok in msg for tok in ("timeout", "connection", "temporar")):
                raise TransientPipelineError(f"Qdrant upsert failed: {exc}") from exc
            raise DataPipelineError(f"Qdrant upsert error: {exc}") from exc

        for chunk, vec, point in zip(chunks, vectors, points, strict=True):
            emb = knowledge.create_embedding(
                model_name=vec.model_name,
                dimension=vec.dimension,
                vector_store=VectorStore.qdrant,
                vector_id=point["point_id"],
                index_name=qdrant.collection_name,
            )
            knowledge.attach_chunk_embedding(chunk, emb.id)

        return {
            "document_version_id": str(document_version_id),
            "embedded_count": len(chunks),
            "model_name": settings.embedding_model_name,
            "dimension": settings.embedding_dimension,
            "provider": settings.embedding_provider,
            "batch_size": settings.embedding_batch_size,
            "qdrant_collection": qdrant.collection_name,
            "vector_store": "qdrant",
        }
