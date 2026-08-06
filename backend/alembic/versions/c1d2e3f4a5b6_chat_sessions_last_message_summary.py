# =============================================================================
# File: c1d2e3f4a5b6_chat_sessions_last_message_summary.py
# Module/Service: Chat Service (FR4 Conversation Memory)
# Layer: Schema
# Purpose: Denormalized last-message summary columns on chat_sessions (Part 2).
# Responsibilities:
#   - Add last_message_preview, last_message_at, message_count
# Dependencies:
#   - revision c0d1e2f3a4b5
# Public Exports:
#   - upgrade, downgrade
# Database/Table: chat_sessions
# Related Modules: ChatSessionRepository.touch, MessageProcessingService
# Important Notes: OpenAPI ChatSession does not expose these fields yet; used
#   internally for session ordering / future FE summary enrichment.
# =============================================================================
"""chat_sessions last message summary

Revision ID: c1d2e3f4a5b6
Revises: c0d1e2f3a4b5
Create Date: 2026-08-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: str | None = "c0d1e2f3a4b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column("last_message_preview", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "chat_sessions",
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "chat_sessions",
        sa.Column(
            "message_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("chat_sessions", "message_count")
    op.drop_column("chat_sessions", "last_message_at")
    op.drop_column("chat_sessions", "last_message_preview")
