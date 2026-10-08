# =============================================================================
# File: l6m7n8o9p0q1_document_version_catalog.py
# Module/Service: Alembic
# Layer: Schema
# Purpose: Store version classification and an append-only edit history.
# Responsibilities:
#   - Add change_note, tags, classification_metadata on document_versions
#   - Create document_version_events and backfill one uploaded event per version
# Dependencies:
#   - revision k5l6m7n8o9p0
# Public Exports:
#   - upgrade, downgrade
# Database/Table: document_versions, document_version_events
# Related Modules: app.models.documents, app.services.versioning
# Important Notes: Additive. Existing versions stay valid with empty tags.
# =============================================================================
"""document version catalog and edit history

Revision ID: l6m7n8o9p0q1
Revises: k5l6m7n8o9p0
Create Date: 2026-10-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "l6m7n8o9p0q1"
down_revision: str | None = "k5l6m7n8o9p0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "document_versions",
        sa.Column("change_note", sa.String(length=2000), nullable=True),
    )
    op.add_column(
        "document_versions",
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "document_versions",
        sa.Column(
            "classification_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index(
        "ix_document_versions_tags_gin",
        "document_versions",
        ["tags"],
        unique=False,
        postgresql_using="gin",
    )

    op.create_table(
        "document_version_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("document_version_id", sa.UUID(), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.String(length=2000), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_document_version_events_workspace_created",
        "document_version_events",
        ["workspace_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_document_version_events_document_created",
        "document_version_events",
        ["document_id", "created_at"],
        unique=False,
    )

    op.execute(
        """
        INSERT INTO document_version_events (
            id,
            workspace_id,
            document_id,
            document_version_id,
            actor_id,
            event_type,
            summary,
            payload,
            created_at
        )
        SELECT
            gen_random_uuid(),
            d.workspace_id,
            d.id,
            v.id,
            v.uploaded_by,
            'uploaded',
            'Tải lên phiên bản v' || v.version_number::text,
            jsonb_build_object(
                'version_number', v.version_number,
                'file_size_bytes', v.file_size_bytes,
                'backfill', true
            ),
            v.created_at
        FROM document_versions AS v
        JOIN documents AS d ON d.id = v.document_id
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_document_version_events_document_created",
        table_name="document_version_events",
    )
    op.drop_index(
        "ix_document_version_events_workspace_created",
        table_name="document_version_events",
    )
    op.drop_table("document_version_events")
    op.drop_index("ix_document_versions_tags_gin", table_name="document_versions")
    op.drop_column("document_versions", "classification_metadata")
    op.drop_column("document_versions", "tags")
    op.drop_column("document_versions", "change_note")
