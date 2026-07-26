# =============================================================================
# File: graph_extraction.py
# Module/Service: Pipeline Worker — stage_graph_extraction ([AI] / LightRAG)
# Layer: Worker
# Purpose: Low-Level entities + High-Level topics for a document version (FR2 Step 5).
# Responsibilities:
#   - LLM (Haiku) structured extraction when configured — ONLY ingestion LLM cost
#   - Persist entities, entity_relations, topics, topic_chunks; embed topic summaries
#   - Best-effort Neo4j mirror of entities/relations
# Dependencies:
#   - app.ai.lightrag_extraction, embedding batch, Qdrant, Neo4j, KnowledgeSyncRepository
# Public Exports:
#   - stage_graph_extraction
# Database/Table: entities, entity_relations, topics, topic_chunks, embeddings
# Related Modules: app.workers.pipeline, System_Architecture LightRAG Core Engine
# Important Notes:
#   - *** LLM COST ***: This stage alone may call Anthropic (Haiku). Prefer cheap
#     model; disable via GRAPH_LLM_ENABLED=false for local/CI (heuristic fallback).
#   - Architecture: Anthropic chat ideally via backend-api; worker direct call is
#     the documented FR2 ingestion exception when ANTHROPIC_API_KEY is set.
# =============================================================================

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.adapters.neo4j_graph import get_neo4j_graph
from app.adapters.qdrant_store import get_qdrant_store
from app.ai.chunking import TextChunk
from app.ai.embedding import embed_texts_batch
from app.ai.lightrag_extraction import extract_lightrag_knowledge
from app.core.config import get_settings
from app.db.sync_session import get_sync_session
from app.models.documents import Document, DocumentVersion
from app.models.enums import VectorStore
from app.models.knowledge import DocumentChunk
from app.repositories.knowledge import KnowledgeSyncRepository
from app.workers.stages.errors import DataPipelineError, TransientPipelineError


def stage_graph_extraction(document_version_id: UUID) -> dict[str, Any]:
    """Extract entity graph + hierarchical topics (LightRAG dual-level).

    Args:
        document_version_id: Target ``document_versions.id``.

    Returns:
        Metadata for ``pipeline_stage_logs`` including LLM model/cost estimates.
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
        db_chunks = knowledge.list_chunks_for_version(document_version_id)
        if not db_chunks:
            raise DataPipelineError(
                "No document_chunks found — run chunking/embedding before graph_extraction"
            )

        text_chunks = [_to_text_chunk(c) for c in db_chunks]
        try:
            extracted = extract_lightrag_knowledge(text_chunks, settings=settings)
        except Exception as exc:
            msg = str(exc).lower()
            if any(tok in msg for tok in ("timeout", "connection", "429", "502", "503")):
                raise TransientPipelineError(f"Graph LLM extraction failed: {exc}") from exc
            raise DataPipelineError(f"Graph extraction failed: {exc}") from exc

        # Drop prior topic vectors before re-inserting graph/topic rows.
        try:
            qdrant.delete_by_document_version(document_version_id, kind="topic")
        except Exception as exc:
            raise TransientPipelineError(f"Qdrant topic delete failed: {exc}") from exc

        knowledge.clear_version_graph_artifacts(document_version_id)

        name_to_id: dict[str, UUID] = {}
        neo4j_entities: list[dict[str, Any]] = []
        for ent in extracted.entities:
            row = knowledge.create_entity(
                workspace_id=document.workspace_id,
                source_version_id=document_version_id,
                name=ent.name,
                type_=ent.type,
                description=ent.description,
            )
            name_to_id[ent.name] = row.id
            neo4j_entities.append(
                {
                    "id": str(row.id),
                    "name": row.name,
                    "type": row.type,
                    "description": row.description,
                }
            )

        relation_count = 0
        neo4j_relations: list[dict[str, Any]] = []
        for rel in extracted.relations:
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
            neo4j_relations.append(
                {
                    "id": str(row.id),
                    "source_entity_id": str(src),
                    "target_entity_id": str(tgt),
                    "relation_type": rel.relation_type,
                    "description": rel.description,
                    "weight": rel.weight,
                }
            )

        # Parents before children (level ascending).
        ordered_topics = sorted(extracted.topics, key=lambda t: (t.level, t.name))
        chunk_by_index = {c.chunk_index: c for c in db_chunks}
        topic_name_to_id: dict[str, UUID] = {}

        topic_summaries = [(t.summary or t.name).strip() or t.name for t in ordered_topics]
        topic_vectors: list[Any] = []
        if topic_summaries:
            try:
                topic_vectors = embed_texts_batch(
                    topic_summaries,
                    model_name=settings.embedding_model_name,
                    dimension=settings.embedding_dimension,
                    provider=settings.embedding_provider,
                    api_key=settings.embedding_api_key,
                    batch_size=settings.embedding_batch_size,
                )
            except Exception as exc:
                raise TransientPipelineError(f"Topic embedding failed: {exc}") from exc
            if len(topic_vectors) != len(ordered_topics):
                raise DataPipelineError("Topic embedding returned unexpected vector count")

        qdrant_points: list[dict[str, Any]] = []
        for topic, summary, vec in zip(ordered_topics, topic_summaries, topic_vectors, strict=True):
            parent_id = topic_name_to_id.get(topic.parent_name) if topic.parent_name else None
            emb = knowledge.create_embedding(
                model_name=vec.model_name,
                dimension=vec.dimension,
                vector_store=VectorStore.qdrant,
                vector_id="pending",
                index_name=qdrant.collection_name,
            )
            row = knowledge.create_topic(
                workspace_id=document.workspace_id,
                name=topic.name,
                level=topic.level,
                summary=topic.summary,
                parent_topic_id=parent_id,
                embedding_id=emb.id,
            )
            emb.vector_id = str(row.id)
            topic_name_to_id[topic.name] = row.id
            qdrant_points.append(
                {
                    "point_id": str(row.id),
                    "vector": vec.values,
                    "payload": {
                        "workspace_id": str(document.workspace_id),
                        "document_version_id": str(document_version_id),
                        "kind": "topic",
                        "topic_id": str(row.id),
                        "level": topic.level,
                        "name": topic.name,
                        "summary": summary[:500],
                    },
                }
            )
            for idx in topic.chunk_indexes:
                chunk = chunk_by_index.get(idx)
                if chunk is not None:
                    knowledge.link_topic_chunk(row.id, chunk.id)

        if qdrant_points:
            try:
                qdrant.upsert_chunk_vectors(qdrant_points)
            except Exception as exc:
                raise TransientPipelineError(f"Qdrant topic upsert failed: {exc}") from exc

        # Best-effort Neo4j mirror (Postgres remains canonical).
        neo4j_synced = False
        if neo4j_entities:
            try:
                get_neo4j_graph().upsert_entities_and_relations(
                    workspace_id=document.workspace_id,
                    source_version_id=document_version_id,
                    entities=neo4j_entities,
                    relations=neo4j_relations,
                )
                neo4j_synced = True
            except Exception:
                neo4j_synced = False

        return {
            "document_version_id": str(document_version_id),
            "entity_count": len(extracted.entities),
            "relation_count": relation_count,
            "topic_count": len(ordered_topics),
            "llm_used": extracted.llm_used,
            "llm_model": extracted.model_used,
            "llm_input_tokens": extracted.input_tokens,
            "llm_output_tokens": extracted.output_tokens,
            "estimated_cost_usd": round(extracted.estimated_cost_usd, 6),
            "neo4j_synced": neo4j_synced,
            # Explicit ops signal: this stage is the ingestion LLM cost center.
            "llm_cost_note": (
                "graph_extraction is the only ingestion stage that may call "
                "Anthropic chat (Haiku). Set GRAPH_LLM_ENABLED=false to use heuristics."
            ),
        }


def _to_text_chunk(chunk: DocumentChunk) -> TextChunk:
    return TextChunk(
        chunk_index=chunk.chunk_index,
        content=chunk.content,
        page_number=chunk.page_number,
        section=chunk.section,
        heading=chunk.section,
        paragraph_index=None,
        start_offset=0,
        end_offset=len(chunk.content or ""),
        token_count=chunk.token_count or 0,
        metadata={
            "page": chunk.page_number,
            "section": chunk.section,
            "heading": chunk.section,
            "paragraph": None,
        },
    )
