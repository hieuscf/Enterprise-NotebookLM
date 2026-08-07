# =============================================================================
# File: b6c7d8e9f0a1_extractions_async_status.py
# Module/Service: Extraction Service (FR7 Part 5)
# Layer: Schema
# Purpose: Add async generation status + nullable result_json on extractions.
# Responsibilities:
#   - Create extraction_status enum (processing|completed|failed)
#   - Backfill existing rows as completed; make result_json nullable
# Dependencies:
#   - revision a5b6c7d8e9f0
# Public Exports:
#   - upgrade, downgrade
# Database/Table: extractions
# Related Modules: Extraction ORM, ExtractionService, OpenAPI Extraction
# Important Notes: Mirrors summaries async status (FR6 Part 2 convention).
# =============================================================================
"""extractions async status

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-08-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b6c7d8e9f0a1"
down_revision: str | None = "a5b6c7d8e9f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_extraction_status = postgresql.ENUM(
    "processing",
    "completed",
    "failed",
    name="extraction_status",
    create_type=False,
)


def upgrade() -> None:
    _extraction_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "extractions",
        sa.Column(
            "status",
            _extraction_status,
            nullable=False,
            server_default="processing",
        ),
    )
    # Historical rows already have generated result_json → completed.
    op.execute(
        """
        UPDATE extractions
        SET status = 'completed'
        WHERE result_json IS NOT NULL
        """
    )
    op.alter_column(
        "extractions",
        "result_json",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=True,
    )
    op.create_index("ix_extractions_status", "extractions", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_extractions_status", table_name="extractions")
    op.execute(
        """
        UPDATE extractions
        SET result_json = '{}'::jsonb
        WHERE result_json IS NULL
        """
    )
    op.alter_column(
        "extractions",
        "result_json",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
    )
    op.drop_column("extractions", "status")
    _extraction_status.drop(op.get_bind(), checkfirst=True)
