# =============================================================================
# File: extractor.py
# Module/Service: Document Structure Extraction (FR8 / TASK-CMP-01)
# Layer: Service
# Purpose: Load the FULL ingested document corpus and extract a normalized
#   structure tree for comparison / citation / risk detection.
# Responsibilities:
#   - extract(workspace_id, document_id) → DocumentStructure
#   - Read every document_chunk for the version (never top-k retrieval)
#   - Log extraction metrics without contract body text
# Dependencies:
#   - DocumentRepository, RetrievalRepository.list_chunks_for_document
#   - app.ai.document_structure.pipeline
# Public Exports:
#   - DocumentStructureExtractor, DocumentStructureError
# Database/Table: documents, document_versions, document_chunks (read-only)
# Related Modules: Comparison Service (consumer in TASK-CMP-03+)
# Important Notes:
#   - Idempotent: no persistence, so repeat calls cannot duplicate rows.
#   - Does not call LLM, embedding, or hybrid retrieval.
#   - extract() is unchanged from CMP-01; extract_normalized() adds CMP-02.
#   - Does not map or compare two documents.
# =============================================================================

from __future__ import annotations

import time
import uuid

from app.ai.document_structure.normalization import NormalizedDocumentStructure
from app.ai.document_structure.pipeline import extract_structure
from app.ai.document_structure.types import (
    CorpusChunk,
    DocumentCorpus,
    DocumentStructure,
)
from app.services.document_structure.normalizer import ClauseNormalizer
from app.core.logging import get_logger
from app.models.documents import Document, DocumentVersion
from app.repositories.documents import DocumentRepository
from app.repositories.retrieval import ChunkHydrationRow, RetrievalRepository

logger = get_logger(__name__)


class DocumentStructureError(Exception):
    """Domain error for structure extraction (not an HTTP layer type)."""

    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class DocumentStructureExtractor:
    """Reusable service: full-document structure extraction (0 LLM)."""

    def __init__(
        self,
        *,
        documents: DocumentRepository,
        retrieval: RetrievalRepository,
    ) -> None:
        self._documents = documents
        self._retrieval = retrieval
        self._normalizer = ClauseNormalizer()

    async def extract(
        self,
        document_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        version_id: uuid.UUID | None = None,
    ) -> DocumentStructure:
        """Extract structure from the entire ingested version corpus.

        Args:
            document_id: Target document.
            workspace_id: Tenant scope (required — never cross-workspace).
            version_id: Optional pin; defaults to ``current_version_id``.

        Returns:
            Normalized ``DocumentStructure``. Empty documents yield a DOCUMENT
            node with no sections rather than raising.

        Raises:
            DocumentStructureError: document / version not found in workspace.
        """
        started = time.perf_counter()
        document, version = await self._require_document_version(
            workspace_id=workspace_id,
            document_id=document_id,
            version_id=version_id,
        )
        logger.info(
            "document_structure_extraction_started",
            document_id=str(document.id),
            document_version_id=str(version.id),
            workspace_id=str(workspace_id),
        )

        rows = await self._retrieval.list_chunks_for_document(
            workspace_id,
            document.id,
            version_id=version.id,
        )
        corpus = DocumentCorpus(
            document_id=document.id,
            title=document.title or "",
            chunks=[_to_corpus_chunk(row) for row in rows],
            layout_metadata=version.layout_metadata,
            version_id=version.id,
            workspace_id=workspace_id,
            page_count=version.page_count,
        )
        structure = extract_structure(corpus)
        duration_ms = int((time.perf_counter() - started) * 1000)
        structure.metadata["extraction_duration_ms"] = duration_ms
        logger.info(
            "document_structure_extraction_completed",
            document_id=str(document.id),
            document_version_id=str(version.id),
            pages_processed=structure.metadata.get("pages_processed"),
            chunks_processed=structure.metadata.get("chunks_processed"),
            structural_units_detected=structure.metadata.get("structural_units_detected"),
            articles_detected=structure.metadata.get("articles_detected"),
            clauses_detected=structure.metadata.get("clauses_detected"),
            appendices_detected=structure.metadata.get("appendices_detected"),
            low_confidence_units=structure.metadata.get("low_confidence_units"),
            extraction_duration_ms=duration_ms,
        )
        return structure

    async def extract_normalized(
        self,
        document_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        version_id: uuid.UUID | None = None,
    ) -> NormalizedDocumentStructure:
        """Extract the full corpus, then normalize units. No mapping/comparison."""
        structure = await self.extract(
            document_id,
            workspace_id=workspace_id,
            version_id=version_id,
        )
        return self._normalizer.normalize(structure)

    async def _require_document_version(
        self,
        *,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        version_id: uuid.UUID | None,
    ) -> tuple[Document, DocumentVersion]:
        document = await self._documents.get_document(workspace_id, document_id)
        if document is None:
            raise DocumentStructureError(
                "not_found",
                f"Document {document_id} not found",
                status_code=404,
            )
        target = version_id or document.current_version_id
        if target is None:
            raise DocumentStructureError(
                "no_current_version",
                f"Document {document_id} has no current version",
                status_code=409,
            )
        version = await self._documents.get_version(workspace_id, document_id, target)
        if version is None:
            raise DocumentStructureError(
                "no_current_version",
                f"Version {target} for document {document_id} not found",
                status_code=409,
            )
        return document, version


def _to_corpus_chunk(row: ChunkHydrationRow) -> CorpusChunk:
    layout = row.layout_type.value if row.layout_type is not None else None
    return CorpusChunk(
        chunk_id=row.chunk_id,
        chunk_index=row.chunk_index if row.chunk_index is not None else 0,
        content=row.content or "",
        page_number=row.page_number,
        layout_type=layout,
        heading_path=row.heading_path,
        section=row.section,
        parent_chunk_id=row.parent_chunk_id,
        depth=row.depth,
    )
