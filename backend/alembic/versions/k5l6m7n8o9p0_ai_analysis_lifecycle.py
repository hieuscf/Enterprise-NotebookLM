# =============================================================================
# File: k5l6m7n8o9p0_ai_analysis_lifecycle.py
# Module/Service: Alembic
# Layer: Schema
# Purpose: Split document usability from AI analysis lifecycle.
# Responsibilities:
#   - Add ai_analysis_status enum + columns on document_versions
#   - Backfill from pipeline_runs so existing READY indexes stay READY
# Dependencies:
#   - revision j4k5l6m7n8o9
# Public Exports:
#   - upgrade, downgrade
# Database/Table: document_versions
# Related Modules: REFACTOR_PLAN.md
# Important Notes: Additive. A version is valid with zero chunks.
# =============================================================================
"""ai_analysis_lifecycle

Revision ID: k5l6m7n8o9p0
Revises: j4k5l6m7n8o9
Create Date: 2026-10-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "k5l6m7n8o9p0"
down_revision: str | None = "j4k5l6m7n8o9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    ai_status = postgresql.ENUM(
        "not_analyzed",
        "queued",
        "processing",
        "ready",
        "failed",
        "stale",
        name="ai_analysis_status",
        create_type=False,
    )
    ai_status.create(bind, checkfirst=True)

    op.add_column(
        "document_versions",
        sa.Column(
            "ai_analysis_status",
            postgresql.ENUM(
                "not_analyzed",
                "queued",
                "processing",
                "ready",
                "failed",
                "stale",
                name="ai_analysis_status",
                create_type=False,
            ),
            nullable=False,
            server_default="not_analyzed",
        ),
    )
    op.add_column(
        "document_versions",
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "document_versions",
        sa.Column("analysis_error", sa.String(length=4000), nullable=True),
    )

    # Completed pipeline → analysis READY (keep document usable).
    op.execute(
        """
        UPDATE document_versions dv
        SET ai_analysis_status = 'ready'::ai_analysis_status,
            analyzed_at = pr.completed_at
        FROM (
            SELECT DISTINCT ON (document_version_id)
                document_version_id, status, completed_at
            FROM pipeline_runs
            ORDER BY document_version_id, completed_at DESC NULLS LAST, started_at DESC NULLS LAST
        ) pr
        WHERE pr.document_version_id = dv.id
          AND pr.status = 'completed'
        """
    )
    op.execute(
        """
        UPDATE document_versions dv
        SET ai_analysis_status = 'failed'::ai_analysis_status,
            analysis_error = LEFT(pr.error_message, 4000),
            status = 'ready'::document_version_status
        FROM (
            SELECT DISTINCT ON (document_version_id)
                document_version_id, status, error_message
            FROM pipeline_runs
            ORDER BY document_version_id, completed_at DESC NULLS LAST, started_at DESC NULLS LAST
        ) pr
        WHERE pr.document_version_id = dv.id
          AND pr.status = 'failed'
        """
    )
    op.execute(
        """
        UPDATE document_versions dv
        SET ai_analysis_status = CASE
                WHEN pr.status = 'pending' THEN 'queued'::ai_analysis_status
                ELSE 'processing'::ai_analysis_status
            END,
            status = 'ready'::document_version_status
        FROM (
            SELECT DISTINCT ON (document_version_id)
                document_version_id, status
            FROM pipeline_runs
            ORDER BY document_version_id, started_at DESC NULLS LAST
        ) pr
        WHERE pr.document_version_id = dv.id
          AND pr.status IN ('pending', 'running')
        """
    )
    # Legacy processing rows with no pipeline (or leftover): file is stored.
    op.execute(
        """
        UPDATE document_versions
        SET status = 'ready'::document_version_status
        WHERE status = 'processing'::document_version_status
        """
    )


def downgrade() -> None:
    op.drop_column("document_versions", "analysis_error")
    op.drop_column("document_versions", "analyzed_at")
    op.drop_column("document_versions", "ai_analysis_status")
    postgresql.ENUM(name="ai_analysis_status").drop(op.get_bind(), checkfirst=True)
