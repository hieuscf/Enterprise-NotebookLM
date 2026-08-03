# =============================================================================
# File: b9c0d1e2f3a4_agent_events_confidence_score_indexes.py
# Module/Service: Alembic
# Layer: Schema
# Purpose: FR14 audit-trail gaps — agent_events.confidence_score + composite indexes.
# Responsibilities:
#   - Add confidence_score on agent_events (score at agent trigger time)
#   - Index agent_events(agent_type, created_at DESC)
#   - Index retrievals(message_id, retrieval_pass, rank)
# Dependencies:
#   - database-design-enterprise-notebooklm.md v3, revision a8b9c0d1e2f3
#   - Prior v3 Part 2 (d4e5f6a7b8c9) already created agent_events / retrieval_pass /
#     message_generations confidence_* columns
# Public Exports:
#   - upgrade, downgrade
# Database/Table: agent_events, retrievals
# Related Modules: app.models.agent_events, app.models.retrieval
# Important Notes:
#   - Additive only; does not recreate tables/enums from d4e5f6a7b8c9.
#   - Does not mutate existing rows (new column nullable; indexes non-unique).
# =============================================================================
"""agent_events_confidence_score_indexes

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-08-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b9c0d1e2f3a4"
down_revision: str | None = "a8b9c0d1e2f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Confidence Engine score at the moment a Micro Agent was triggered
    # (distinct from message_generations.confidence_score = final answer score).
    op.add_column(
        "agent_events",
        sa.Column("confidence_score", sa.Float(), nullable=True),
    )

    op.create_index(
        "ix_agent_events_agent_type_created_at",
        "agent_events",
        ["agent_type", "created_at"],
        unique=False,
        postgresql_ops={"created_at": "DESC"},
    )

    op.create_index(
        "ix_retrievals_message_id_retrieval_pass_rank",
        "retrievals",
        ["message_id", "retrieval_pass", "rank"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_retrievals_message_id_retrieval_pass_rank",
        table_name="retrievals",
    )
    op.drop_index(
        "ix_agent_events_agent_type_created_at",
        table_name="agent_events",
    )
    op.drop_column("agent_events", "confidence_score")
