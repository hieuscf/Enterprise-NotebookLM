# =============================================================================
# File: a1b2c3d4e5f6_workspaces_soft_delete_and_seed_roles.py
# Module/Service: Workspace Service
# Layer: Schema
# Purpose: Phase 1.3 — soft-delete workspaces/members + idempotent roles seed.
# Responsibilities:
#   - Add workspaces.deleted_at + index (soft DELETE /workspaces/{id})
#   - Add workspace_members.deleted_at + partial unique index (re-invite safe)
#   - Seed roles (admin/editor/viewer) idempotently — required by role_id FK
# Dependencies:
#   - Alembic, revision 6ebf6936f6c1 (initial schema v2)
# Public Exports:
#   - upgrade, downgrade
# Database/Table: workspaces, workspace_members, roles
# Related Modules: FR1 Workspace Management; database-design (extension)
# Important Notes:
#   - Soft-delete extends schema v2 (hard delete cascades FK children).
#   - workspace_members.role_id is FK → roles.id (NOT an inline ENUM column).
#     OpenAPI exposes role as string enum via JOIN roles.name; RBAC 1.2 already
#     compares RoleName from that join — seed is mandatory before any create.
# =============================================================================

"""workspaces soft-delete + seed roles

Revision ID: a1b2c3d4e5f6
Revises: 6ebf6936f6c1
Create Date: 2026-07-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "6ebf6936f6c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- workspaces soft-delete ---
    op.add_column(
        "workspaces",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_workspaces_deleted_at"),
        "workspaces",
        ["deleted_at"],
        unique=False,
    )

    # --- workspace_members soft-delete ---
    # When a workspace is soft-deleted, members are soft-deleted too so RBAC
    # (get_role_for_user) no longer treats them as active members.
    op.add_column(
        "workspace_members",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_workspace_members_deleted_at"),
        "workspace_members",
        ["deleted_at"],
        unique=False,
    )
    # Replace plain UNIQUE(workspace_id, user_id) with a partial unique index so
    # a user can be re-invited after soft-delete (only one active row allowed).
    op.drop_constraint(
        "uq_workspace_members_workspace_user",
        "workspace_members",
        type_="unique",
    )
    op.create_index(
        "uq_workspace_members_workspace_user_active",
        "workspace_members",
        ["workspace_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # --- seed roles (idempotent via UNIQUE(name) + ON CONFLICT DO NOTHING) ---
    # role_id FK on workspace_members makes this mandatory before POST /workspaces.
    conn = op.get_bind()
    for role_name in ("admin", "editor", "viewer"):
        conn.execute(
            sa.text(
                """
                INSERT INTO roles (id, name, permissions)
                VALUES (gen_random_uuid(), CAST(:name AS role_name), '{}'::jsonb)
                ON CONFLICT (name) DO NOTHING
                """
            ),
            {"name": role_name},
        )


def downgrade() -> None:
    op.drop_index(
        "uq_workspace_members_workspace_user_active",
        table_name="workspace_members",
    )
    op.create_unique_constraint(
        "uq_workspace_members_workspace_user",
        "workspace_members",
        ["workspace_id", "user_id"],
    )
    op.drop_index(op.f("ix_workspace_members_deleted_at"), table_name="workspace_members")
    op.drop_column("workspace_members", "deleted_at")

    # Do not delete seeded roles — other rows may reference them.
    op.drop_index(op.f("ix_workspaces_deleted_at"), table_name="workspaces")
    op.drop_column("workspaces", "deleted_at")
