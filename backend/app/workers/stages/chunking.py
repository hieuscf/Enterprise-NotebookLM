# =============================================================================
# File: chunking.py
# Module/Service: Pipeline Worker — stage_chunking ([AI])
# Layer: Worker
# Purpose: Structure-aware chunking from OCR segments → document_chunks (FR2 Step 4).
# Responsibilities:
#   - Load OCR artifact; chunk by section then token windows with overlap
#   - Persist document_chunks (page_number, section, token_count)
# Dependencies:
#   - app.ai.chunking, app.workers.artifacts, MinIO, KnowledgeSyncRepository
# Public Exports:
#   - stage_chunking
# Database/Table: document_chunks
# Related Modules: app.workers.pipeline, app.ai.chunking, app.ai.tokens
# Important Notes: Requires OCR artifact from Step 3; clears prior version chunks.
# =============================================================================

from __future__ import annotations

from typing import Any
from uuid import UUID

from minio.error import S3Error

from app.adapters.minio_storage import get_minio_storage
from app.ai.chunking import run_chunking_from_segments
from app.ai.tokens import get_token_encoding_name
from app.core.config import get_settings
from app.db.sync_session import get_sync_session
from app.models.documents import DocumentVersion
from app.repositories.knowledge import KnowledgeSyncRepository
from app.workers.artifacts import OCR_SEGMENTS_ARTIFACT, load_json_artifact
from app.workers.stages.errors import DataPipelineError, TransientPipelineError


def stage_chunking(document_version_id: UUID) -> dict[str, Any]:
    """Chunk OCR segments and insert ``document_chunks`` rows.

    Args:
        document_version_id: Target version id.

    Returns:
        Metadata: chunk_count, avg_chars, tokenizer, max_tokens, overlap_ratio.
    """
    settings = get_settings()
    storage = get_minio_storage()

    with get_sync_session() as session:
        version = session.get(DocumentVersion, document_version_id)
        if version is None:
            raise DataPipelineError(f"document_version not found: {document_version_id}")

        try:
            artifact = load_json_artifact(
                storage,
                storage_path=version.storage_path,
                artifact_name=OCR_SEGMENTS_ARTIFACT,
            )
        except S3Error as exc:
            code = getattr(exc, "code", "") or ""
            if code in {"NoSuchKey", "NoSuchBucket", "NotFound"}:
                raise DataPipelineError(
                    "OCR segments artifact missing — run ocr_cleaning before chunking"
                ) from exc
            raise TransientPipelineError(f"Failed to load OCR artifact: {exc}") from exc
        except (OSError, ValueError) as exc:
            raise DataPipelineError(f"Invalid OCR artifact: {exc}") from exc

        segments = artifact.get("segments") or []
        if not isinstance(segments, list) or not segments:
            raise DataPipelineError("OCR artifact has no segments to chunk")

        text_chunks = run_chunking_from_segments(
            segments,
            max_tokens=settings.chunk_max_tokens,
            overlap_ratio=settings.chunk_overlap_ratio,
        )
        if not text_chunks:
            raise DataPipelineError("Chunking produced zero chunks from OCR segments")

        knowledge = KnowledgeSyncRepository(session)
        knowledge.clear_version_artifacts(document_version_id)

        for tc in text_chunks:
            knowledge.create_chunk(
                document_version_id=document_version_id,
                chunk_index=tc.chunk_index,
                content=tc.content,
                page_number=tc.page_number,
                section=tc.section,
                token_count=tc.token_count,
            )

        total_chars = sum(len(c.content) for c in text_chunks)
        avg_chars = total_chars / len(text_chunks)
        return {
            "document_version_id": str(document_version_id),
            "chunk_count": len(text_chunks),
            "avg_chars": round(avg_chars, 2),
            "avg_tokens": round(
                sum(c.token_count for c in text_chunks) / len(text_chunks),
                2,
            ),
            "max_tokens": settings.chunk_max_tokens,
            "overlap_ratio": settings.chunk_overlap_ratio,
            "tokenizer": get_token_encoding_name(),
        }
