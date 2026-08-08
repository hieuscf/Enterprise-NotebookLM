# =============================================================================
# File: query_logs.py
# Module/Service: Observability Module (FR13)
# Layer: Service
# Purpose: Admin listing of query_logs for workspace audit / cost routing.
# Responsibilities:
#   - List QueryLogResponse rows filtered by optional route_type + pagination
# Dependencies:
#   - QueryLogRepository, QueryLogResponse
# Public Exports:
#   - QueryLogsService
# Database/Table: query_logs
# Related Modules: app.api.admin, OpenAPI QueryLog
# Important Notes: Default sort is created_at DESC (repository).
# =============================================================================

from __future__ import annotations

import uuid

from app.models.enums import RouteType
from app.repositories.query_logs import QueryLogRepository
from app.schemas.admin import QueryLogResponse


class QueryLogsService:
    """Admin read-side for ``GET /admin/.../query-logs``."""

    def __init__(self, repo: QueryLogRepository) -> None:
        self._repo = repo

    async def list_logs(
        self,
        *,
        workspace_id: uuid.UUID,
        route_type: RouteType | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[QueryLogResponse]:
        rows = await self._repo.list_for_workspace(
            workspace_id=workspace_id,
            route_type=route_type,
            page=page,
            page_size=page_size,
        )
        return [QueryLogResponse.model_validate(row) for row in rows]
