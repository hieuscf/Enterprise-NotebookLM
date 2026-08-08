# =============================================================================
# File: pipeline.py
# Module/Service: Document Ingestion Service / Observability Module
# Layer: Repository
# Purpose: Async data access for pipeline_runs + pipeline_stage_logs (FR2/FR13).
# Responsibilities:
#   - Create pending runs on upload; load run + stages for status API
#   - list_for_workspace — admin list via document_versions → documents JOIN
# Dependencies:
#   - SQLAlchemy AsyncSession, app.models.pipeline, documents
# Public Exports:
#   - PipelineRepository
# Database/Table: pipeline_runs, pipeline_stage_logs, document_versions, documents
# Related Modules: app.services.documents, app.services.pipeline_runs, app.api.admin
# Important Notes: Stage writes during processing use sync repos in Celery worker.
# =============================================================================

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.documents import Document, DocumentVersion
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

    async def list_for_workspace(
        self,
        *,
        workspace_id: uuid.UUID,
        status: PipelineStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[PipelineRun]:
        """List pipeline_runs for a workspace via document_versions → documents.

        ``pipeline_runs`` has no ``workspace_id``; scope is enforced by JOIN.
        Each returned run has a transient ``stages`` list from ``pipeline_stage_logs``.
        """
        page = max(1, page)
        page_size = min(100, max(1, page_size))
        offset = (page - 1) * page_size

        stmt = (
            select(PipelineRun)
            .join(
                DocumentVersion,
                DocumentVersion.id == PipelineRun.document_version_id,
            )
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(Document.workspace_id == workspace_id)
        )
        if status is not None:
            stmt = stmt.where(PipelineRun.status == status)
        stmt = (
            stmt.order_by(
                PipelineRun.started_at.desc().nullslast(),
                PipelineRun.id.desc(),
            )
            .offset(offset)
            .limit(page_size)
        )
        runs = list((await self._session.scalars(stmt)).all())
        if not runs:
            return []

        run_ids = [run.id for run in runs]
        stages_stmt = (
            select(PipelineStageLog)
            .where(PipelineStageLog.pipeline_run_id.in_(run_ids))
            .order_by(
                PipelineStageLog.started_at.asc().nullslast(),
                PipelineStageLog.id.asc(),
            )
        )
        stages = list((await self._session.scalars(stages_stmt)).all())
        by_run: dict[uuid.UUID, list[PipelineStageLog]] = defaultdict(list)
        for stage in stages:
            by_run[stage.pipeline_run_id].append(stage)
        for run in runs:
            run.stages = by_run[run.id]  # type: ignore[attr-defined]
        return runs
