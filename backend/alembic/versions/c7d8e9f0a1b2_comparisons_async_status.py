# =============================================================================
# File: c7d8e9f0a1b2_comparisons_async_status.py
# Module/Service: Comparison Service (FR8 Part 2)
# Layer: Schema
# Purpose: Add async generation status + focus on comparisons (Summary convention).
# Responsibilities:
#   - Create comparison_status enum (processing|completed|failed)
#   - Add status + focus columns; backfill existing rows with result as completed
# Dependencies:
#   - revision b6c7d8e9f0a1
# Public Exports:
#   - upgrade, downgrade
# Database/Table: comparisons
# Related Modules: Comparison ORM, ComparisonService, OpenAPI Comparison
# Important Notes: Mirrors summaries/extractions async status for Celery + FE poll.
# =============================================================================
"""comparisons async status

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-08-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c7d8e9f0a1b2"
down_revision: str | None = "b6c7d8e9f0a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_comparison_status = postgresql.ENUM(
    "processing",
    "completed",
    "failed",
    name="comparison_status",
    create_type=False,
)


def upgrade() -> None:
    _comparison_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "comparisons",
        sa.Column("focus", sa.Text(), nullable=True),
    )
    op.add_column(
        "comparisons",
        sa.Column(
            "status",
            _comparison_status,
            nullable=False,
            server_default="processing",
        ),
    )
    op.execute(
        """
        UPDATE comparisons
        SET status = 'completed'
        WHERE result IS NOT NULL
        """
    )
    op.create_index("ix_comparisons_status", "comparisons", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_comparisons_status", table_name="comparisons")
    op.drop_column("comparisons", "status")
    op.drop_column("comparisons", "focus")
    _comparison_status.drop(op.get_bind(), checkfirst=True)
