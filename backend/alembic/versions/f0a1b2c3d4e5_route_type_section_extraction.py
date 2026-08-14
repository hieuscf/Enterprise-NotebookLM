# =============================================================================
# File: f0a1b2c3d4e5_route_type_section_extraction.py
# Module/Service: Query Router (FR11)
# Layer: Schema
# Purpose: Add route_type enum value section_extraction for structure-aware
#          document section listing (0 LLM).
# Responsibilities:
#   - ALTER TYPE route_type ADD VALUE 'section_extraction'
# Dependencies:
#   - Alembic, revision e9f0a1b2c3d4
# Public Exports:
#   - upgrade, downgrade
# Database/Table: query_logs.route_type, message_generations.route_type,
#   query_cache (no enum column — route lives on logs/generations)
# Related Modules: app.models.enums.RouteType
# Important Notes:
#   - Additive enum value only; no new tables/columns.
#   - PostgreSQL cannot drop an enum value — downgrade is a no-op.
# =============================================================================
"""Add section_extraction to route_type enum

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2026-08-15
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "f0a1b2c3d4e5"
down_revision: str | None = "e9f0a1b2c3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE route_type ADD VALUE IF NOT EXISTS 'section_extraction'")


def downgrade() -> None:
    # PostgreSQL cannot remove a value from an existing enum type without
    # recreating it. Leaving the unused value is safe.
    pass
