# =============================================================================
# File: __init__.py
# Module/Service: API Gateway / Auth Middleware
# Layer: Presentation
# Purpose: Package marker for FastAPI routers (OpenAPI resource modules).
# Responsibilities:
#   - Hold FastAPI APIRouter modules matching Enterprise_notebooklm_openapi.yaml
# Dependencies:
#   - FastAPI, app.services
# Public Exports:
#   - auth.router
# Database/Table: N/A
# Related Modules: docs/Enterprise notebooklm openapi.yaml
# Important Notes: Maps to "routers/" in architecture rules (folder name: api/).
# =============================================================================

from app.api.auth import router as auth_router
from app.api.workspaces import router as workspaces_router

__all__ = ["auth_router", "workspaces_router"]
