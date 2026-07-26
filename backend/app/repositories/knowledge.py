# =============================================================================
# File: knowledge.py
# Module/Service: Pipeline Worker / Knowledge Base
# Layer: Repository
# Purpose: Sync ORM helpers for chunks, embeddings, entities, topics (FR2).
# Responsibilities:
#   - Persist pipeline outputs keyed by document_version_id / source_version_id
# Dependencies:
#   - SQLAlchemy Session (sync), app.models.knowledge
# Public Exports:
#   - KnowledgeSyncRepository
# Database/Table: embeddings, document_chunks, entities, entity_relations,
#   topics, topic_chunks
# Related Modules: app.workers.pipeline, app.ai.*
# Important Notes: Chunks/entities never FK directly to documents.id.
# =============================================================================

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.enums import VectorStore
from app.models.knowledge import (
    DocumentChunk,
    Embedding,
    Entity,
    EntityRelation,
    Topic,
    TopicChunk,
)


class KnowledgeSyncRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def clear_version_artifacts(self, document_version_id: uuid.UUID) -> None:
        """Remove prior chunk/entity/topic rows for a re-processed version."""
        self.clear_version_graph_artifacts(document_version_id)
        chunk_ids = list(
            self._session.scalars(
                select(DocumentChunk.id).where(
                    DocumentChunk.document_version_id == document_version_id
                )
            ).all()
        )
        if chunk_ids:
            self._session.execute(delete(DocumentChunk).where(DocumentChunk.id.in_(chunk_ids)))
        self._session.flush()

    def clear_version_graph_artifacts(self, document_version_id: uuid.UUID) -> None:
        """Remove entities/topics for a version without deleting document_chunks.

        Used by ``graph_extraction`` re-runs after chunks already exist.
        """
        chunk_ids = list(
            self._session.scalars(
                select(DocumentChunk.id).where(
                    DocumentChunk.document_version_id == document_version_id
                )
            ).all()
        )
        topic_ids: list[uuid.UUID] = []
        if chunk_ids:
            topic_ids = list(
                self._session.scalars(
                    select(TopicChunk.topic_id).where(TopicChunk.chunk_id.in_(chunk_ids)).distinct()
                ).all()
            )
            self._session.execute(delete(TopicChunk).where(TopicChunk.chunk_id.in_(chunk_ids)))

        if topic_ids:
            # Drop topics that no longer link to any chunk.
            still_linked = set(
                self._session.scalars(
                    select(TopicChunk.topic_id).where(TopicChunk.topic_id.in_(topic_ids)).distinct()
                ).all()
            )
            orphan_topics = [tid for tid in topic_ids if tid not in still_linked]
            if orphan_topics:
                emb_ids = list(
                    self._session.scalars(
                        select(Topic.embedding_id).where(
                            Topic.id.in_(orphan_topics),
                            Topic.embedding_id.is_not(None),
                        )
                    ).all()
                )
                self._session.execute(delete(Topic).where(Topic.id.in_(orphan_topics)))
                if emb_ids:
                    self._session.execute(delete(Embedding).where(Embedding.id.in_(emb_ids)))

        entity_ids = list(
            self._session.scalars(
                select(Entity.id).where(Entity.source_version_id == document_version_id)
            ).all()
        )
        if entity_ids:
            self._session.execute(
                delete(EntityRelation).where(
                    EntityRelation.source_entity_id.in_(entity_ids)
                    | EntityRelation.target_entity_id.in_(entity_ids)
                )
            )
            self._session.execute(delete(Entity).where(Entity.id.in_(entity_ids)))
        self._session.flush()

    def create_chunk(
        self,
        *,
        document_version_id: uuid.UUID,
        chunk_index: int,
        content: str,
        page_number: int | None,
        token_count: int | None,
        section: str | None = None,
    ) -> DocumentChunk:
        chunk = DocumentChunk(
            document_version_id=document_version_id,
            chunk_index=chunk_index,
            content=content,
            page_number=page_number,
            section=section,
            token_count=token_count,
        )
        self._session.add(chunk)
        self._session.flush()
        return chunk

    def create_embedding(
        self,
        *,
        model_name: str,
        dimension: int,
        vector_store: VectorStore,
        vector_id: str,
        index_name: str,
    ) -> Embedding:
        emb = Embedding(
            model_name=model_name,
            dimension=dimension,
            vector_store=vector_store,
            vector_id=vector_id,
            index_name=index_name,
        )
        self._session.add(emb)
        self._session.flush()
        return emb

    def attach_chunk_embedding(self, chunk: DocumentChunk, embedding_id: uuid.UUID) -> None:
        chunk.embedding_id = embedding_id
        self._session.flush()

    def create_entity(
        self,
        *,
        workspace_id: uuid.UUID,
        source_version_id: uuid.UUID,
        name: str,
        type_: str,
        description: str | None,
    ) -> Entity:
        entity = Entity(
            workspace_id=workspace_id,
            source_version_id=source_version_id,
            name=name,
            type=type_,
            description=description,
        )
        self._session.add(entity)
        self._session.flush()
        return entity

    def create_relation(
        self,
        *,
        source_entity_id: uuid.UUID,
        target_entity_id: uuid.UUID,
        relation_type: str,
        description: str | None = None,
        weight: float | None = None,
    ) -> EntityRelation:
        rel = EntityRelation(
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            relation_type=relation_type,
            description=description,
            weight=weight,
        )
        self._session.add(rel)
        self._session.flush()
        return rel

    def create_topic(
        self,
        *,
        workspace_id: uuid.UUID,
        name: str,
        level: int,
        summary: str | None,
        parent_topic_id: uuid.UUID | None = None,
        embedding_id: uuid.UUID | None = None,
    ) -> Topic:
        topic = Topic(
            workspace_id=workspace_id,
            name=name,
            level=level,
            summary=summary,
            parent_topic_id=parent_topic_id,
            embedding_id=embedding_id,
        )
        self._session.add(topic)
        self._session.flush()
        return topic

    def link_topic_chunk(self, topic_id: uuid.UUID, chunk_id: uuid.UUID) -> TopicChunk:
        link = TopicChunk(topic_id=topic_id, chunk_id=chunk_id)
        self._session.add(link)
        self._session.flush()
        return link

    def list_chunks_for_version(self, document_version_id: uuid.UUID) -> list[DocumentChunk]:
        return list(
            self._session.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_version_id == document_version_id)
                .order_by(DocumentChunk.chunk_index.asc())
            ).all()
        )
