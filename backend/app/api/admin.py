# =============================================================================
# File: admin.py
# Module/Service: Observability Module (FR13 + FR14)
# Layer: Presentation
# Purpose: Admin observability endpoints (cost-summary).
# Responsibilities:
#   - GET /admin/workspaces/{workspaceId}/cost-summary
# Dependencies:
#   - require_workspace_admin_rl, CostSummaryService, get_db_session
# Public Exports:
#   - router
# Database/Table: message_generations, agent_events (via service)
# Related Modules: docs/Enterprise_notebooklm_openapi.yaml §Admin/Observability
# Important Notes: Admin-only; by_agent_type is additive (backward-compatible).
# =============================================================================

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.dependencies.rate_limit import require_workspace_admin_rl
from app.dependencies.rbac import WorkspaceAccess
from app.repositories.cost_summary import CostSummaryRepository
from app.schemas.admin import CostSummaryResponse
from app.schemas.common import ErrorResponse
from app.services.cost_summary import CostSummaryService

router = APIRouter(prefix="/admin/workspaces", tags=["Admin/Observability"])


def get_cost_summary_service(
    session: AsyncSession = Depends(get_db_session),
) -> CostSummaryService:
    return CostSummaryService(CostSummaryRepository(session))


@router.get(
    "/{workspaceId}/cost-summary",
    response_model=CostSummaryResponse,
    summary="Tổng hợp chi phí LLM theo model/route_type (+ by_agent_type FR14)",
    operation_id="getWorkspaceCostSummary",
    responses={
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    },
)
async def get_workspace_cost_summary(
    access: WorkspaceAccess = Depends(require_workspace_admin_rl),
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    service: CostSummaryService = Depends(get_cost_summary_service),
) -> CostSummaryResponse:
    """Aggregate message_generations + agent_events for the workspace."""
    return await service.get_summary(
        workspace_id=access.workspace_id,
        date_from=date_from,
        date_to=date_to,
    )
