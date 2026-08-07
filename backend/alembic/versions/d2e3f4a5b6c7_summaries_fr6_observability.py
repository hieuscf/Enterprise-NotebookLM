# =============================================================================
# File: d2e3f4a5b6c7_summaries_fr6_observability.py
# Module/Service: Summary Service (FR6)
# Layer: Schema
# Purpose: Extend summaries with source_version + LLM observability columns.
# Responsibilities:
#   - Add source_version_id / model_used / token / cost / latency columns
#   - Backfill source_version_id from documents.current_version_id (then latest)
#   - Index (document_id, type) and (source_version_id)
# Dependencies:
#   - revision c1d2e3f4a5b6
# Public Exports:
#   - upgrade, downgrade
# Database/Table: summaries
# Related Modules: app.models.artifacts.Summary, SummaryService
# Important Notes:
#   - DB column remains ``type`` (OpenAPI ``style``); do not rename.
#   - Existing rows are preserved; source_version_id backfilled before NOT NULL.
# =============================================================================
"""summaries FR6 observability columns

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-08-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d2e3f4a5b6c7"
down_revision: str | None = "c1d2e3f4a5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "summaries",
        sa.Column("source_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "summaries",
        sa.Column("model_used", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "summaries",
        sa.Column(
            "prompt_tokens",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "summaries",
        sa.Column(
            "completion_tokens",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "summaries",
        sa.Column(
            "cost_usd",
            sa.Numeric(precision=10, scale=6),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "summaries",
        sa.Column("latency_ms", sa.Integer(), nullable=True),
    )

    # 1) Prefer documents.current_version_id (deterministic current version).
    op.execute(
        """
        UPDATE summaries AS s
        SET source_version_id = d.current_version_id
        FROM documents AS d
        WHERE s.document_id = d.id
          AND s.source_version_id IS NULL
          AND d.current_version_id IS NOT NULL
        """
    )
    # 2) Fallback: latest document_versions.version_number for the document.
    op.execute(
        """
        UPDATE summaries AS s
        SET source_version_id = (
            SELECT dv.id
            FROM document_versions AS dv
            WHERE dv.document_id = s.document_id
            ORDER BY dv.version_number DESC
            LIMIT 1
        )
        WHERE s.source_version_id IS NULL
        """
    )

    conn = op.get_bind()
    remaining = conn.execute(
        sa.text("SELECT COUNT(*) FROM summaries WHERE source_version_id IS NULL")
    ).scalar()
    if remaining and int(remaining) > 0:
        raise RuntimeError(
            f"Cannot enforce summaries.source_version_id NOT NULL: "
            f"{remaining} row(s) have no document_versions to backfill from. "
            "Attach a version to those documents (or remove orphan summaries) "
            "before re-running this migration."
        )

    op.alter_column(
        "summaries",
        "source_version_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.create_foreign_key(
        "fk_summaries_source_version_id",
        "summaries",
        "document_versions",
        ["source_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    # Existing index on document_id alone remains; composite aids (doc, style/type) lookups.
    op.create_index(
        "ix_summaries_document_id_type",
        "summaries",
        ["document_id", "type"],
        unique=False,
    )
    op.create_index(
        "ix_summaries_source_version_id",
        "summaries",
        ["source_version_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_summaries_source_version_id", table_name="summaries")
    op.drop_index("ix_summaries_document_id_type", table_name="summaries")
    op.drop_constraint("fk_summaries_source_version_id", "summaries", type_="foreignkey")
    op.drop_column("summaries", "latency_ms")
    op.drop_column("summaries", "cost_usd")
    op.drop_column("summaries", "completion_tokens")
    op.drop_column("summaries", "prompt_tokens")
    op.drop_column("summaries", "model_used")
    op.drop_column("summaries", "source_version_id")
