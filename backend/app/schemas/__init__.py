# =============================================================================
# File: __init__.py
# Module/Service: Schemas
# Layer: Schema
# Purpose: Package marker for Pydantic request/response schemas (OpenAPI).
# Responsibilities:
#   - Define *CreateRequest / *Response / *Update models matching OpenAPI
# Dependencies:
#   - Pydantic
# Public Exports:
#   - Auth and User schemas (Phase 1.2)
# Database/Table: N/A
# Related Modules: docs/Enterprise notebooklm openapi.yaml, app.api
# Important Notes: OpenAPI YAML not checked into repo yet; schemas follow FR12 brief.
# =============================================================================

from app.schemas.auth import AuthToken, LoginRequest, RefreshRequest, Unauthorized
from app.schemas.common import ErrorResponse
from app.schemas.users import UserResponse, WorkspaceMembership
from app.schemas.workspaces import WorkspaceResponse

__all__ = [
    "AuthToken",
    "LoginRequest",
    "RefreshRequest",
    "Unauthorized",
    "ErrorResponse",
    "UserResponse",
    "WorkspaceMembership",
    "WorkspaceResponse",
]
