# =============================================================================
# File: analysis_service.py
# Module/Service: Document Analysis Service
# Layer: Service
# Purpose: On-demand AI analysis for a document version (upload ≠ analysis).
# Responsibilities:
#   - GET current ai_analysis_status (never enqueues)
#   - POST enqueue run_pipeline when AI is enabled; idempotent if READY/in-flight
# Dependencies:
#   - DocumentRepository, PipelineRepository, Settings, AI Gateway
# Public Exports:
#   - AnalysisService, AnalysisServiceError
# Database/Table: document_versions, pipeline_runs
# Related Modules: app.workers.pipeline, app.api.documents
# Important Notes: Duplicate POST on READY/QUEUED/PROCESSING does not re-index.
# =============================================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.integrations.ai.exceptions import AI_DISABLED, AIGatewayError
from app.integrations.ai.gateway import get_ai_gateway
from app.models.documents import DocumentVersion
from app.models.enums import AiAnalysisStatus, PipelineStatus
from app.models.pipeline import PipelineRun
from app.repositories.documents import DocumentRepository
from app.repositories.pipeline import PipelineRepository

logger = get_logger(__name__)


class AnalysisServiceError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class AnalysisSnapshot:
    version: DocumentVersion
    pipeline_run: PipelineRun | None


class AnalysisService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        enqueue: bool = True,
    ) -> None:
        self._session = session
        self._docs = DocumentRepository(session)
        self._pipeline = PipelineRepository(session)
        self._settings = settings or get_settings()
        self._enqueue = enqueue

    async def get_status(
        self,
        *,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> AnalysisSnapshot:
        version = await self._require_version(workspace_id, document_id, version_id)
        run = await self._pipeline.get_latest_run_with_stages(version.id)
        return AnalysisSnapshot(version=version, pipeline_run=run)

    async def request_analysis(
        self,
        *,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> AnalysisSnapshot:
        gateway = get_ai_gateway(self._settings)
        if not gateway.is_enabled():
            raise AIGatewayError(
                AI_DISABLED,
                "AI analysis is disabled (AI_ENABLED=false)",
                status_code=503,
            )

        version = await self._require_version(workspace_id, document_id, version_id)
        existing = await self._pipeline.get_latest_run_with_stages(version.id)

        if version.ai_analysis_status == AiAnalysisStatus.ready:
            logger.info(
                "analysis_idempotent_ready",
                version_id=str(version.id),
            )
            return AnalysisSnapshot(version=version, pipeline_run=existing)

        if version.ai_analysis_status in {
            AiAnalysisStatus.queued,
            AiAnalysisStatus.processing,
        }:
            logger.info(
                "analysis_idempotent_in_flight",
                version_id=str(version.id),
                status=version.ai_analysis_status.value,
            )
            return AnalysisSnapshot(version=version, pipeline_run=existing)

        if existing is not None and existing.status in {
            PipelineStatus.pending,
            PipelineStatus.running,
        }:
            version.ai_analysis_status = (
                AiAnalysisStatus.queued
                if existing.status == PipelineStatus.pending
                else AiAnalysisStatus.processing
            )
            await self._session.commit()
            return AnalysisSnapshot(version=version, pipeline_run=existing)

        run = await self._pipeline.create_run(version.id)
        version.ai_analysis_status = AiAnalysisStatus.queued
        version.analysis_error = None
        await self._session.commit()
        self._enqueue_pipeline(run.id)
        logger.info(
            "analysis_enqueued",
            version_id=str(version.id),
            pipeline_run_id=str(run.id),
        )
        return AnalysisSnapshot(version=version, pipeline_run=run)

    async def _require_version(
        self,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> DocumentVersion:
        version = await self._docs.get_version(workspace_id, document_id, version_id)
        if version is None:
            raise AnalysisServiceError(
                "not_found",
                "Document version not found",
                status_code=404,
            )
        return version

    def _enqueue_pipeline(self, pipeline_run_id: uuid.UUID) -> None:
        if not self._enqueue:
            return
        from app.workers.pipeline import run_pipeline

        run_pipeline.delay(str(pipeline_run_id))

    @staticmethod
    def snapshot_error(version: DocumentVersion) -> str | None:
        if version.ai_analysis_status != AiAnalysisStatus.failed:
            return None
        return version.analysis_error

    @staticmethod
    def mark_queued_timestamp() -> datetime:
        return datetime.now(UTC)
