# =============================================================================
# File: h2i3j4k5l6m7_comparison_comments.py
# Module/Service: Comparison Service (TASK-CMP-22)
# Layer: Schema
# Purpose: Persist reviewer comments separately from comparison analysis.
# Responsibilities:
#   - Add comparisons.comments JSONB list
# Dependencies:
#   - revision g1h2i3j4k5l6
# Public Exports:
#   - upgrade, downgrade
# Database/Table: comparisons
# Related Modules: Comparison ORM, ComparisonService.add_comment
# Important Notes: Does not alter comparisons.result or comparisons.review.
# =============================================================================
"""comparison comments metadata

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
Create Date: 2026-08-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "h2i3j4k5l6m7"
down_revision: str | None = "g1h2i3j4k5l6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "comparisons",
        sa.Column(
            "comments",
            postgresql.JSONB(asuuid=False),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("comparisons", "comments")
