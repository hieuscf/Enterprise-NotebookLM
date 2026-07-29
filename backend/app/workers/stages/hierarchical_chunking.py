# =============================================================================
# File: hierarchical_chunking.py
# Module/Service: Pipeline Worker — stage_hierarchical_chunking ([AI])
# Layer: Worker
# Purpose: Celery stage entrypoint for v3 Hierarchical Chunking (FR2).
# Responsibilities:
#   - Load document_version + document rows
#   - Delegate chunk planning/persistence to HierarchicalChunkingService
# Dependencies:
#   - app.services.hierarchical_chunking, sync DB session, MinIO adapter
# Public Exports:
#   - stage_hierarchical_chunking
# Database/Table: document_chunks
# Related Modules: app.workers.stages.embedding
# Important Notes: Rule-based only — embedding stage consumes output unchanged.
# =============================================================================

from __future__ import annotations

import traceback
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.adapters.minio_storage import get_minio_storage
from app.core.logging import get_logger
from app.db.sync_session import get_sync_session
from app.models.documents import Document, DocumentVersion
from app.services.hierarchical_chunking import HierarchicalChunkingService
from app.workers.pipeline_errors import DataPipelineError, TransientPipelineError

logger = get_logger(__name__)


def stage_hierarchical_chunking(document_version_id: UUID) -> dict[str, Any]:
    """Chunk cleaned Markdown hierarchically into ``document_chunks``.

    Args:
        document_version_id: Target ``document_versions.id``.

    Returns:
        Metadata for ``pipeline_stage_logs.metadata`` (chunk counts, depth, tokens).

    Raises:
        DataPipelineError: Missing inputs or zero chunks produced (message includes traceback).
        TransientPipelineError: Temporary MinIO failures.
    """
    storage = get_minio_storage()
    service = HierarchicalChunkingService(storage=storage)

    with get_sync_session() as session:
        version, document = _load_version_and_document(session, document_version_id)
        try:
            return service.execute(
                session=session,
                document_version_id=document_version_id,
                version=version,
                document=document,
            )
        except TransientPipelineError:
            logger.exception(
                "Hierarchical chunking transient failure",
                document_version_id=str(document_version_id),
            )
            raise
        except Exception as exc:
            logger.exception(
                "Hierarchical chunking failed",
                document_version_id=str(document_version_id),
            )
            raise DataPipelineError(traceback.format_exc()) from exc


def _load_version_and_document(
    session: Session,
    document_version_id: UUID,
) -> tuple[DocumentVersion, Document]:
    version = session.get(DocumentVersion, document_version_id)
    if version is None:
        raise DataPipelineError(f"document_version not found: {document_version_id}")
    document = session.get(Document, version.document_id)
    if document is None:
        raise DataPipelineError(f"document not found for version: {document_version_id}")
    return version, document
