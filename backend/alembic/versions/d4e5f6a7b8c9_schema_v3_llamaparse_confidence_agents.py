# =============================================================================
# File: d4e5f6a7b8c9_schema_v3_llamaparse_confidence_agents.py
# Module/Service: Alembic
# Layer: Schema
# Purpose: Schema v3 migration — LlamaParse columns, hierarchical chunks,
#   pipeline stage enum, confidence/agent fields, agent_events table.
# Responsibilities:
#   - Add v3 columns to document_versions, document_chunks, retrievals,
#     message_generations
#   - Replace pipeline_stage enum (map v2 stage values → v3)
#   - Create agent_events + supporting PostgreSQL ENUM types
# Dependencies:
#   - database-design-enterprise-notebooklm.md v3, revision c3d4e5f6a7b8
# Public Exports:
#   - upgrade, downgrade
# Database/Table: document_versions, document_chunks, pipeline_stage_logs,
#   retrievals, message_generations, agent_events
# Related Modules: app.models.*
# Important Notes:
#   - Existing pipeline_stage_logs: ocr_cleaning→document_understanding,
#     chunking→hierarchical_chunking; embedding/graph/indexing unchanged.
#   - cleaning_normalize is new — no v2 rows.
# =============================================================================
"""schema_v3_llamaparse_confidence_agents

Revision ID: d4e5f6a7b8c9
Revises: f6a7b8c9d0e1
Create Date: 2026-07-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- document_versions: parser engine label (v3 Part 2) ---
    op.add_column(
        "document_versions",
        sa.Column(
            "parser",
            sa.String(length=64),
            nullable=False,
            server_default="llamaparse",
        ),
    )

    # --- retrievals (second retrieval pass) ---
    op.add_column(
        "retrievals",
        sa.Column("retrieval_pass", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index(
        "ix_retrievals_message_id_retrieval_pass",
        "retrievals",
        ["message_id", "retrieval_pass"],
        unique=False,
    )

    # --- message_generations (confidence engine) ---
    confidence_level = postgresql.ENUM(
        "high", "low", name="confidence_level", create_type=False
    )
    confidence_level.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "message_generations",
        sa.Column("confidence_level", confidence_level, nullable=True),
    )
    op.add_column(
        "message_generations",
        sa.Column("confidence_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "message_generations",
        sa.Column(
            "agent_triggered",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )

    # --- agent_events (event-driven micro agents) ---
    agent_type = postgresql.ENUM(
        "rewrite", "graph", "sql", name="agent_type", create_type=False
    )
    agent_trigger_reason = postgresql.ENUM(
        "ambiguous_query",
        "multi_hop_reasoning",
        "structured_misclassified",
        name="agent_trigger_reason",
        create_type=False,
    )
    agent_type.create(op.get_bind(), checkfirst=True)
    agent_trigger_reason.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "agent_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column("agent_type", agent_type, nullable=False),
        sa.Column("trigger_reason", agent_trigger_reason, nullable=False),
        sa.Column(
            "input_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "output_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "triggered_second_retrieval",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column("model_used", sa.String(length=128), nullable=True),
        sa.Column(
            "cost_usd",
            sa.Numeric(precision=10, scale=6),
            nullable=False,
            server_default="0",
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["message_id"], ["chat_messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_events_message_id", "agent_events", ["message_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_agent_events_message_id", table_name="agent_events")
    op.drop_table("agent_events")

    op.drop_column("message_generations", "agent_triggered")
    op.drop_column("message_generations", "confidence_score")
    op.drop_column("message_generations", "confidence_level")
    op.execute("DROP TYPE IF EXISTS confidence_level")

    op.drop_index("ix_retrievals_message_id_retrieval_pass", table_name="retrievals")
    op.drop_column("retrievals", "retrieval_pass")

    op.drop_column("document_versions", "parser")

    op.execute("DROP TYPE IF EXISTS agent_trigger_reason")
    op.execute("DROP TYPE IF EXISTS agent_type")
