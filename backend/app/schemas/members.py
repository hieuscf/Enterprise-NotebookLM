# =============================================================================
# File: members.py
# Module/Service: Workspace Service
# Layer: Schema
# Purpose: Pydantic models for WorkspaceMember APIs (FR1 / UC10 / OpenAPI).
# Responsibilities:
#   - Match OpenAPI WorkspaceMember + add/update request bodies
#   - MemberCandidate for invite directory search
# Dependencies:
#   - Pydantic
# Public Exports:
#   - WorkspaceMemberResponse, AddMemberRequest, UpdateMemberRoleRequest
#   - MemberCandidateResponse
# Database/Table: workspace_members, users, roles
# Related Modules: app.api.workspaces, docs/Enterprise_notebooklm_openapi.yaml
# Important Notes: AddMember accepts user_id OR email (at least one required).
# =============================================================================

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, model_validator

WorkspaceRole = Literal["admin", "editor", "viewer"]


class AddMemberRequest(BaseModel):
    """Invite payload — identify the user by UUID and/or email."""

    user_id: UUID | None = None
    email: EmailStr | None = None
    role: WorkspaceRole

    @model_validator(mode="after")
    def require_user_id_or_email(self) -> Self:
        if self.user_id is None and self.email is None:
            raise ValueError("Provide user_id or email")
        return self


class UpdateMemberRoleRequest(BaseModel):
    role: WorkspaceRole


class WorkspaceMemberResponse(BaseModel):
    user_id: UUID
    email: str
    role: WorkspaceRole
    joined_at: datetime


class MemberCandidateResponse(BaseModel):
    """Active user eligible to invite (not already an active member)."""

    user_id: UUID
    email: str
    full_name: str
