# =============================================================================
# File: reports.py
# Module/Service: Report Service (FR9) / Pipeline Worker
# Layer: Worker
# Purpose: Celery task that completes async report generation.
# Responsibilities:
#   - Load pending Report by id; exit safely if missing / not pending
#   - Delegate generation to ReportService.process_report
#   - Never create a second Report row
# Dependencies:
#   - Celery, async_session_factory, ReportService, MinIO, aggregation, renderers
# Public Exports:
#   - generate_report (task name), run_report_generation
# Database/Table: reports, report_items
# Related Modules: app.services.report_service
# Important Notes:
#   - Idempotent: deleted / ready / failed rows are not regenerated.
#   - Uses run_celery_async so asyncpg is not bound to a closed event loop.
#   - Schema v1 has no reports.error — failures log + status=failed only.
# =============================================================================

from __future__ import annotations

import uuid
from typing import Any

from app.adapters.minio_storage import get_minio_storage
from app.core.logging import get_logger
from app.db.session import async_session_factory
from app.models.enums import ReportStatus
from app.repositories.chat_messages import ChatMessageRepository
from app.repositories.chat_sessions import ChatSessionRepository
from app.repositories.comparisons import ComparisonRepository
from app.repositories.documents import DocumentRepository
from app.repositories.extractions import ExtractionRepository
from app.repositories.reports import ReportRepository
from app.repositories.summaries import SummaryRepository
from app.services.report_aggregation import ReportAggregationService
from app.services.report_service import ReportService
from app.workers.async_runtime import run_celery_async
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="generate_report", bind=True, max_retries=0)
def generate_report(self, report_id: str) -> dict[str, Any]:
    """Celery entrypoint enqueued by ReportService.request_report."""
    del self
    return run_celery_async(run_report_generation(uuid.UUID(report_id)))


async def run_report_generation(report_id: uuid.UUID) -> dict[str, Any]:
    """Async worker body — one DB session, process then commit."""
    async with async_session_factory() as session:
        reports = ReportRepository(session)
        aggregation = ReportAggregationService(
            summaries=SummaryRepository(session),
            extractions=ExtractionRepository(session),
            comparisons=ComparisonRepository(session),
            chat_sessions=ChatSessionRepository(session),
            chat_messages=ChatMessageRepository(session),
            documents=DocumentRepository(session),
        )
        service = ReportService(
            session=session,
            reports=reports,
            aggregation=aggregation,
            storage=get_minio_storage(),
            enqueue=False,
        )
        try:
            outcome = await service.process_report(report_id)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("report_task_failed", report_id=str(report_id))
            async with async_session_factory() as fail_session:
                repo = ReportRepository(fail_session)
                await repo.mark_failed(report_id=report_id)
                await fail_session.commit()
            return {
                "report_id": str(report_id),
                "status": ReportStatus.failed.value,
            }

    if outcome is None:
        return {"report_id": str(report_id), "status": "missing"}
    return {
        "report_id": str(report_id),
        "status": outcome.status.value,
    }
