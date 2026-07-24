# =============================================================================
# File: workspaces.py
# Module/Service: Workspace Service
# Layer: Schema
# Purpose: Pydantic Workspace response for demo GET /workspaces/{workspaceId}.
# Responsibilities:
#   - Match OpenAPI Workspace schema (minimal fields for RBAC demo)
# Dependencies:
#   - Pydantic
# Public Exports:
#   - WorkspaceResponse
# Database/Table: workspaces
# Related Modules: app.api.workspaces, docs/Enterprise_notebooklm_openapi.yaml
# Important Notes: Full Workspace CRUD belongs to phase 1.3 — read-only demo here.
# =============================================================================

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class WorkspaceResponse(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime
