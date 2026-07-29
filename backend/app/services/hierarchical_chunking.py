# =============================================================================
# File: hierarchical_chunking.py
# Module/Service: Document Ingestion Service — Hierarchical Chunking
# Layer: Service
# Purpose: Business logic for v3 Hierarchical Chunking (FR2).
# Responsibilities:
#   - Load cleaned Markdown + layout_metadata
#   - Plan hierarchical chunks and persist document_chunks rows
# Dependencies:
#   - app.ai.hierarchical_chunking, app.repositories.knowledge, MinIO adapter
# Public Exports:
#   - HierarchicalChunkingService
# Database/Table: document_chunks
# Related Modules: app.workers.stages.hierarchical_chunking
# Important Notes: Rule-based only — no LLM, embedding, or graph extraction.
# =============================================================================

from __future__ import annotations

from typing import Any
from uuid import UUID

from minio.error import S3Error
from sqlalchemy.orm import Session

from app.adapters.minio_storage import MinioStorageAdapter
from app.ai.hierarchical_chunking.parent_resolver import resolve_parent_chunk_id
from app.ai.hierarchical_chunking.pipeline import run_hierarchical_chunking
from app.ai.hierarchical_chunking.types import ChunkingInput
from app.core.config import Settings
from app.core.logging import get_logger
from app.models.documents import Document, DocumentVersion
from app.repositories.knowledge import KnowledgeSyncRepository
from app.workers.pipeline_errors import DataPipelineError, TransientPipelineError

logger = get_logger(__name__)


class HierarchicalChunkingService:
    """Plan and persist hierarchical chunks for one document version."""

    def __init__(self, *, storage: MinioStorageAdapter, settings: Settings) -> None:
        self._storage = storage
        self._settings = settings

    def execute(
        self,
        *,
        session: Session,
        document_version_id: UUID,
        version: DocumentVersion,
        document: Document,
    ) -> dict[str, Any]:
        """Run hierarchical chunking and insert ``document_chunks`` rows."""
        markdown_key = version.markdown_storage_path
        if not markdown_key or not markdown_key.strip():
            raise DataPipelineError(
                f"markdown_storage_path missing for version {document_version_id} — "
                "run document_understanding and cleaning_normalize first"
            )

        logger.info(
            "Start hierarchical chunking",
            document_version_id=str(document_version_id),
            markdown_storage_path=markdown_key,
        )

        markdown = self._download_markdown(markdown_key)
        plan = run_hierarchical_chunking(
            ChunkingInput(
                markdown=markdown,
                layout_metadata=version.layout_metadata,
                file_type=document.file_type,
            ),
            max_tokens=self._settings.chunk_max_tokens,
            overlap_ratio=self._settings.chunk_overlap_ratio,
        )
        if not plan.planned_chunks:
            raise DataPipelineError("Hierarchical chunking produced zero chunks")

        knowledge = KnowledgeSyncRepository(session)
        knowledge.clear_version_artifacts(document_version_id)

        temp_to_db: dict[str, UUID] = {}
        for planned in plan.planned_chunks:
            parent_id = resolve_parent_chunk_id(planned, temp_to_db)
            chunk = knowledge.create_chunk(
                document_version_id=document_version_id,
                chunk_index=planned.chunk_index,
                content=planned.content,
                page_number=planned.page_number,
                section_index=planned.section_index,
                section=planned.section,
                token_count=planned.token_count,
                parent_chunk_id=parent_id,
                heading_path=planned.heading_path,
                depth=planned.depth,
                layout_type=planned.layout_type,
            )
            temp_to_db[planned.temp_id] = chunk.id

        logger.info(
            "Hierarchical chunking completed",
            document_version_id=str(document_version_id),
            chunk_count=plan.metrics.chunk_count,
            heading_chunk_count=plan.metrics.heading_chunk_count,
        )

        return {
            "document_version_id": str(document_version_id),
            **plan.metrics.as_dict(),
        }

    def _download_markdown(self, object_key: str) -> str:
        try:
            raw = self._storage.download_bytes(object_key)
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
