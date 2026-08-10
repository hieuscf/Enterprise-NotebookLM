# =============================================================================
# File: admin_health.py
# Module/Service: Observability Module — System Health (FR13)
# Layer: Presentation
# Purpose: Platform Manage endpoint GET /admin/health.
# Responsibilities:
#   - Require platform_role == manage
#   - Delegate to SystemHealthService
# Dependencies:
#   - require_platform_manage, SystemHealthService, get_db_session, Settings
# Public Exports:
#   - router
# Database/Table: N/A
# Related Modules: docs/Enterprise_notebooklm_openapi.yaml SystemHealth
# Important Notes: Workspace Admin cannot access /admin/*. No secrets in body.
# =============================================================================

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.dependencies.auth import CurrentUser
from app.dependencies.rbac import require_platform_manage
from app.schemas.admin import SystemHealthResponse
from app.schemas.common import ErrorResponse
from app.services.health import SystemHealthService

router = APIRouter(prefix="/admin", tags=["Admin/Observability"])


def get_system_health_service(
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> SystemHealthService:
    return SystemHealthService(session, settings)


@router.get(
    "/health",
    response_model=SystemHealthResponse,
    summary="System & dependency health (Manage)",
    operation_id="getAdminSystemHealth",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    },
)
async def get_admin_system_health(
    _manage: CurrentUser = Depends(require_platform_manage),
    service: SystemHealthService = Depends(get_system_health_service),
) -> SystemHealthResponse:
    """Return current availability of core + AI/retrieval dependencies."""
    return await service.get_health()
