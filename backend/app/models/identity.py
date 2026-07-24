# =============================================================================
# File: identity.py
# Module/Service: Workspace Service / Auth
# Layer: Schema
# Purpose: ORM models for users, workspaces, roles, workspace_members.
# Responsibilities:
#   - Map identity & RBAC tables (FR1, FR12)
# Dependencies:
#   - app.db.base, app.models.enums, app.models.types
# Public Exports:
#   - User, Workspace, Role, WorkspaceMember
# Database/Table: users, workspaces, roles, workspace_members
# Related Modules: erd-enterprise-notebooklm.mermaid, OpenAPI User/Workspace
# Important Notes: Multi-tenant isolation starts at workspace_members.
# =============================================================================

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import RoleName, UserStatus
from app.models.types import (
    created_at_col,
    role_name_enum,
    updated_at_col,
    user_status_enum,
    uuid_pk,
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[UserStatus] = mapped_column(
        user_status_enum,
        nullable=False,
        server_default=UserStatus.active.value,
    )
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[RoleName] = mapped_column(role_name_enum, unique=True, nullable=False)
    permissions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_members_workspace_user"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
