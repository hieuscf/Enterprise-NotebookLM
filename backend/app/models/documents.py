# =============================================================================
# File: documents.py
# Module/Service: Document Ingestion Service
# Layer: Schema
# Purpose: ORM models for documents and document_versions (FR2).
# Responsibilities:
#   - Persist document identity vs physical version history
# Dependencies:
#   - app.db.base, app.models.enums, app.models.types
# Public Exports:
#   - Document, DocumentVersion, DocumentVersionEvent
# Database/Table: documents, document_versions, document_version_events
# Related Modules: database-design-enterprise-notebooklm.md §1
# Important Notes: documents.current_version_id uses use_alter for circular FK.
# =============================================================================

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import (
    AiAnalysisStatus,
    DocumentVersionStatus,
    FileType,
    PreviewStatus,
    PreviewType,
)
from app.models.types import (
    ai_analysis_status_enum,
    created_at_col,
    document_version_status_enum,
    file_type_enum,
    preview_status_enum,
    preview_type_enum,
    updated_at_col,
    uuid_pk,
)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "document_versions.id",
            use_alter=True,
            name="fk_documents_current_version_id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    file_type: Mapped[FileType] = mapped_column(file_type_enum, nullable=False)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        Index("ix_document_versions_document_id_is_current", "document_id", "is_current"),
        Index("ix_document_versions_tags_gin", "tags", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    page_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        doc=(
            "Physical page/slide/sheet count for PDF/PPTX/XLSX. "
            "For DOCX: logical section count (by heading), not printed pages."
        ),
    )
    status: Mapped[DocumentVersionStatus] = mapped_column(
        document_version_status_enum,
        nullable=False,
        server_default=DocumentVersionStatus.ready.value,
    )
    # AI analysis is independent of document usability (status).
    ai_analysis_status: Mapped[AiAnalysisStatus] = mapped_column(
        ai_analysis_status_enum,
        nullable=False,
        server_default=AiAnalysisStatus.not_analyzed.value,
        default=AiAnalysisStatus.not_analyzed,
    )
    analyzed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    analysis_error: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # User-facing classification. Independent of layout_metadata (parser artifact).
    change_note: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    tags: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    classification_metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    parser: Mapped[str] = mapped_column(String(64), nullable=False, server_default="llamaparse")
    markdown_storage_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    layout_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Preview Representation (Viewer). storage_path = original_file_path.
    preview_file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    preview_status: Mapped[PreviewStatus] = mapped_column(
        preview_status_enum,
        nullable=False,
        default=PreviewStatus.pending,
        server_default=PreviewStatus.pending.value,
    )
    preview_type: Mapped[PreviewType | None] = mapped_column(preview_type_enum, nullable=True)
    preview_generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = created_at_col()


class DocumentVersionEvent(Base):
    """Append-only edit history for a document version (upload, rollback, tags)."""

    __tablename__ = "document_version_events"
    __table_args__ = (
        Index(
            "ix_document_version_events_workspace_created",
            "workspace_id",
            "created_at",
        ),
        Index(
            "ix_document_version_events_document_created",
            "document_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    summary: Mapped[str] = mapped_column(String(2000), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = created_at_col()
