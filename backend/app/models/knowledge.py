# =============================================================================
# File: knowledge.py
# Module/Service: Knowledge Base / LightRAG
# Layer: Schema
# Purpose: ORM models for embeddings, chunks, entities, topics (FR2, FR3).
# Responsibilities:
#   - Persist embedding metadata and dual-level knowledge graph structures
# Dependencies:
#   - app.db.base, app.models.enums, app.models.types
# Public Exports:
#   - Embedding, DocumentChunk, Entity, EntityRelation, Topic, TopicChunk
# Database/Table: embeddings, document_chunks, entities, entity_relations,
#   topics, topic_chunks
# Related Modules: database-design-enterprise-notebooklm.md §3, §8; ERD
# Important Notes: Chunks/entities point at document_version_id/source_version_id.
#   Vectors live in Qdrant/pgvector — embeddings table stores metadata only.
#   Location: page_number (PDF/PPTX/XLSX) XOR section_index (DOCX); see FR5.
#   v3: parent_chunk_id, heading_path, depth, layout_type for hierarchical chunking.
# =============================================================================

import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import ChunkLayoutType, VectorStore
from app.models.types import chunk_layout_type_enum, created_at_col, uuid_pk, vector_store_enum


class Embedding(Base):
    __tablename__ = "embeddings"

    id: Mapped[uuid.UUID] = uuid_pk()
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    vector_store: Mapped[VectorStore] = mapped_column(vector_store_enum, nullable=False)
    vector_id: Mapped[str] = mapped_column(String(255), nullable=False)
    index_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = created_at_col()


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        Index("ix_document_chunks_parent_chunk_id", "parent_chunk_id"),
        Index("ix_document_chunks_document_version_id_depth", "document_version_id", "depth"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    embedding_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("embeddings.id", ondelete="SET NULL"), nullable=True
    )
    parent_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_chunks.id", ondelete="SET NULL"),
        nullable=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(String(512), nullable=True)
    heading_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    depth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    layout_type: Mapped[ChunkLayoutType | None] = mapped_column(
        chunk_layout_type_enum, nullable=True
    )
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = created_at_col()


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    type: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = created_at_col()


class EntityRelation(Base):
    __tablename__ = "entity_relations"

    id: Mapped[uuid.UUID] = uuid_pk()
    source_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    target_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)


class Topic(Base):
    __tablename__ = "topics"
    __table_args__ = (Index("ix_topics_parent_topic_id", "parent_topic_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    embedding_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("embeddings.id", ondelete="SET NULL"), nullable=True
    )
    parent_topic_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("topics.id", ondelete="SET NULL"), nullable=True
    )
    level: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class TopicChunk(Base):
    __tablename__ = "topic_chunks"

    topic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="CASCADE"), primary_key=True
    )
