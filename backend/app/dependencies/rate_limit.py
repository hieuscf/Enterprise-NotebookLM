# =============================================================================
# File: rate_limit.py
# Module/Service: API Gateway / Auth Middleware
# Layer: Presentation
# Purpose: FastAPI dependency that rate-limits after workspace RBAC succeeds.
# Responsibilities:
#   - rate_limited(rbac_dep): run RBAC first, then consume workspace quota
#   - Raise 429 + Retry-After when over limit
# Dependencies:
#   - app.core.rate_limit, app.core.config, app.dependencies.rbac
# Public Exports:
#   - rate_limited
#   - require_workspace_member_rl, require_workspace_editor_rl, require_workspace_admin_rl
# Database/Table: N/A
# Related Modules: app.api.workspaces
# Important Notes:
#   - API-layer limit only (FR12). LLM call quotas are separate (phase 2).
#   - Must wrap require_workspace_role so workspace_id is known and authorized.
# =============================================================================

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Depends, HTTPException, status

from app.core.config import Settings, get_settings
from app.core.rate_limit import WorkspaceRateLimiter, get_workspace_rate_limiter
from app.dependencies.rbac import (
    WorkspaceAccess,
    require_workspace_admin,
    require_workspace_editor,
    require_workspace_member,
)
from app.schemas.common import ErrorResponse


def rate_limited(
    rbac_dependency: Callable[..., Coroutine[Any, Any, WorkspaceAccess]],
) -> Callable[..., Coroutine[Any, Any, WorkspaceAccess]]:
    """Compose RBAC + per-workspace rate limit (RBAC always runs first)."""

    async def _dependency(
        access: WorkspaceAccess = Depends(rbac_dependency),
        limiter: WorkspaceRateLimiter = Depends(get_workspace_rate_limiter),
        settings: Settings = Depends(get_settings),
    ) -> WorkspaceAccess:
        result = limiter.hit(
            access.workspace_id,
            limit=settings.rate_limit_requests_per_minute,
            window_seconds=settings.rate_limit_window_seconds,
        )
        if not result.allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=ErrorResponse(
                    code="rate_limited",
                    message="Workspace API rate limit exceeded",
                ).model_dump(),
                headers={"Retry-After": str(result.retry_after)},
            )
        return access

    return _dependency


# Convenience deps for routers (RBAC allow-list + rate limit).
require_workspace_member_rl = rate_limited(require_workspace_member)
require_workspace_editor_rl = rate_limited(require_workspace_editor)
require_workspace_admin_rl = rate_limited(require_workspace_admin)
