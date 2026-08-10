# =============================================================================
# File: __init__.py
# Module/Service: Domain
# Layer: Domain
# Purpose: Domain package exports (permission helpers, pure rules).
# Responsibilities:
#   - Re-export commonly used domain helpers
# Dependencies:
#   - app.domain.permissions
# Public Exports:
#   - is_manage, is_workspace_admin, has_workspace_role
# Database/Table: N/A
# Related Modules: app.dependencies.rbac
# Important Notes: Keep domain helpers free of FastAPI / SQLAlchemy session I/O.
# =============================================================================

from app.domain.permissions import has_workspace_role, is_manage, is_workspace_admin

__all__ = ["is_manage", "is_workspace_admin", "has_workspace_role"]
