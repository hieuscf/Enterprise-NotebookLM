# =============================================================================
# File: artifacts.py
# Module/Service: Summary / Extraction / Comparison / Report Services
# Layer: Schema
# Purpose: ORM models for extended analysis artifacts (FR6–FR9).
# Responsibilities:
#   - Persist summaries, extractions, comparisons, and reports
# Dependencies:
#   - app.db.base, app.models.enums, app.models.types
# Public Exports:
#   - Summary, Extraction, Comparison, ComparisonDocument, Report, ReportItem
# Database/Table: summaries, extractions, comparisons, comparison_documents,
#   reports, report_items
# Related Modules: ERD + OpenAPI (enums/columns inferred for v1-stable tables)
# Important Notes:
#   - Enum values prefer OpenAPI where ERD shorthand differs.
#   - summaries.type maps to OpenAPI Summary.style (do not rename the DB column).
#   - source_version_id pins the document_versions row used for generation.
#   - extractions.result_json maps to OpenAPI Extraction.result.
#   - extractions.source_version_id pins the version used for extraction.
# =============================================================================

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import (
    ComparisonStatus,
    ExtractionOutputFormat,
    ExtractionStatus,
    ExtractionType,
    ReportFormat,
    ReportSourceType,
    ReportStatus,
    SummaryStatus,
    SummaryType,
)
from app.models.types import (
    comparison_status_enum,
    created_at_col,
    extraction_output_format_enum,
    extraction_status_enum,
    extraction_type_enum,
    report_format_enum,
    report_source_type_enum,
    report_status_enum,
    summary_status_enum,
    summary_type_enum,
    uuid_pk,
)


class Summary(Base):
    __tablename__ = "summaries"
    __table_args__ = (
        Index("ix_summaries_document_id_type", "document_id", "type"),
        Index("ix_summaries_source_version_id", "source_version_id"),
        Index("ix_summaries_status", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    source_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    type: Mapped[SummaryType] = mapped_column(summary_type_enum, nullable=False)
    status: Mapped[SummaryStatus] = mapped_column(
        summary_status_enum,
        nullable=False,
        server_default=SummaryStatus.processing.value,
    )
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    sections: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    completion_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False, server_default="0"
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = created_at_col()


class Extraction(Base):
    __tablename__ = "extractions"
    __table_args__ = (
        Index("ix_extractions_document_id_extraction_type", "document_id", "extraction_type"),
        Index("ix_extractions_source_version_id", "source_version_id"),
        Index("ix_extractions_status", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    source_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    extraction_type: Mapped[ExtractionType] = mapped_column(extraction_type_enum, nullable=False)
    output_format: Mapped[ExtractionOutputFormat] = mapped_column(
        extraction_output_format_enum,
        nullable=False,
        server_default=ExtractionOutputFormat.json.value,
    )
    status: Mapped[ExtractionStatus] = mapped_column(
        extraction_status_enum,
        nullable=False,
        server_default=ExtractionStatus.processing.value,
    )
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    completion_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False, server_default="0"
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = created_at_col()


class Comparison(Base):
    __tablename__ = "comparisons"
    __table_args__ = (Index("ix_comparisons_status", "status"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    focus: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ComparisonStatus] = mapped_column(
        comparison_status_enum,
        nullable=False,
        server_default=ComparisonStatus.processing.value,
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = created_at_col()


class ComparisonDocument(Base):
    __tablename__ = "comparison_documents"

    comparison_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("comparisons.id", ondelete="CASCADE"), primary_key=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    format: Mapped[ReportFormat] = mapped_column(report_format_enum, nullable=False)
    status: Mapped[ReportStatus] = mapped_column(
        report_status_enum,
        nullable=False,
        server_default=ReportStatus.pending.value,
    )
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = created_at_col()


class ReportItem(Base):
    __tablename__ = "report_items"

    id: Mapped[uuid.UUID] = uuid_pk()
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_type: Mapped[ReportSourceType] = mapped_column(report_source_type_enum, nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
