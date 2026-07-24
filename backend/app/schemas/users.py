# =============================================================================
# File: users.py
# Module/Service: Auth Service
# Layer: Schema
# Purpose: Pydantic User response models for GET /auth/me (FR12).
# Responsibilities:
#   - Define User and workspace membership role projection
# Dependencies:
#   - Pydantic
# Public Exports:
#   - WorkspaceMembership, UserResponse
# Database/Table: users, workspace_members, roles
# Related Modules: app.api.auth, app.services.auth
# Important Notes: workspaces always loaded from DB at call time (not JWT only).
# =============================================================================

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr


class WorkspaceMembership(BaseModel):
    workspace_id: UUID
    role: Literal["admin", "editor", "viewer"]


class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    full_name: str
    workspaces: list[WorkspaceMembership]
