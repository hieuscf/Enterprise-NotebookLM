# =============================================================================
# File: __init__.py
# Module/Service: API Gateway / Auth Middleware
# Layer: Presentation
# Purpose: FastAPI dependency injection for auth and DB wiring.
# Responsibilities:
#   - Package marker for reusable Depends factories (auth + RBAC)
# Dependencies:
#   - FastAPI
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: app.dependencies.auth, app.dependencies.rbac
# Important Notes: Prefer factories here over hardcoding checks in each route.
# =============================================================================
