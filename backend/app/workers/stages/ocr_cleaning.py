# =============================================================================
# File: ocr_cleaning.py
# Module/Service: Pipeline Worker — stage_ocr_cleaning ([AI])
# Layer: Worker
# Purpose: Real OCR & Cleaning stage — MinIO in, segments artifact out (FR2 Step 3).
# Responsibilities:
#   - Load version + file_type; download bytes from MinIO
#   - Run multi-format OCR/cleaning; fail on empty text
#   - Persist segments JSON artifact; update document_versions.page_count
# Dependencies:
#   - app.ai.ocr, app.workers.artifacts, MinIO, sync DB session
# Public Exports:
#   - stage_ocr_cleaning
# Database/Table: document_versions (page_count); no segment table
# Related Modules: app.workers.pipeline, app.ai.ocr
# Important Notes: Empty/scanned PDF → DataPipelineError; MinIO blips → Transient.
# =============================================================================

from __future__ import annotations

import json
import time
from typing import Any
from uuid import UUID

from minio.error import S3Error
from sqlalchemy.orm import Session

from app.adapters.minio_storage import MinioStorageAdapter, get_minio_storage
from app.ai.ocr import EmptyOcrError, OcrSegment, run_ocr_cleaning
from app.db.sync_session import get_sync_session
from app.models.documents import Document, DocumentVersion
from app.workers.artifacts import OCR_SEGMENTS_ARTIFACT, save_json_artifact
from app.workers.stages.errors import DataPipelineError, TransientPipelineError


def stage_ocr_cleaning(document_version_id: UUID) -> dict[str, Any]:
    """OCR & Cleaning for one document version.

    Args:
        document_version_id: Target ``document_versions.id``.

    Returns:
        Metadata for ``pipeline_stage_logs.metadata`` (counts, sizes, timing).

    Raises:
        DataPipelineError: Missing rows, corrupt/unreadable file, empty text.
        TransientPipelineError: Temporary MinIO / network failures.
    """
    started = time.perf_counter()
    storage = get_minio_storage()

    with get_sync_session() as session:
        version, document = _load_version_and_document(session, document_version_id)
        storage_path = version.storage_path
        file_type = document.file_type

    raw = _download_bytes(storage, storage_path)
    try:
        result = run_ocr_cleaning(file_type=file_type, data=raw)
    except EmptyOcrError as exc:
        raise DataPipelineError(str(exc)) from exc
    except (ValueError, OSError) as exc:
        raise DataPipelineError(f"OCR failed for {file_type.value}: {exc}") from exc
    except Exception as exc:
        # Parser crashes on corrupt binaries are data errors, not retries.
        raise DataPipelineError(f"OCR parse error ({file_type.value}): {exc}") from exc

    artifact_payload = {
        "document_version_id": str(document_version_id),
        "file_type": file_type.value,
        "page_count": result.page_count,
        "char_count": result.char_count,
        "segment_count": len(result.segments),
        "segments": [_segment_to_dict(s) for s in result.segments],
    }
    try:
        artifact_key = save_json_artifact(
            storage,
            storage_path=storage_path,
            artifact_name=OCR_SEGMENTS_ARTIFACT,
            payload=artifact_payload,
        )
    except S3Error as exc:
        raise TransientPipelineError(f"Failed to store OCR artifact: {exc}") from exc

    # page_count is applied by orchestration from this metadata (single writer).
    duration_ms = int((time.perf_counter() - started) * 1000)
    output_bytes = len(json.dumps(artifact_payload, ensure_ascii=False).encode("utf-8"))
    return {
        "document_version_id": str(document_version_id),
        "file_type": file_type.value,
        "page_count": result.page_count,
        "segment_count": len(result.segments),
        "char_count": result.char_count,
        "output_bytes": output_bytes,
        "artifact_key": artifact_key,
        "duration_ms": duration_ms,
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


def _download_bytes(storage: MinioStorageAdapter, storage_path: str) -> bytes:
    try:
        data = storage.download_bytes(storage_path)
    except S3Error as exc:
        code = getattr(exc, "code", "") or ""
        if code in {"NoSuchKey", "NoSuchBucket", "NotFound"}:
            raise DataPipelineError(
                f"Source file missing in object storage: {storage_path}"
            ) from exc
        raise TransientPipelineError(f"MinIO download failed: {exc}") from exc
    except OSError as exc:
        raise TransientPipelineError(f"MinIO download I/O error: {exc}") from exc

    if not data:
        raise DataPipelineError("Source file in object storage is empty")
    return data


def _segment_to_dict(segment: OcrSegment) -> dict[str, Any]:
    return {
        "text": segment.text,
        "page_number": segment.page_number,
        "section": segment.section,
        "order_index": segment.order_index,
    }
