# =============================================================================
# File: preview_generation.py
# Module/Service: Pipeline Worker — stage_preview_generation
# Layer: Worker
# Purpose: First pipeline stage — build Preview Representation for Viewer.
# Responsibilities:
#   - Delegate to PreviewGeneratorService; return stage metadata
#   - Soft-fail (completed stage + preview_status=failed) so AI stages continue
# Dependencies:
#   - app.services.preview_generator
# Public Exports:
#   - stage_preview_generation
# Database/Table: document_versions.preview_*
# Related Modules: app.workers.pipeline STAGE_ORDER[0]
# Important Notes: Never raises on conversion failure; Transient only for MinIO.
# =============================================================================

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.adapters.minio_storage import get_minio_storage
from app.core.logging import get_logger
from app.services.preview_generator import PreviewGeneratorService

logger = get_logger(__name__)


def stage_preview_generation(document_version_id: UUID) -> dict[str, Any]:
    """Generate document.pdf (or identity PDF) for the Original Document Viewer."""
    storage = get_minio_storage()
    service = PreviewGeneratorService(storage)
    result = service.generate_for_version(document_version_id)
    logger.info(
        "preview_generation_finished",
        document_version_id=str(document_version_id),
        preview_status=result.preview_status.value,
        engine=result.engine,
    )
    return result.as_metadata()
