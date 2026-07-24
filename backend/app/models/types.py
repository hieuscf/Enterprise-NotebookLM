# =============================================================================
# File: types.py
# Module/Service: Models
# Layer: Schema
# Purpose: Shared SQLAlchemy column helpers (UUID PK, timestamps, ENUM factory).
# Responsibilities:
#   - Provide consistent UUID primary keys and timestamp columns
#   - Build native PostgreSQL ENUMs from Python enums (shared instances)
# Dependencies:
#   - SQLAlchemy, app.models.enums
# Public Exports:
#   - uuid_pk, created_at_col, updated_at_col, pg_enum, shared enum column types
# Database/Table: N/A
# Related Modules: app.models.*
# Important Notes: Reuse the same SAEnum instance when multiple tables share a type.
# =============================================================================

import uuid
from datetime import datetime
from enum import Enum
from typing import TypeVar

from sqlalchemy import DateTime, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import (
    DocumentVersionStatus,
    ExtractionOutputFormat,
    ExtractionType,
    FileType,
    FinishReason,
    MessageRole,
    PipelineStage,
    PipelineStatus,
    ReportFormat,
    ReportSourceType,
    ReportStatus,
    RetrievalMethod,
    RoleName,
    RouteType,
    SummaryType,
    UserStatus,
    VectorStore,
)

E = TypeVar("E", bound=Enum)


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def created_at_col() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def updated_at_col() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


def pg_enum(enum_cls: type[E], name: str, *, create_type: bool = True) -> SAEnum:
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=True,
        create_type=create_type,
        values_callable=lambda members: [m.value for m in members],
    )


# Shared PostgreSQL enum type instances (one DB type → many columns)
user_status_enum = pg_enum(UserStatus, "user_status")
role_name_enum = pg_enum(RoleName, "role_name")
file_type_enum = pg_enum(FileType, "file_type")
document_version_status_enum = pg_enum(DocumentVersionStatus, "document_version_status")
pipeline_status_enum = pg_enum(PipelineStatus, "pipeline_status")
pipeline_stage_enum = pg_enum(PipelineStage, "pipeline_stage")
vector_store_enum = pg_enum(VectorStore, "vector_store")
message_role_enum = pg_enum(MessageRole, "message_role")
route_type_enum = pg_enum(RouteType, "route_type")
finish_reason_enum = pg_enum(FinishReason, "finish_reason")
retrieval_method_enum = pg_enum(RetrievalMethod, "retrieval_method")
summary_type_enum = pg_enum(SummaryType, "summary_type")
extraction_type_enum = pg_enum(ExtractionType, "extraction_type")
extraction_output_format_enum = pg_enum(ExtractionOutputFormat, "extraction_output_format")
report_format_enum = pg_enum(ReportFormat, "report_format")
report_status_enum = pg_enum(ReportStatus, "report_status")
report_source_type_enum = pg_enum(ReportSourceType, "report_source_type")
