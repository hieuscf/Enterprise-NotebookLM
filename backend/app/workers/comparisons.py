# =============================================================================
# File: comparisons.py
# Module/Service: Comparison Service (FR8) / Pipeline Worker
# Layer: Worker
# Purpose: Celery task that completes async multi-document comparison.
# Responsibilities:
#   - Load processing Comparison by id; exit safely if missing / not processing
#   - Delegate generation to ComparisonService.process_comparison
#   - Never create a second Comparison row
# Dependencies:
#   - Celery, async_session_factory, ComparisonService, chat LLM adapter
# Public Exports:
#   - generate_comparison (task name), run_comparison_generation
# Database/Table: comparisons, comparison_documents
# Related Modules: app.services.comparison.comparison_service
# Important Notes:
#   - FR8 exception: worker may call chat LLM (same as generate_summary/extraction).
#   - Idempotent: deleted / completed / failed rows are not regenerated.
#   - Uses run_celery_async so asyncpg is not bound to a closed event loop.
# =============================================================================

from __future__ import annotations

import uuid
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import async_session_factory
from app.models.enums import ComparisonStatus
from app.repositories.comparisons import ComparisonRepository
from app.repositories.documents import DocumentRepository
from app.repositories.retrieval import RetrievalRepository
from app.repositories.summaries import SummaryRepository
from app.services.comparison.comparison_service import ComparisonService
from app.workers.async_runtime import run_celery_async
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="generate_comparison", bind=True, max_retries=0)
def generate_comparison(self, comparison_id: str) -> dict[str, Any]:
    """Celery entrypoint enqueued by ComparisonService.request_comparison."""
    del self
    return run_celery_async(run_comparison_generation(uuid.UUID(comparison_id)))


async def run_comparison_generation(comparison_id: uuid.UUID) -> dict[str, Any]:
    """Async worker body — one DB session, process then commit."""
    async with async_session_factory() as session:
        service = ComparisonService(
            settings=get_settings(),
            session=session,
            documents=DocumentRepository(session),
            retrieval=RetrievalRepository(session),
            summaries=SummaryRepository(session),
            comparisons=ComparisonRepository(session),
            enqueue=False,
        )
        try:
            outcome = await service.process_comparison(comparison_id)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("comparison_task_failed", comparison_id=str(comparison_id))
            async with async_session_factory() as fail_session:
                repo = ComparisonRepository(fail_session)
                await repo.mark_failed(comparison_id=comparison_id)
                await fail_session.commit()
            return {
                "comparison_id": str(comparison_id),
                "status": ComparisonStatus.failed.value,
            }

    if outcome is None:
        return {"comparison_id": str(comparison_id), "status": "missing"}
    return {
        "comparison_id": str(comparison_id),
        "status": outcome.comparison.status.value,
    }
