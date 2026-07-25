# =============================================================================
# File: workspaces.py
# Module/Service: Workspace Service
# Layer: Schema
# Purpose: Pydantic request/response models for Workspace CRUD (FR1 / OpenAPI).
# Responsibilities:
#   - Match OpenAPI Workspace, WorkspaceListResponse, create/update bodies
# Dependencies:
#   - Pydantic
# Public Exports:
#   - WorkspaceCreateRequest, WorkspaceUpdateRequest
#   - WorkspaceResponse, WorkspaceListResponse
# Database/Table: workspaces
# Related Modules: app.api.workspaces, docs/Enterprise_notebooklm_openapi.yaml
# Important Notes: deleted_at is internal — not exposed in API response schema.
# =============================================================================

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)


class WorkspaceUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)


class WorkspaceResponse(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class WorkspaceListResponse(BaseModel):
    items: list[WorkspaceResponse]
    page: int
    page_size: int
    total: int
