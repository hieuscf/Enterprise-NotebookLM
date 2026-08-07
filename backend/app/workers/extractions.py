# =============================================================================
# File: extractions.py
# Module/Service: Extraction Service (FR7) / Pipeline Worker
# Layer: Worker
# Purpose: Celery task that completes async Information Extraction.
# Responsibilities:
#   - Load processing Extraction by id; exit safely if missing / not processing
#   - Delegate generation to ExtractionService.process_extraction
#   - Never create a second Extraction row
# Dependencies:
#   - Celery, async_session_factory, ExtractionService, chat LLM adapter
# Public Exports:
#   - generate_extraction (task name), run_extraction_generation
# Database/Table: extractions
# Related Modules: app.services.extraction.extraction_service
# Important Notes:
#   - FR7 exception: worker may call chat LLM (same as generate_summary).
#   - entities REUSE path still makes ZERO LLM calls inside process_extraction.
#   - Idempotent: deleted / completed / failed rows are not regenerated.
# =============================================================================

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import async_session_factory
from app.models.enums import ExtractionStatus
from app.repositories.documents import DocumentRepository
from app.repositories.extractions import ExtractionRepository
from app.repositories.retrieval import RetrievalRepository
from app.services.extraction.extraction_service import ExtractionService
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="generate_extraction", bind=True, max_retries=0)
def generate_extraction(self, extraction_id: str) -> dict[str, Any]:
    """Celery entrypoint enqueued by ExtractionService.request_extraction."""
    del self
    return asyncio.run(run_extraction_generation(uuid.UUID(extraction_id)))


async def run_extraction_generation(extraction_id: uuid.UUID) -> dict[str, Any]:
    """Async worker body — one DB session, process then commit."""
    async with async_session_factory() as session:
        service = ExtractionService(
            settings=get_settings(),
            session=session,
            documents=DocumentRepository(session),
            retrieval=RetrievalRepository(session),
            extractions=ExtractionRepository(session),
            enqueue=False,
        )
        try:
            row = await service.process_extraction(extraction_id)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("extraction_task_failed", extraction_id=str(extraction_id))
            async with async_session_factory() as fail_session:
                repo = ExtractionRepository(fail_session)
                await repo.mark_failed(extraction_id=extraction_id)
                await fail_session.commit()
            return {
                "extraction_id": str(extraction_id),
                "status": ExtractionStatus.failed.value,
            }

    if row is None:
        return {"extraction_id": str(extraction_id), "status": "missing"}
    return {"extraction_id": str(extraction_id), "status": row.status.value}
