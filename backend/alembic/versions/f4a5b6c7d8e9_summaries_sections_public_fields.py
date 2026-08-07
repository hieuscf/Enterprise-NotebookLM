# =============================================================================
# File: f4a5b6c7d8e9_summaries_sections_public_fields.py
# Module/Service: Summary Service (FR6 Part 3)
# Layer: Schema
# Purpose: Persist structured by_topic sections for the public Summary API.
# Responsibilities:
#   - Add nullable JSONB ``sections`` on summaries
# Dependencies:
#   - revision e3f4a5b6c7d8
# Public Exports:
#   - upgrade, downgrade
# Database/Table: summaries
# Related Modules: SummaryResponse.sections, OpenAPI Summary
# Important Notes: source_version_id already exists; Part 3 exposes it in API only.
# =============================================================================
"""summaries sections jsonb

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-08-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f4a5b6c7d8e9"
down_revision: str | None = "e3f4a5b6c7d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "summaries",
        sa.Column("sections", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("summaries", "sections")
