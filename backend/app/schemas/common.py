# =============================================================================
# File: common.py
# Module/Service: API Gateway / Auth Middleware
# Layer: Schema
# Purpose: Shared OpenAPI Error schema (Unauthorized / Forbidden bodies).
# Responsibilities:
#   - Define Error model matching Enterprise_notebooklm_openapi.yaml
# Dependencies:
#   - Pydantic
# Public Exports:
#   - ErrorResponse
# Database/Table: N/A
# Related Modules: app.dependencies.auth, app.api.*
# Important Notes: OpenAPI components.schemas.Error — {code, message}.
# =============================================================================

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    code: str
    message: str
