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
Revises: c3d4e5f6a7b8
Create Date: 2026-07-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PIPELINE_STAGE_V3 = (
    "document_understanding",
    "cleaning_normalize",
    "hierarchical_chunking",
    "embedding",
    "graph_extraction",
    "indexing",
)

_PIPELINE_STAGE_V2 = (
    "ocr_cleaning",
    "chunking",
    "embedding",
    "graph_extraction",
    "indexing",
)


def _replace_pipeline_stage_enum(*, to_v3: bool) -> None:
    if to_v3:
        new_values = _PIPELINE_STAGE_V3
        case_sql = """
            CASE stage::text
                WHEN 'ocr_cleaning' THEN 'document_understanding'
                WHEN 'chunking' THEN 'hierarchical_chunking'
                ELSE stage::text
            END
        """
    else:
        new_values = _PIPELINE_STAGE_V2
        case_sql = """
            CASE stage::text
                WHEN 'document_understanding' THEN 'ocr_cleaning'
                WHEN 'cleaning_normalize' THEN 'ocr_cleaning'
                WHEN 'hierarchical_chunking' THEN 'chunking'
                ELSE stage::text
            END
        """

    tmp_name = "pipeline_stage_new"
    values_sql = ", ".join(f"'{v}'" for v in new_values)
    op.execute(f"CREATE TYPE {tmp_name} AS ENUM ({values_sql})")
    op.execute(
        f"""
        ALTER TABLE pipeline_stage_logs
        ALTER COLUMN stage TYPE {tmp_name}
        USING ({case_sql})::{tmp_name}
        """
    )
    op.execute("DROP TYPE pipeline_stage")
    op.execute(f"ALTER TYPE {tmp_name} RENAME TO pipeline_stage")


def upgrade() -> None:
    # --- document_versions (LlamaParse metadata) ---
    op.add_column(
        "document_versions",
        sa.Column(
            "parser",
            sa.String(length=64),
            nullable=False,
            server_default="llamaparse",
        ),
    )
    op.add_column(
        "document_versions",
        sa.Column("markdown_storage_path", sa.String(length=1024), nullable=True),
    )
    op.add_column(
        "document_versions",
        sa.Column("layout_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # --- document_chunks (hierarchical chunking) ---
    chunk_layout_type = postgresql.ENUM(
        "paragraph",
        "heading",
        "table",
        "list",
        name="chunk_layout_type",
        create_type=True,
    )
    chunk_layout_type.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "document_chunks",
        sa.Column("parent_chunk_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("heading_path", sa.String(length=1024), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("depth", sa.Integer(), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("layout_type", chunk_layout_type, nullable=True),
    )
    op.create_foreign_key(
        "fk_document_chunks_parent_chunk_id",
        "document_chunks",
        "document_chunks",
        ["parent_chunk_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_document_chunks_parent_chunk_id",
        "document_chunks",
        ["parent_chunk_id"],
        unique=False,
    )

    # --- pipeline_stage enum v2 → v3 ---
    _replace_pipeline_stage_enum(to_v3=True)

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
    confidence_level = postgresql.ENUM("high", "low", name="confidence_level", create_type=True)
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
    agent_type = postgresql.ENUM("rewrite", "graph", "sql", name="agent_type", create_type=True)
    agent_trigger_reason = postgresql.ENUM(
        "ambiguous_query",
        "multi_hop_reasoning",
        "structured_misclassified",
        name="agent_trigger_reason",
        create_type=True,
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

    _replace_pipeline_stage_enum(to_v3=False)

    op.drop_index("ix_document_chunks_parent_chunk_id", table_name="document_chunks")
    op.drop_constraint("fk_document_chunks_parent_chunk_id", "document_chunks", type_="foreignkey")
    op.drop_column("document_chunks", "layout_type")
    op.drop_column("document_chunks", "depth")
    op.drop_column("document_chunks", "heading_path")
    op.drop_column("document_chunks", "parent_chunk_id")
    op.execute("DROP TYPE IF EXISTS chunk_layout_type")

    op.drop_column("document_versions", "layout_metadata")
    op.drop_column("document_versions", "markdown_storage_path")
    op.drop_column("document_versions", "parser")

    op.execute("DROP TYPE IF EXISTS agent_trigger_reason")
    op.execute("DROP TYPE IF EXISTS agent_type")
