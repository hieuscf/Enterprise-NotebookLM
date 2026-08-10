# =============================================================================
# File: permissions.py
# Module/Service: Auth Service / Platform + Workspace RBAC (FR12)
# Layer: Domain
# Purpose: Pure permission helpers separating Platform Manage from Workspace roles.
# Responsibilities:
#   - is_manage — platform_role == manage
#   - is_workspace_admin / has_workspace_role — workspace-scoped checks
# Dependencies:
#   - app.models.enums
# Public Exports:
#   - is_manage, is_workspace_admin, has_workspace_role
# Database/Table: N/A (callers supply already-loaded role values)
# Related Modules: app.dependencies.rbac, app.services.admin_users
# Important Notes:
#   - manage ≠ workspace admin; scopes are independent.
#   - Never treat owner_id as a platform or workspace role.
# =============================================================================

from __future__ import annotations

from typing import Protocol

from app.models.enums import PlatformRole, RoleName


class _HasPlatformRole(Protocol):
    platform_role: PlatformRole | None


def is_manage(user: _HasPlatformRole) -> bool:
    """True when the user holds the Enterprise Platform Manage role."""
    return user.platform_role == PlatformRole.manage


def is_workspace_admin(role: RoleName | str | None) -> bool:
    """True when the resolved workspace membership role is admin."""
    if role is None:
        return False
    value = role.value if isinstance(role, RoleName) else role
    return value == RoleName.admin.value


def has_workspace_role(
    role: RoleName | str | None,
    *allowed: RoleName | str,
) -> bool:
    """True when role is one of the allowed workspace roles."""
    if role is None or not allowed:
        return False
    value = role.value if isinstance(role, RoleName) else str(role)
    allowed_values = {
        a.value if isinstance(a, RoleName) else str(a) for a in allowed
    }
    return value in allowed_values
