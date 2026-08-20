# =============================================================================
# File: j4k5l6m7n8o9_target_language_summaries_extractions.py
# Module/Service: Summary Service (FR6) / Extraction Service (FR7)
# Layer: Schema
# Purpose: Persist LLM output language for summaries and extractions.
# Responsibilities:
#   - Create shared PostgreSQL enum target_language (vi|en)
#   - Add target_language columns (default vi) on summaries and extractions
# Dependencies:
#   - revision i3j4k5l6m7n8
# Public Exports:
#   - upgrade, downgrade
# Database/Table: summaries, extractions
# Related Modules: TargetLanguage enum, Summary/Extraction ORM + OpenAPI
# Important Notes: Existing rows backfill to vi (prior hardcoded Vietnamese).
# =============================================================================
"""target_language on summaries and extractions

Revision ID: j4k5l6m7n8o9
Revises: i3j4k5l6m7n8
Create Date: 2026-08-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "j4k5l6m7n8o9"
down_revision: str | None = "i3j4k5l6m7n8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TARGET_LANGUAGE = sa.Enum("vi", "en", name="target_language")


def upgrade() -> None:
    _TARGET_LANGUAGE.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "summaries",
        sa.Column(
            "target_language",
            _TARGET_LANGUAGE,
            nullable=False,
            server_default="vi",
        ),
    )
    op.add_column(
        "extractions",
        sa.Column(
            "target_language",
            _TARGET_LANGUAGE,
            nullable=False,
            server_default="vi",
        ),
    )


def downgrade() -> None:
    op.drop_column("extractions", "target_language")
    op.drop_column("summaries", "target_language")
    _TARGET_LANGUAGE.drop(op.get_bind(), checkfirst=True)
