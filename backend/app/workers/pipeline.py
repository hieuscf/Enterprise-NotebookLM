# =============================================================================
# File: pipeline.py
# Module/Service: Pipeline Worker
# Layer: Worker
# Purpose: Celery orchestration OCR→Chunk→Embed→Graph→Index (FR2, FR13).
# Responsibilities:
#   - process_document_pipeline task; per-stage logs (status, duration_ms, metadata)
#   - Call [AI] stage modules; persist via sync repos; index Qdrant/ES/Neo4j [BE]
# Dependencies:
#   - Celery, app.ai.*, app.adapters.*, app.repositories.pipeline_sync, knowledge
# Public Exports:
#   - run_pipeline (Celery task name for Document Ingestion enqueue)
# Database/Table: pipeline_runs, pipeline_stage_logs, document_chunks, embeddings,
#   entities, entity_relations, topics, topic_chunks, document_versions
# Related Modules: Document Ingestion Service, System_Architecture Pipeline Worker
# Important Notes: Must NOT call Anthropic/LLM Provider from this worker.
# =============================================================================

from __future__ import annotations

import uuid
from typing import Any

from app.adapters.elasticsearch_bm25 import get_elasticsearch_bm25
from app.adapters.minio_storage import get_minio_storage
from app.adapters.neo4j_graph import get_neo4j_graph
from app.adapters.qdrant_store import get_qdrant_store
from app.ai.chunking import run_chunking
from app.ai.embedding import embed_texts
from app.ai.graph_extraction import extract_graph
from app.ai.ocr import run_ocr_cleaning
from app.ai.topic_extraction import extract_topics
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.sync_session import get_sync_session
from app.models.documents import Document
from app.models.enums import DocumentVersionStatus, PipelineStage, PipelineStatus, VectorStore
from app.repositories.knowledge import KnowledgeSyncRepository
from app.repositories.pipeline_sync import PipelineSyncRepository
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="run_pipeline", bind=True, max_retries=2)
def run_pipeline(self, pipeline_run_id: str) -> dict[str, Any]:
    """Celery entrypoint enqueued by Document Ingestion Service (FR2 Step 1+)."""
    run_id = uuid.UUID(pipeline_run_id)
    try:
        return _execute_pipeline(run_id)
    except Exception as exc:
        logger.exception("pipeline_failed", pipeline_run_id=pipeline_run_id)
        with get_sync_session() as session:
            pipe = PipelineSyncRepository(session)
            run = pipe.get_run(run_id)
            if run is not None and run.status not in {
                PipelineStatus.failed,
                PipelineStatus.completed,
            }:
                run.retry_count = (run.retry_count or 0) + 1
                pipe.mark_run_failed(run, str(exc))
                version = pipe.get_version(run.document_version_id)
                if version is not None:
                    pipe.set_version_status(version, DocumentVersionStatus.failed)
        raise


# Backward-compatible alias (older enqueue name).
process_document_pipeline = run_pipeline


def _execute_pipeline(pipeline_run_id: uuid.UUID) -> dict[str, Any]:
    settings = get_settings()
    storage = get_minio_storage()
    qdrant = get_qdrant_store()
    es = get_elasticsearch_bm25()
    neo4j = get_neo4j_graph()

    with get_sync_session() as session:
        pipe = PipelineSyncRepository(session)
        knowledge = KnowledgeSyncRepository(session)

        run = pipe.get_run(pipeline_run_id)
        if run is None:
            raise ValueError(f"pipeline_run not found: {pipeline_run_id}")

        version = pipe.get_version(run.document_version_id)
        if version is None:
            raise ValueError(f"document_version not found: {run.document_version_id}")

        document = session.get(Document, version.document_id)
        if document is None:
            raise ValueError(f"document not found: {version.document_id}")

        workspace_id = document.workspace_id
        pipe.mark_run_running(run)

        try:
            # --- stage: ocr_cleaning ---
            log = pipe.start_stage(run.id, PipelineStage.ocr_cleaning)
            try:
                raw = storage.download_bytes(version.storage_path)
                ocr = run_ocr_cleaning(file_type=document.file_type, data=raw)
                pipe.set_version_status(
                    version, DocumentVersionStatus.processing, page_count=ocr.page_count
                )
                pipe.complete_stage(
                    log,
                    metadata={
                        "page_count": ocr.page_count,
                        "char_count": ocr.char_count,
                        "file_type": document.file_type.value,
                    },
                )
            except Exception as exc:
                pipe.fail_stage(log, str(exc))
                raise

            # --- stage: chunking ---
            log = pipe.start_stage(run.id, PipelineStage.chunking)
            try:
                knowledge.clear_version_artifacts(version.id)
                text_chunks = run_chunking(ocr.pages)
                db_chunks = []
                for tc in text_chunks:
                    db_chunks.append(
                        knowledge.create_chunk(
                            document_version_id=version.id,
                            chunk_index=tc.chunk_index,
                            content=tc.content,
                            page_number=tc.page_number,
                            token_count=tc.token_count,
                        )
                    )
                pipe.complete_stage(log, metadata={"chunk_count": len(db_chunks)})
            except Exception as exc:
                pipe.fail_stage(log, str(exc))
                raise

            # --- stage: embedding ---
            log = pipe.start_stage(run.id, PipelineStage.embedding)
            try:
                vectors = embed_texts(
                    [c.content for c in text_chunks],
                    model_name=settings.embedding_model_name,
                    dimension=settings.embedding_dimension,
                )
                vector_store = (
                    VectorStore.qdrant
                    if settings.vector_store == "qdrant"
                    else VectorStore.pgvector
                )
                try:
                    qdrant.delete_by_document_version(version.id)
                except Exception:
                    logger.warning("qdrant_delete_skipped", version_id=str(version.id))

                for chunk, tc, vec in zip(db_chunks, text_chunks, vectors, strict=True):
                    point_id = str(chunk.id)
                    qdrant.upsert_chunk_vector(
                        point_id=point_id,
                        vector=vec.values,
                        payload={
                            "chunk_id": str(chunk.id),
                            "document_version_id": str(version.id),
                            "workspace_id": str(workspace_id),
                            "chunk_index": tc.chunk_index,
                            "page_number": tc.page_number,
                        },
                    )
                    emb = knowledge.create_embedding(
                        model_name=vec.model_name,
                        dimension=vec.dimension,
                        vector_store=vector_store,
                        vector_id=point_id,
                        index_name=qdrant.collection_name,
                    )
                    knowledge.attach_chunk_embedding(chunk, emb.id)

                pipe.complete_stage(
                    log,
                    metadata={
                        "embedded_count": len(db_chunks),
                        "model_name": settings.embedding_model_name,
                        "dimension": settings.embedding_dimension,
                    },
                )
            except Exception as exc:
                pipe.fail_stage(log, str(exc))
                raise

            # --- stage: graph_extraction (entities + topics) ---
            log = pipe.start_stage(run.id, PipelineStage.graph_extraction)
            try:
                graph = extract_graph(text_chunks)
                name_to_id: dict[str, uuid.UUID] = {}
                neo_entities: list[dict[str, Any]] = []
                for ent in graph.entities:
                    row = knowledge.create_entity(
                        workspace_id=workspace_id,
                        source_version_id=version.id,
                        name=ent.name,
                        type_=ent.type,
                        description=ent.description,
                    )
                    name_to_id[ent.name] = row.id
                    neo_entities.append(
                        {
                            "id": str(row.id),
                            "name": row.name,
                            "type": row.type,
                            "description": row.description,
                        }
                    )

                neo_relations: list[dict[str, Any]] = []
                relation_count = 0
                for rel in graph.relations:
                    src = name_to_id.get(rel.source_name)
                    tgt = name_to_id.get(rel.target_name)
                    if src is None or tgt is None:
                        continue
                    row = knowledge.create_relation(
                        source_entity_id=src,
                        target_entity_id=tgt,
                        relation_type=rel.relation_type,
                        description=rel.description,
                        weight=rel.weight,
                    )
                    relation_count += 1
                    neo_relations.append(
                        {
                            "id": str(row.id),
                            "source_entity_id": str(src),
                            "target_entity_id": str(tgt),
                            "relation_type": row.relation_type,
                            "description": row.description,
                            "weight": row.weight,
                        }
                    )

                topic_result = extract_topics(text_chunks)
                chunk_by_index = {c.chunk_index: c for c in db_chunks}
                topic_name_to_id: dict[str, uuid.UUID] = {}
                topic_count = 0
                for topic in topic_result.topics:
                    parent_id = (
                        topic_name_to_id.get(topic.parent_name) if topic.parent_name else None
                    )
                    row = knowledge.create_topic(
                        workspace_id=workspace_id,
                        name=topic.name,
                        level=topic.level,
                        summary=topic.summary,
                        parent_topic_id=parent_id,
                    )
                    topic_name_to_id[topic.name] = row.id
                    topic_count += 1
                    for idx in topic.chunk_indexes:
                        chunk = chunk_by_index.get(idx)
                        if chunk is not None:
                            knowledge.link_topic_chunk(row.id, chunk.id)

                try:
                    neo4j.upsert_entities_and_relations(
                        workspace_id=workspace_id,
                        source_version_id=version.id,
                        entities=neo_entities,
                        relations=neo_relations,
                    )
                except Exception as neo_exc:
                    logger.warning("neo4j_upsert_failed", error=str(neo_exc))

                pipe.complete_stage(
                    log,
                    metadata={
                        "entity_count": len(graph.entities),
                        "relation_count": relation_count,
                        "topic_count": topic_count,
                    },
                )
            except Exception as exc:
                pipe.fail_stage(log, str(exc))
                raise

            # --- stage: indexing (BM25 Elasticsearch) ---
            log = pipe.start_stage(run.id, PipelineStage.indexing)
            try:
                try:
                    es.delete_by_document_version(version.id)
                except Exception:
                    logger.warning("es_delete_skipped", version_id=str(version.id))

                docs = [
                    {
                        "chunk_id": str(chunk.id),
                        "document_version_id": str(version.id),
                        "workspace_id": str(workspace_id),
                        "content": chunk.content,
                        "page_number": chunk.page_number,
                        "chunk_index": chunk.chunk_index,
                    }
                    for chunk in db_chunks
                ]
                indexed = es.index_chunks(docs)
                pipe.complete_stage(
                    log,
                    metadata={
                        "bm25_indexed": indexed,
                        "elasticsearch_index": es.index_name,
                        "qdrant_collection": qdrant.collection_name,
                    },
                )
            except Exception as exc:
                pipe.fail_stage(log, str(exc))
                raise

            pipe.set_version_status(version, DocumentVersionStatus.ready, page_count=ocr.page_count)
            pipe.mark_run_completed(run)
            logger.info(
                "pipeline_completed",
                pipeline_run_id=str(run.id),
                document_version_id=str(version.id),
                chunks=len(db_chunks),
            )
            return {
                "pipeline_run_id": str(run.id),
                "document_version_id": str(version.id),
                "status": "completed",
                "chunk_count": len(db_chunks),
            }
        except Exception as exc:
            # Persist stage/run failure before session context rolls back uncommitted work.
            pipe.mark_run_failed(run, str(exc))
            pipe.set_version_status(version, DocumentVersionStatus.failed)
            session.commit()
            raise
