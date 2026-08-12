# =============================================================================
# File: document_understanding.py
# Module/Service: Pipeline Worker — stage_document_understanding ([AI])
# Layer: Worker
# Purpose: Celery stage entrypoint for v3 Document Understanding (FR2, UC2).
# Responsibilities:
#   - Load and validate document_version + document rows
#   - Delegate parsing, layout and artifact persistence to DocumentUnderstandingService
#   - Persist parser / markdown_storage_path / layout_metadata in one DB transaction
#   - Roll back MinIO artifacts when the DB transaction fails
# Dependencies:
#   - app.services.document_understanding, app.adapters.minio_storage, sync DB session
# Public Exports:
#   - stage_document_understanding, PARSER_LLAMAPARSE, PARSER_LOCAL_OCR
# Database/Table: document_versions (parser, markdown_storage_path, layout_metadata)
# Related Modules: app.services.document_understanding
# Important Notes:
#   - Business logic lives in DocumentUnderstandingService — this module is orchestration only.
#   - Parser selection is explicit via Settings.document_parser (see config.py).
#   - LlamaParse client poll-timeout may fall back to local OCR when
#     LLAMAPARSE_FALLBACK_TO_LOCAL_OCR=true (auth/quota/unsupported never fall back).
#   - Expunge version/document before session commit; expire_on_commit would otherwise
#     detach them and cause DetachedInstanceError during long-running parse I/O.
# =============================================================================

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.adapters.minio_storage import get_minio_storage
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.sync_session import get_sync_session
from app.models.documents import Document, DocumentVersion
from app.services.document_understanding import (
    PARSER_LLAMAPARSE,
    PARSER_LOCAL_OCR,
    DocumentUnderstandingResult,
    build_document_understanding_service,
)
from app.workers.pipeline_errors import DataPipelineError

logger = get_logger(__name__)

__all__ = [
    "PARSER_LLAMAPARSE",
    "PARSER_LOCAL_OCR",
    "stage_document_understanding",
]


def stage_document_understanding(document_version_id: UUID) -> dict[str, Any]:
    """Parse one document version into Markdown + Layout Analysis.

    Args:
        document_version_id: Target ``document_versions.id``.

    Returns:
        Metadata for ``pipeline_stage_logs.metadata``: Metadata Extraction counts
        (headings per level, tables, figures, words), page_count, artifact keys
        and parser timings.

    Raises:
        DataPipelineError: Missing rows, validation, parse, or configuration failures.
        TransientPipelineError: Temporary MinIO read/write failures only.
    """
    settings = get_settings()
    storage = get_minio_storage()
    service = build_document_understanding_service(storage=storage, settings=settings)

    with get_sync_session() as session:
        version, document = _load_version_and_document(session, document_version_id)
        # Expunge before commit so attrs stay readable after the session closes.
        # Otherwise expire_on_commit triggers DetachedInstanceError in execute().
        session.expunge(document)
        session.expunge(version)

    result: DocumentUnderstandingResult | None = None
    try:
        result = service.execute(
            document_version_id=document_version_id,
            version=version,
            document=document,
        )
        _persist_version_fields(document_version_id, result)
    except Exception:
        logger.exception(
            "Document understanding failed",
            document_version_id=str(document_version_id),
        )
        if result is not None and result.artifact_keys:
            service.rollback_artifacts(result.artifact_keys)
        raise

    logger.info(
        "Document understanding stage completed",
        document_version_id=str(document_version_id),
        parser=result.parser,
    )
    return result.stage_metadata


def _persist_version_fields(
    document_version_id: UUID,
    result: DocumentUnderstandingResult,
) -> None:
    """Update document_versions inside a single committed transaction."""
    logger.info("Update database", document_version_id=str(document_version_id))
    with get_sync_session() as session:
        version = session.get(DocumentVersion, document_version_id)
        if version is None:
            raise DataPipelineError(f"document_version disappeared: {document_version_id}")
        version.parser = result.parser
        version.markdown_storage_path = result.markdown_storage_path
        version.layout_metadata = result.layout_metadata


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
