# =============================================================================
# File: e3f4a5b6c7d8_summaries_async_status.py
# Module/Service: Summary Service (FR6 Part 2)
# Layer: Schema
# Purpose: Add async generation status + nullable content on summaries.
# Responsibilities:
#   - Create summary_status enum (processing|completed|failed)
#   - Backfill existing rows as completed; make content nullable
# Dependencies:
#   - revision d2e3f4a5b6c7
# Public Exports:
#   - upgrade, downgrade
# Database/Table: summaries
# Related Modules: app.models.artifacts.Summary, SummaryService, OpenAPI Summary
# Important Notes: Existing summaries with content → status=completed.
# =============================================================================
"""summaries async status

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-08-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e3f4a5b6c7d8"
down_revision: str | None = "d2e3f4a5b6c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_summary_status = postgresql.ENUM(
    "processing",
    "completed",
    "failed",
    name="summary_status",
    create_type=False,
)


def upgrade() -> None:
    _summary_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "summaries",
        sa.Column(
            "status",
            _summary_status,
            nullable=False,
            server_default="processing",
        ),
    )
    # Historical rows already have generated content → completed.
    op.execute(
        """
        UPDATE summaries
        SET status = 'completed'
        WHERE content IS NOT NULL AND BTRIM(content) <> ''
        """
    )
    op.alter_column(
        "summaries",
        "content",
        existing_type=sa.Text(),
        nullable=True,
    )
    op.create_index("ix_summaries_status", "summaries", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_summaries_status", table_name="summaries")
    # Restore NOT NULL content: failed/processing rows get empty string placeholder.
    op.execute(
        """
        UPDATE summaries
        SET content = ''
        WHERE content IS NULL
        """
    )
    op.alter_column(
        "summaries",
        "content",
        existing_type=sa.Text(),
        nullable=False,
    )
    op.drop_column("summaries", "status")
    _summary_status.drop(op.get_bind(), checkfirst=True)
