# =============================================================================
# File: c3d4e5f6a7b8_document_chunks_add_section_index.py
# Module/Service: Document Ingestion / Knowledge Base
# Layer: Schema
# Purpose: Add document_chunks.section_index for DOCX logical locators (FR5).
# Responsibilities:
#   - Persist 1-based section_index from OCR/Chunking onto document_chunks
#   - Keep page_number for physical formats; both nullable (no backfill)
# Dependencies:
#   - Alembic, revision b2c3d4e5f6a7
# Public Exports:
#   - upgrade, downgrade
# Database/Table: document_chunks
# Related Modules: database-design-enterprise-notebooklm.md; stage_chunking; FR5
# Important Notes: Old rows stay NULL; re-run pipeline to populate. No backfill.
# =============================================================================

"""document_chunks.add section_index

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "document_chunks",
        sa.Column("section_index", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document_chunks", "section_index")
