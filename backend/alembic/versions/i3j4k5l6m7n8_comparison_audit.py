# =============================================================================
# File: i3j4k5l6m7n8_comparison_audit.py
# Module/Service: Comparison Service (TASK-CMP-23)
# Layer: Schema
# Purpose: Persist an append-only comparison audit trail separately from analysis.
# Responsibilities:
#   - Add comparisons.audit JSONB list
# Dependencies:
#   - revision h2i3j4k5l6m7
# Public Exports:
#   - upgrade, downgrade
# Database/Table: comparisons
# Related Modules: Comparison ORM, ComparisonService.record_clause_opened
# Important Notes: Does not alter comparisons.result, review, or comments.
# =============================================================================
"""comparison audit trail

Revision ID: i3j4k5l6m7n8
Revises: h2i3j4k5l6m7
Create Date: 2026-08-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "i3j4k5l6m7n8"
down_revision: str | None = "h2i3j4k5l6m7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "comparisons",
        sa.Column(
            "audit",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("comparisons", "audit")
