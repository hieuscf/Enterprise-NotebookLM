# =============================================================================
# File: previews.py
# Module/Service: Preview Generator (Document Ingestion)
# Layer: Worker
# Purpose: Standalone Celery task to (re)generate Preview Representation.
# Responsibilities:
#   - generate_preview: run Preview Generator for one document_version
#   - backfill_previews: enqueue preview generation for versions still pending
# Dependencies:
#   - app.services.preview_generator, Celery
# Public Exports:
#   - generate_preview, backfill_previews
# Database/Table: document_versions (preview_*)
# Related Modules: app.workers.stages.preview_generation
# Important Notes: Used for documents ingested before Preview Generation existed;
#   does not re-run any AI stage.
# =============================================================================

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.adapters.minio_storage import get_minio_storage
from app.core.logging import get_logger
from app.db.sync_session import get_sync_session
from app.models.documents import DocumentVersion
from app.models.enums import PreviewStatus
from app.services.preview_generator import PreviewGeneratorService
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="generate_preview")
def generate_preview(document_version_id: str) -> dict[str, Any]:
    """Generate the Preview Representation for a single document version."""
    service = PreviewGeneratorService(get_minio_storage())
    result = service.generate_for_version(UUID(document_version_id))
    return result.as_metadata()


@celery_app.task(name="backfill_previews")
def backfill_previews(limit: int = 200) -> dict[str, Any]:
    """Enqueue preview generation for versions without a completed preview."""
    with get_sync_session() as session:
        stmt = (
            select(DocumentVersion.id)
            .where(DocumentVersion.preview_status != PreviewStatus.completed)
            .limit(limit)
        )
        version_ids = [str(row) for row in session.execute(stmt).scalars().all()]

    for version_id in version_ids:
        generate_preview.delay(version_id)

    logger.info("preview_backfill_enqueued", count=len(version_ids))
    return {"enqueued": len(version_ids), "document_version_ids": version_ids}
