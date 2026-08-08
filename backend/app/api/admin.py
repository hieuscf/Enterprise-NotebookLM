# =============================================================================
# File: admin.py
# Module/Service: Observability Module (FR13 + FR14)
# Layer: Presentation
# Purpose: Admin observability endpoints (query-logs, cost-summary).
# Responsibilities:
#   - GET /admin/workspaces/{workspaceId}/query-logs
#   - GET /admin/workspaces/{workspaceId}/cost-summary
# Dependencies:
#   - require_workspace_admin_rl, QueryLogsService, CostSummaryService, get_db_session
# Public Exports:
#   - router
# Database/Table: query_logs, message_generations, agent_events (via services)
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
from app.models.enums import RouteType
from app.repositories.cost_summary import CostSummaryRepository
from app.repositories.query_logs import QueryLogRepository
from app.schemas.admin import CostSummaryResponse, QueryLogResponse
from app.schemas.common import ErrorResponse
from app.services.cost_summary import CostSummaryService
from app.services.query_logs import QueryLogsService

router = APIRouter(prefix="/admin/workspaces", tags=["Admin/Observability"])


def get_cost_summary_service(
    session: AsyncSession = Depends(get_db_session),
) -> CostSummaryService:
    return CostSummaryService(CostSummaryRepository(session))


def get_query_logs_service(
    session: AsyncSession = Depends(get_db_session),
) -> QueryLogsService:
    return QueryLogsService(QueryLogRepository(session))


@router.get(
    "/{workspaceId}/query-logs",
    response_model=list[QueryLogResponse],
    summary="Log định tuyến truy vấn (route_type, llm_calls_count, latency) — audit chi phí",
    operation_id="listWorkspaceQueryLogs",
    responses={
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    },
)
async def list_workspace_query_logs(
    access: WorkspaceAccess = Depends(require_workspace_admin_rl),
    route_type: RouteType | None = Query(
        None,
        description="Filter by Query Router route_type",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: QueryLogsService = Depends(get_query_logs_service),
) -> list[QueryLogResponse]:
    """List ``query_logs`` for the workspace (admin-only), newest first."""
    return await service.list_logs(
        workspace_id=access.workspace_id,
        route_type=route_type,
        page=page,
        page_size=page_size,
    )


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
