# =============================================================================
# File: pipeline_runs.py
# Module/Service: Observability Module (FR13)
# Layer: Service
# Purpose: Admin listing of pipeline_runs with nested stage logs.
# Responsibilities:
#   - List PipelineRunResponse for a workspace (status filter + pagination)
#   - Map ORM runs + transient stages → OpenAPI PipelineRun shape
# Dependencies:
#   - PipelineRepository, PipelineRunResponse schemas
# Public Exports:
#   - PipelineRunsService
# Database/Table: pipeline_runs, pipeline_stage_logs (via repo JOIN)
# Related Modules: app.api.admin, OpenAPI PipelineRun
# Important Notes: Workspace scope is repo JOIN — never trust client filters alone.
# =============================================================================

from __future__ import annotations

import uuid

from app.models.enums import PipelineStatus
from app.models.pipeline import PipelineRun, PipelineStageLog
from app.repositories.pipeline import PipelineRepository
from app.schemas.documents import PipelineRunResponse, PipelineStageLogResponse


class PipelineRunsService:
    """Admin read-side for ``GET /admin/.../pipeline-runs``."""

    def __init__(self, repo: PipelineRepository) -> None:
        self._repo = repo

    async def list_runs(
        self,
        *,
        workspace_id: uuid.UUID,
        status: PipelineStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[PipelineRunResponse]:
        rows = await self._repo.list_for_workspace(
            workspace_id=workspace_id,
            status=status,
            page=page,
            page_size=page_size,
        )
        return [_run_response(row) for row in rows]


def _stage_response(log: PipelineStageLog) -> PipelineStageLogResponse:
    return PipelineStageLogResponse(
        id=log.id,
        stage=log.stage.value,  # type: ignore[arg-type]
        status=log.status.value,  # type: ignore[arg-type]
        duration_ms=log.duration_ms,
        metadata=log.metadata_,
        error_message=log.error_message,
    )


def _run_response(run: PipelineRun) -> PipelineRunResponse:
    stages = getattr(run, "stages", []) or []
    file_type = getattr(run, "document_file_type", None)
    return PipelineRunResponse(
        id=run.id,
        document_version_id=run.document_version_id,
        status=run.status.value,  # type: ignore[arg-type]
        retry_count=run.retry_count,
        error_message=run.error_message,
        stages=[_stage_response(s) for s in stages],
        started_at=run.started_at,
        completed_at=run.completed_at,
        document_id=getattr(run, "document_id", None),
        document_title=getattr(run, "document_title", None),
        file_type=file_type.value if file_type is not None else None,
        version_number=getattr(run, "version_number", None),
    )
