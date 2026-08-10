# =============================================================================
# File: e9f0a1b2c3d4_users_platform_role.py
# Module/Service: Auth Service / Platform RBAC (FR12)
# Layer: Schema
# Purpose: Add nullable users.platform_role for Enterprise Manage (platform scope).
# Responsibilities:
#   - Create PostgreSQL enum platform_role ('manage' only)
#   - Add users.platform_role nullable column (NULL = ordinary user)
#   - Optionally promote BOOTSTRAP_MANAGE_EMAIL if set (env at migrate time)
# Dependencies:
#   - Alembic, revision d8e9f0a1b2c3
# Public Exports:
#   - upgrade, downgrade
# Database/Table: users
# Related Modules: app.models.identity.User, app.dependencies.rbac
# Important Notes:
#   - Does NOT promote existing workspace admins to manage.
#   - Does NOT add manage to roles / role_name (workspace-scoped only).
#   - Rollback: drop column + enum type.
# =============================================================================
"""users.platform_role for Platform Manage RBAC

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-08-11
"""

from __future__ import annotations

import os
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e9f0a1b2c3d4"
down_revision: str | None = "d8e9f0a1b2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

platform_role_enum = postgresql.ENUM("manage", name="platform_role", create_type=False)


def upgrade() -> None:
    op.execute("CREATE TYPE platform_role AS ENUM ('manage')")
    op.add_column(
        "users",
        sa.Column("platform_role", platform_role_enum, nullable=True),
    )

    # Optional bootstrap: promote an existing account by email. Never invents a
    # password and never promotes workspace admins en masse.
    bootstrap_email = (os.environ.get("BOOTSTRAP_MANAGE_EMAIL") or "").strip().lower()
    if bootstrap_email:
        op.execute(
            sa.text(
                "UPDATE users SET platform_role = CAST('manage' AS platform_role) "
                "WHERE lower(email) = :email AND platform_role IS NULL"
            ).bindparams(email=bootstrap_email)
        )


def downgrade() -> None:
    op.drop_column("users", "platform_role")
    op.execute("DROP TYPE IF EXISTS platform_role")
