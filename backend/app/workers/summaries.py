# =============================================================================
# File: summaries.py
# Module/Service: Summary Service (FR6) / Pipeline Worker
# Layer: Worker
# Purpose: Celery task that completes async AI Summary generation.
# Responsibilities:
#   - Load processing Summary by id; exit safely if missing / not processing
#   - Delegate generation to SummaryService.process_summary (source_version_id)
#   - Never create a second Summary row
# Dependencies:
#   - Celery, async_session_factory, SummaryService, chat LLM adapter
# Public Exports:
#   - generate_summary (task name), run_summary_generation
# Database/Table: summaries
# Related Modules: app.services.summary.summary_service, Document Ingestion enqueue
# Important Notes:
#   - FR6 exception: worker may call chat LLM (same as graph_extraction exception).
#   - Idempotent: deleted / completed / failed rows are not regenerated.
#   - Uses run_celery_async so asyncpg is not bound to a closed event loop.
# =============================================================================

from __future__ import annotations

import uuid
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import async_session_factory
from app.models.enums import SummaryStatus
from app.repositories.documents import DocumentRepository
from app.repositories.retrieval import RetrievalRepository
from app.repositories.summaries import SummaryRepository
from app.services.summary.summary_service import SummaryService
from app.workers.async_runtime import run_celery_async
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="generate_summary", bind=True, max_retries=0)
def generate_summary(self, summary_id: str) -> dict[str, Any]:
    """Celery entrypoint enqueued by SummaryService.request_summary."""
    del self
    return run_celery_async(run_summary_generation(uuid.UUID(summary_id)))


async def run_summary_generation(summary_id: uuid.UUID) -> dict[str, Any]:
    """Async worker body — one DB session, process then commit."""
    async with async_session_factory() as session:
        service = SummaryService(
            settings=get_settings(),
            session=session,
            documents=DocumentRepository(session),
            retrieval=RetrievalRepository(session),
            summaries=SummaryRepository(session),
            enqueue=False,
        )
        try:
            row = await service.process_summary(summary_id)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("summary_task_failed", summary_id=str(summary_id))
            # Best-effort mark failed in a fresh session (no stack to API).
            async with async_session_factory() as fail_session:
                repo = SummaryRepository(fail_session)
                await repo.mark_failed(summary_id=summary_id)
                await fail_session.commit()
            return {"summary_id": str(summary_id), "status": SummaryStatus.failed.value}

    if row is None:
        return {"summary_id": str(summary_id), "status": "missing"}
    return {"summary_id": str(summary_id), "status": row.status.value}
