# =============================================================================
# File: cleaning_normalize.py
# Module/Service: Pipeline Worker — stage_cleaning_normalize ([AI])
# Layer: Worker
# Purpose: Celery stage for rule-based Markdown cleaning after Document Understanding
#   and before Hierarchical Chunking (FR2 v3).
# Responsibilities:
#   - Load Markdown from document_versions.markdown_storage_path
#   - Apply pure-function cleaners; overwrite the same MinIO object in place
#   - Return before/after character and line-removal stats for pipeline_stage_logs
# Dependencies:
#   - app.ai.markdown_cleaning, app.adapters.minio_storage, sync DB session
# Public Exports:
#   - stage_cleaning_normalize
# Database/Table: document_versions.markdown_storage_path
# Related Modules: app.workers.stages.document_understanding, hierarchical_chunking
# Important Notes:
#   - Overwrites document.md in place so markdown_storage_path stays stable for
#     downstream stages; raw parse text remains recoverable from layout artifact.
#   - No LLM calls; headings (# …) must survive cleaning intact.
# =============================================================================

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

from minio.error import S3Error

from sqlalchemy.orm import Session

from app.adapters.minio_storage import MinioStorageAdapter, get_minio_storage
from app.ai.markdown_cleaning import clean_markdown
from app.core.logging import get_logger
from app.db.sync_session import get_sync_session
from app.models.documents import Document, DocumentVersion
from app.workers.pipeline_errors import DataPipelineError, TransientPipelineError

logger = get_logger(__name__)


def stage_cleaning_normalize(document_version_id: UUID) -> dict[str, Any]:
    """Clean and normalize Markdown produced by Document Understanding.

    Args:
        document_version_id: Target ``document_versions.id``.

    Returns:
        Metadata for ``pipeline_stage_logs.metadata``: chars/lines before & after,
        lines removed, markdown path.

    Raises:
        DataPipelineError: Missing version, markdown path, or empty markdown.
        TransientPipelineError: Temporary MinIO read/write failures.
    """
    started = time.perf_counter()
    storage = get_minio_storage()

    with get_sync_session() as session:
        version, document = _load_version_and_document(session, document_version_id)
        markdown_key = version.markdown_storage_path
        if not markdown_key or not markdown_key.strip():
            raise DataPipelineError(
                f"markdown_storage_path missing for version {document_version_id} — "
                "run document_understanding first"
            )
        file_type = document.file_type
        parser = version.parser or "unknown"

    logger.info(
        "Start cleaning normalize",
        document_version_id=str(document_version_id),
        markdown_storage_path=markdown_key,
    )

    raw_markdown = _download_markdown(storage, markdown_key)
    cleaned_markdown, stats = clean_markdown(raw_markdown)

    if not cleaned_markdown.strip():
        raise DataPipelineError(
            "Cleaning removed all Markdown content — refusing to overwrite durable output"
        )

    _upload_markdown(storage, markdown_key, cleaned_markdown)

    logger.info(
        "Cleaning normalize completed",
        document_version_id=str(document_version_id),
        lines_removed=stats.lines_removed,
        chars_before=stats.chars_before,
        chars_after=stats.chars_after,
    )

    return {
        "document_version_id": str(document_version_id),
        "markdown_storage_path": markdown_key,
        "file_type": file_type.value,
        "parser": parser,
        **stats.as_dict(),
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }


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


def _download_markdown(storage: MinioStorageAdapter, object_key: str) -> str:
    try:
        raw = storage.download_bytes(object_key)
    except S3Error as exc:
        code = getattr(exc, "code", "") or ""
        if code in {"NoSuchKey", "NoSuchBucket", "NotFound"}:
            raise DataPipelineError(
                f"Markdown object missing in object storage: {object_key}"
            ) from exc
        raise TransientPipelineError(f"MinIO download failed: {exc}") from exc
    except OSError as exc:
        raise TransientPipelineError(f"MinIO download I/O error: {exc}") from exc

    if not raw:
        raise DataPipelineError(f"Markdown object is empty: {object_key}")

    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DataPipelineError(f"Markdown is not valid UTF-8: {object_key}") from exc


def _upload_markdown(storage: MinioStorageAdapter, object_key: str, text: str) -> None:
    try:
        storage.upload_bytes(
            object_key=object_key,
            data=text.encode("utf-8"),
            content_type="text/markdown; charset=utf-8",
        )
    except S3Error as exc:
        raise TransientPipelineError(f"Failed to store cleaned Markdown: {exc}") from exc
    except OSError as exc:
        raise TransientPipelineError(f"MinIO upload I/O error: {exc}") from exc
