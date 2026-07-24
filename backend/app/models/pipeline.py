# =============================================================================
# File: pipeline.py
# Module/Service: Pipeline Worker / Observability Module
# Layer: Schema
# Purpose: ORM models for pipeline_runs and pipeline_stage_logs (FR2, FR13).
# Responsibilities:
#   - Persist ingestion pipeline run status and per-stage logs
# Dependencies:
#   - app.db.base, app.models.enums, app.models.types
# Public Exports:
#   - PipelineRun, PipelineStageLog
# Database/Table: pipeline_runs, pipeline_stage_logs
# Related Modules: database-design-enterprise-notebooklm.md §2
# Important Notes: Stage enum is fixed to five OCR→indexing stages.
# =============================================================================

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import PipelineStage, PipelineStatus
from app.models.types import pipeline_stage_enum, pipeline_status_enum, uuid_pk


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    __table_args__ = (
        Index("ix_pipeline_runs_document_version_id_status", "document_version_id", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[PipelineStatus] = mapped_column(
        pipeline_status_enum,
        nullable=False,
        server_default=PipelineStatus.pending.value,
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PipelineStageLog(Base):
    __tablename__ = "pipeline_stage_logs"

    id: Mapped[uuid.UUID] = uuid_pk()
    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage: Mapped[PipelineStage] = mapped_column(pipeline_stage_enum, nullable=False)
    status: Mapped[PipelineStatus] = mapped_column(pipeline_status_enum, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
