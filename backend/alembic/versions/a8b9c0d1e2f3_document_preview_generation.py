# =============================================================================
# File: a8b9c0d1e2f3_document_preview_generation.py
# Module/Service: Alembic
# Layer: Schema
# Purpose: Preview Representation columns + preview_generation pipeline stage.
# Responsibilities:
#   - document_versions: preview_file_path, preview_status, preview_type,
#     preview_generated_at (original remains storage_path)
#   - Extend pipeline_stage enum with preview_generation
# Dependencies:
#   - revision e5f6a7b8c9d0
# Public Exports:
#   - upgrade, downgrade
# Database/Table: document_versions, pipeline_stage_logs
# Related Modules: Original Document Viewer, Preview Generator
# Important Notes: Docs schema v3 did not list preview_* — added for Viewer
#   Original Representation; storage_path = original_file_path.
# =============================================================================
"""document_preview_generation

Revision ID: a8b9c0d1e2f3
Revises: e5f6a7b8c9d0
Create Date: 2026-08-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a8b9c0d1e2f3"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum_has_value(connection: sa.Connection, enum_name: str, value: str) -> bool:
    row = connection.execute(
        sa.text(
            """
            SELECT 1
            FROM pg_enum e
            JOIN pg_type t ON e.enumtypid = t.oid
            WHERE t.typname = :enum_name AND e.enumlabel = :value
            LIMIT 1
            """
        ),
        {"enum_name": enum_name, "value": value},
    ).first()
    return row is not None


def upgrade() -> None:
    preview_status = postgresql.ENUM(
        "pending",
        "processing",
        "completed",
        "failed",
        name="preview_status",
        create_type=False,
    )
    preview_status.create(op.get_bind(), checkfirst=True)

    preview_type = postgresql.ENUM(
        "pdf",
        "html",
        "image",
        name="preview_type",
        create_type=False,
    )
    preview_type.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "document_versions",
        sa.Column("preview_file_path", sa.String(length=1024), nullable=True),
    )
    op.add_column(
        "document_versions",
        sa.Column(
            "preview_status",
            preview_status,
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "document_versions",
        sa.Column("preview_type", preview_type, nullable=True),
    )
    op.add_column(
        "document_versions",
        sa.Column("preview_generated_at", sa.DateTime(timezone=True), nullable=True),
    )

    bind = op.get_bind()
    if not _enum_has_value(bind, "pipeline_stage", "preview_generation"):
        op.execute("ALTER TYPE pipeline_stage ADD VALUE 'preview_generation'")


def downgrade() -> None:
    op.drop_column("document_versions", "preview_generated_at")
    op.drop_column("document_versions", "preview_type")
    op.drop_column("document_versions", "preview_status")
    op.drop_column("document_versions", "preview_file_path")
    op.execute("DROP TYPE IF EXISTS preview_status")
    op.execute("DROP TYPE IF EXISTS preview_type")
    # pipeline_stage ADD VALUE cannot be removed safely — leave preview_generation.
