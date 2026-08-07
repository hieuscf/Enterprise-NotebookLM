# =============================================================================
# File: a5b6c7d8e9f0_extractions_fr7_observability.py
# Module/Service: Extraction Service (FR7)
# Layer: Schema
# Purpose: Extend extractions with source_version + LLM observability columns.
# Responsibilities:
#   - Add source_version_id / model_used / token / cost / latency columns
#   - Backfill source_version_id from documents.current_version_id (then latest)
#   - Index (document_id, extraction_type) and (source_version_id)
# Dependencies:
#   - revision f4a5b6c7d8e9
# Public Exports:
#   - upgrade, downgrade
# Database/Table: extractions
# Related Modules: app.models.artifacts.Extraction, ExtractionService
# Important Notes:
#   - Existing columns preserved (result_json stays the JSONB result column).
#   - source_version_id backfilled before NOT NULL; migration fails if orphan rows.
# =============================================================================
"""extractions FR7 observability columns

Revision ID: a5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-08-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a5b6c7d8e9f0"
down_revision: str | None = "f4a5b6c7d8e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "extractions",
        sa.Column("source_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "extractions",
        sa.Column("model_used", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "extractions",
        sa.Column(
            "prompt_tokens",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "extractions",
        sa.Column(
            "completion_tokens",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "extractions",
        sa.Column(
            "cost_usd",
            sa.Numeric(precision=10, scale=6),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "extractions",
        sa.Column("latency_ms", sa.Integer(), nullable=True),
    )

    # 1) Prefer documents.current_version_id (deterministic current version).
    op.execute(
        """
        UPDATE extractions AS e
        SET source_version_id = d.current_version_id
        FROM documents AS d
        WHERE e.document_id = d.id
          AND e.source_version_id IS NULL
          AND d.current_version_id IS NOT NULL
        """
    )
    # 2) Fallback: latest document_versions.version_number for the document.
    op.execute(
        """
        UPDATE extractions AS e
        SET source_version_id = (
            SELECT dv.id
            FROM document_versions AS dv
            WHERE dv.document_id = e.document_id
            ORDER BY dv.version_number DESC
            LIMIT 1
        )
        WHERE e.source_version_id IS NULL
        """
    )

    conn = op.get_bind()
    remaining = conn.execute(
        sa.text("SELECT COUNT(*) FROM extractions WHERE source_version_id IS NULL")
    ).scalar()
    if remaining and int(remaining) > 0:
        raise RuntimeError(
            f"Cannot enforce extractions.source_version_id NOT NULL: "
            f"{remaining} row(s) have no document_versions to backfill from. "
            "Attach a version to those documents (or remove orphan extractions) "
            "before re-running this migration."
        )

    op.alter_column(
        "extractions",
        "source_version_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.create_foreign_key(
        "fk_extractions_source_version_id",
        "extractions",
        "document_versions",
        ["source_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_extractions_document_id_extraction_type",
        "extractions",
        ["document_id", "extraction_type"],
        unique=False,
    )
    op.create_index(
        "ix_extractions_source_version_id",
        "extractions",
        ["source_version_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_extractions_source_version_id", table_name="extractions")
    op.drop_index(
        "ix_extractions_document_id_extraction_type",
        table_name="extractions",
    )
    op.drop_constraint(
        "fk_extractions_source_version_id",
        "extractions",
        type_="foreignkey",
    )
    op.drop_column("extractions", "latency_ms")
    op.drop_column("extractions", "cost_usd")
    op.drop_column("extractions", "completion_tokens")
    op.drop_column("extractions", "prompt_tokens")
    op.drop_column("extractions", "model_used")
    op.drop_column("extractions", "source_version_id")
