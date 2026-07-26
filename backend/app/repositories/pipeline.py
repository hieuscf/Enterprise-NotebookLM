# =============================================================================
# File: pipeline.py
# Module/Service: Document Ingestion Service / Observability Module
# Layer: Repository
# Purpose: Async data access for pipeline_runs + pipeline_stage_logs (FR2/FR13).
# Responsibilities:
#   - Create pending runs on upload; load run + stages for status API
# Dependencies:
#   - SQLAlchemy AsyncSession, app.models.pipeline
# Public Exports:
#   - PipelineRepository
# Database/Table: pipeline_runs, pipeline_stage_logs
# Related Modules: app.services.documents, app.api.documents
# Important Notes: Stage writes during processing use sync repos in Celery worker.
# =============================================================================

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PipelineStatus
from app.models.pipeline import PipelineRun, PipelineStageLog


class PipelineRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_run(self, document_version_id: uuid.UUID) -> PipelineRun:
        run = PipelineRun(
            document_version_id=document_version_id,
            status=PipelineStatus.pending,
            retry_count=0,
        )
        self._session.add(run)
        await self._session.flush()
        return run

    async def get_latest_run_with_stages(
        self,
        document_version_id: uuid.UUID,
    ) -> PipelineRun | None:
        """Return the most recent pipeline_run for a version, with stage logs.

        Stages are loaded via a separate query ordered by started_at because
        PipelineRun has no ORM relationship configured (schema-first models).
        """
        stmt = (
            select(PipelineRun)
            .where(PipelineRun.document_version_id == document_version_id)
            .order_by(PipelineRun.started_at.desc().nullslast(), PipelineRun.id.desc())
            .limit(1)
        )
        run = (await self._session.execute(stmt)).scalar_one_or_none()
        if run is None:
            return None

        stages_stmt = (
            select(PipelineStageLog)
            .where(PipelineStageLog.pipeline_run_id == run.id)
            .order_by(PipelineStageLog.started_at.asc().nullslast(), PipelineStageLog.id.asc())
        )
        stages = list((await self._session.execute(stages_stmt)).scalars().all())
        # Attach transient attribute for service/API mapping (not an ORM relationship).
        run.stages = stages  # type: ignore[attr-defined]
        return run
