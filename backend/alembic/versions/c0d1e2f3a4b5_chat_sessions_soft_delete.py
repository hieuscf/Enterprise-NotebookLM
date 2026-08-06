# =============================================================================
# File: c0d1e2f3a4b5_chat_sessions_soft_delete.py
# Module/Service: Chat Service (FR4 Conversation Memory)
# Layer: Schema
# Purpose: Soft-delete columns on chat_sessions for audit-safe DELETE.
# Responsibilities:
#   - Add deleted_at / deleted_by (nullable) — soft DELETE only
#   - Index active-list filter (workspace_id, user_id) where deleted_at IS NULL
# Dependencies:
#   - revision b9c0d1e2f3a4
# Public Exports:
#   - upgrade, downgrade
# Database/Table: chat_sessions
# Related Modules: app.models.chat.ChatSession, Phase 2.4 Part 1
# Important Notes:
#   - Does not hard-delete sessions/messages (cost-summary / analytics retain rows).
#   - Downgrade drops columns only; no other tables affected.
# =============================================================================
"""chat_sessions soft-delete

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
Create Date: 2026-08-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c0d1e2f3a4b5"
down_revision: str | None = "b9c0d1e2f3a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "chat_sessions",
        sa.Column("deleted_by", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_chat_sessions_deleted_by_users",
        "chat_sessions",
        "users",
        ["deleted_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_chat_sessions_workspace_id_user_id_active",
        "chat_sessions",
        ["workspace_id", "user_id"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_chat_sessions_workspace_id_user_id_active",
        table_name="chat_sessions",
    )
    op.drop_constraint(
        "fk_chat_sessions_deleted_by_users",
        "chat_sessions",
        type_="foreignkey",
    )
    op.drop_column("chat_sessions", "deleted_by")
    op.drop_column("chat_sessions", "deleted_at")
