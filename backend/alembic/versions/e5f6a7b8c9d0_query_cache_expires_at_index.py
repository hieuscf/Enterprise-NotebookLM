# =============================================================================
# File: e5f6a7b8c9d0_query_cache_expires_at_index.py
# Module/Service: Alembic
# Layer: Schema
# Purpose: Add standalone expires_at index for query_cache cleanup DELETE.
# Responsibilities:
#   - Create ix_query_cache_expires_at for Celery cleanup job
# Dependencies:
#   - database-design-enterprise-notebooklm.md (query_cache cleanup index note)
# Public Exports:
#   - upgrade, downgrade
# Database/Table: query_cache
# Related Modules: app.tasks.cleanup_expired_cache, app.models.query
# Important Notes: Complements existing (workspace_id, expires_at) composite index.
# =============================================================================
"""query_cache_expires_at_index

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-31
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_query_cache_expires_at",
        "query_cache",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_query_cache_expires_at", table_name="query_cache")
