# =============================================================================
# File: f6a7b8c9d0e1_schema_v3_part1_llamaparse_hierarchy.py
# Module/Service: Alembic
# Layer: Schema
# Purpose: Schema v3 Part 1 — LlamaParse storage + hierarchical chunks + pipeline enum extend.
# Responsibilities:
#   - document_versions: markdown_storage_path, layout_metadata
#   - document_chunks: parent_chunk_id, heading_path, depth, layout_type
#   - pipeline_stage_logs.stage: ADD v3 values; KEEP ocr_cleaning/chunking (deprecated)
#   - Indexes on parent_chunk_id and (document_version_id, depth)
# Dependencies:
#   - database-design-enterprise-notebooklm.md v3, revision c3d4e5f6a7b8
# Public Exports:
#   - upgrade, downgrade
# Database/Table: document_versions, document_chunks, pipeline_stage_logs
# Related Modules: app.models.documents, app.models.knowledge, app.models.enums
# Important Notes:
#   - pipeline_stage: ocr_cleaning + chunking are DEPRECATED but retained so historical
#     pipeline_stage_logs rows remain valid without data migration.
#   - New pipeline code should use document_understanding / hierarchical_chunking instead.
#   - Downgrade refuses to shrink pipeline_stage enum if v3 stage values are in use.
# =============================================================================
"""schema_v3_part1_llamaparse_hierarchy

Revision ID: f6a7b8c9d0e1
Revises: c3d4e5f6a7b8
Create Date: 2026-07-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# v2 baseline (kept — deprecated, do not remove from ENUM)
_PIPELINE_STAGE_DEPRECATED = ("ocr_cleaning", "chunking")

# v3 additions (ALTER TYPE ADD VALUE — does not remove deprecated members)
_PIPELINE_STAGE_V3_NEW = (
    "document_understanding",
    "cleaning_normalize",
    "hierarchical_chunking",
)

_PIPELINE_STAGE_V2_ONLY = (
    "ocr_cleaning",
    "chunking",
    "embedding",
    "graph_extraction",
    "indexing",
)

_CHUNK_LAYOUT_VALUES = ("heading", "paragraph", "table", "list", "figure_caption")


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


def _add_pipeline_stage_values() -> None:
    bind = op.get_bind()
    for value in _PIPELINE_STAGE_V3_NEW:
        if not _enum_has_value(bind, "pipeline_stage", value):
            # PG 12+: IF NOT EXISTS; safe for idempotent re-run in dev.
            op.execute(f"ALTER TYPE pipeline_stage ADD VALUE '{value}'")


def _pipeline_logs_use_v3_stages(connection: sa.Connection) -> bool:
    placeholders = ", ".join(f"'{v}'" for v in _PIPELINE_STAGE_V3_NEW)
    row = connection.execute(
        sa.text(
            f"""
            SELECT 1 FROM pipeline_stage_logs
            WHERE stage::text IN ({placeholders})
            LIMIT 1
            """
        )
    ).first()
    return row is not None


def _shrink_pipeline_stage_enum_to_v2() -> None:
    """Recreate pipeline_stage with v2-only labels when no v3 stage rows exist."""
    connection = op.get_bind()
    if _pipeline_logs_use_v3_stages(connection):
        raise RuntimeError(
            "Cannot downgrade f6a7b8c9d0e1: pipeline_stage_logs contains v3 stage values. "
            "Delete or migrate those rows before downgrade."
        )

    tmp_name = "pipeline_stage_v2_restore"
    values_sql = ", ".join(f"'{v}'" for v in _PIPELINE_STAGE_V2_ONLY)
    op.execute(f"CREATE TYPE {tmp_name} AS ENUM ({values_sql})")
    op.execute(
        f"""
        ALTER TABLE pipeline_stage_logs
        ALTER COLUMN stage TYPE {tmp_name}
        USING (stage::text)::{tmp_name}
        """
    )
    op.execute("DROP TYPE pipeline_stage")
    op.execute(f"ALTER TYPE {tmp_name} RENAME TO pipeline_stage")


def upgrade() -> None:
    # --- 1. document_versions (LlamaParse outputs) ---
    op.add_column(
        "document_versions",
        sa.Column("markdown_storage_path", sa.String(length=1024), nullable=True),
    )
    op.add_column(
        "document_versions",
        sa.Column("layout_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # --- 2. document_chunks (hierarchical chunking) ---
    chunk_layout_type = postgresql.ENUM(
        *_CHUNK_LAYOUT_VALUES,
        name="chunk_layout_type",
        create_type=False,
    )
    chunk_layout_type.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "document_chunks",
        sa.Column("parent_chunk_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("heading_path", sa.String(length=1024), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("depth", sa.Integer(), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("layout_type", chunk_layout_type, nullable=True),
    )
    op.create_foreign_key(
        "fk_document_chunks_parent_chunk_id",
        "document_chunks",
        "document_chunks",
        ["parent_chunk_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # --- 4. indexes ---
    op.create_index(
        "ix_document_chunks_parent_chunk_id",
        "document_chunks",
        ["parent_chunk_id"],
        unique=False,
    )
    op.create_index(
        "ix_document_chunks_document_version_id_depth",
        "document_chunks",
        ["document_version_id", "depth"],
        unique=False,
    )

    # --- 3. pipeline_stage_logs.stage — extend ENUM (keep deprecated v2 labels) ---
    # ocr_cleaning / chunking remain valid for historical rows; new runs use v3 labels.
    _add_pipeline_stage_values()


def downgrade() -> None:
    _shrink_pipeline_stage_enum_to_v2()

    op.drop_index(
        "ix_document_chunks_document_version_id_depth",
        table_name="document_chunks",
    )
    op.drop_index("ix_document_chunks_parent_chunk_id", table_name="document_chunks")
    op.drop_constraint(
        "fk_document_chunks_parent_chunk_id",
        "document_chunks",
        type_="foreignkey",
    )
    op.drop_column("document_chunks", "layout_type")
    op.drop_column("document_chunks", "depth")
    op.drop_column("document_chunks", "heading_path")
    op.drop_column("document_chunks", "parent_chunk_id")
    op.execute("DROP TYPE IF EXISTS chunk_layout_type")

    op.drop_column("document_versions", "layout_metadata")
    op.drop_column("document_versions", "markdown_storage_path")
