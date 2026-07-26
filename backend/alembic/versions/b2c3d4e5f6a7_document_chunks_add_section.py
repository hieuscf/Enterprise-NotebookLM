# =============================================================================
# File: b2c3d4e5f6a7_document_chunks_add_section.py
# Module/Service: Document Ingestion / Knowledge Base
# Layer: Schema
# Purpose: Add document_chunks.section for structure-aware chunk metadata (FR2).
# Responsibilities:
#   - Persist heading/sheet/slide section labels from OCR segments onto chunks
# Dependencies:
#   - Alembic, revision a1b2c3d4e5f6
# Public Exports:
#   - upgrade, downgrade
# Database/Table: document_chunks
# Related Modules: database-design-enterprise-notebooklm.md; stage_chunking
# Important Notes: Schema v2 had page_number only — section needed for citation UX.
# =============================================================================

"""document_chunks.add section

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "document_chunks",
        sa.Column("section", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document_chunks", "section")
