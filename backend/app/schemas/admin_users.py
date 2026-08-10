# =============================================================================
# File: admin_users.py
# Module/Service: Auth Service / Admin User Management (FR12)
# Layer: Schema
# Purpose: Pydantic request/response models for Admin User CRUD
#          (POST/GET/DELETE /admin/users).
# Responsibilities:
#   - Define CreateAdminUserRequest, AdminUserResponse, AdminUserListItem
# Dependencies:
#   - Pydantic EmailStr
# Public Exports:
#   - CreateAdminUserRequest, AdminUserResponse, AdminUserMembership,
#     AdminUserListItem, AdminUserListResponse
# Database/Table: users, workspace_members, roles, workspaces
# Related Modules: app.api.admin_users, docs/Enterprise_notebooklm_openapi.yaml
# Important Notes:
#   - Never expose password_hash. Client sends plain `password` only.
#   - Password policy matches LoginRequest (min_length=1) — no extra rules.
# =============================================================================

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class CreateAdminUserRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)
    full_name: str = Field(min_length=1, max_length=255)


class AdminUserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str


class AdminUserMembership(BaseModel):
    workspace_id: UUID
    workspace_name: str
    role: Literal["admin", "editor", "viewer"]
    joined_at: datetime


class AdminUserListItem(BaseModel):
    user_id: UUID
    # str (not EmailStr): list must not 500 on legacy/invalid stored emails.
    email: str
    full_name: str
    memberships: list[AdminUserMembership]


class AdminUserListResponse(BaseModel):
    items: list[AdminUserListItem]
