# =============================================================================
# File: d8e9f0a1b2c3_query_logs_route_type_index.py
# Module/Service: Alembic
# Layer: Schema
# Purpose: Composite index for admin query-logs filter by route_type.
# Responsibilities:
#   - Create ix_query_logs_workspace_id_route_type_created_at
# Dependencies:
#   - revision c7d8e9f0a1b2
# Public Exports:
#   - upgrade, downgrade
# Database/Table: query_logs
# Related Modules: app.models.query.QueryLog, GET /admin/.../query-logs
# Important Notes: Complements existing ix_query_logs_workspace_id.
# =============================================================================
"""query_logs route_type composite index

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-08-09
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "d8e9f0a1b2c3"
down_revision: str | None = "c7d8e9f0a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_query_logs_workspace_id_route_type_created_at",
        "query_logs",
        ["workspace_id", "route_type", "created_at"],
        unique=False,
        postgresql_ops={"created_at": "DESC"},
    )


def downgrade() -> None:
    op.drop_index(
        "ix_query_logs_workspace_id_route_type_created_at",
        table_name="query_logs",
    )
