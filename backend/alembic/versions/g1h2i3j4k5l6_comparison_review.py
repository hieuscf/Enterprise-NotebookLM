# =============================================================================
# File: g1h2i3j4k5l6_comparison_review.py
# Module/Service: Comparison Service (TASK-CMP-20)
# Layer: Schema
# Purpose: Persist reviewer decisions separately from comparison analysis.
# Responsibilities:
#   - Add comparisons.review JSONB map (clause_id → decision)
# Dependencies:
#   - revision f0a1b2c3d4e5
# Public Exports:
#   - upgrade, downgrade
# Database/Table: comparisons
# Related Modules: Comparison ORM, ComparisonService.set_review
# Important Notes: Does not alter comparisons.result. Analysis remains immutable.
# =============================================================================
"""comparison review metadata

Revision ID: g1h2i3j4k5l6
Revises: f0a1b2c3d4e5
Create Date: 2026-08-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "g1h2i3j4k5l6"
down_revision: str | None = "f0a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "comparisons",
        sa.Column(
            "review",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("comparisons", "review")
