# =============================================================================
# File: members.py
# Module/Service: Workspace Service
# Layer: Schema
# Purpose: Pydantic models for WorkspaceMember APIs (FR1 / UC10 / OpenAPI).
# Responsibilities:
#   - Match OpenAPI WorkspaceMember + add/update request bodies
# Dependencies:
#   - Pydantic
# Public Exports:
#   - WorkspaceMemberResponse, AddMemberRequest, UpdateMemberRoleRequest
# Database/Table: workspace_members, users, roles
# Related Modules: app.api.workspaces, docs/Enterprise_notebooklm_openapi.yaml
# Important Notes: role is OpenAPI string enum; DB stores role_id FK → roles.id.
# =============================================================================

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

WorkspaceRole = Literal["admin", "editor", "viewer"]


class AddMemberRequest(BaseModel):
    user_id: UUID
    role: WorkspaceRole


class UpdateMemberRoleRequest(BaseModel):
    role: WorkspaceRole


class WorkspaceMemberResponse(BaseModel):
    user_id: UUID
    email: str
    role: WorkspaceRole
    joined_at: datetime
