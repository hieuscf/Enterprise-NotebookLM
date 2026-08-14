# =============================================================================
# File: normalizer.py
# Module/Service: Clause Normalization (FR8 / TASK-CMP-02)
# Layer: Service
# Purpose: Application wrapper around the pure clause-normalization pipeline.
# Responsibilities:
#   - normalize(DocumentStructure) → NormalizedDocumentStructure
#   - Log counts without contract body text
# Dependencies:
#   - app.ai.document_structure.normalization
# Public Exports:
#   - ClauseNormalizer
# Database/Table: N/A (read-only in-memory transform)
# Related Modules: DocumentStructureExtractor; Comparison Service (later tasks)
# Important Notes:
#   - Does not map or compare two documents.
#   - Does not call LLM / retrieval / embedding.
#   - Idempotent: same input tree → same identity keys.
# =============================================================================

from __future__ import annotations

import time

from app.ai.document_structure.normalization import (
    NormalizedDocumentStructure,
    normalize_structure,
)
from app.ai.document_structure.types import DocumentStructure
from app.core.logging import get_logger

logger = get_logger(__name__)


class ClauseNormalizer:
    """Reusable per-document clause normalization (0 LLM)."""

    def normalize(self, structure: DocumentStructure) -> NormalizedDocumentStructure:
        """Canonicalize one extracted structure. Never compares two documents."""
        started = time.perf_counter()
        logger.info(
            "clause_normalization_started",
            document_id=str(structure.document_id),
            document_version_id=(
                str(structure.version_id) if structure.version_id else None
            ),
        )
        result = normalize_structure(structure)
        duration_ms = int((time.perf_counter() - started) * 1000)
        result.metadata["normalization_duration_ms"] = duration_ms
        logger.info(
            "clause_normalization_completed",
            document_id=str(structure.document_id),
            document_version_id=(
                str(structure.version_id) if structure.version_id else None
            ),
            units_normalized=result.metadata.get("units_normalized"),
            articles_normalized=result.metadata.get("articles_normalized"),
            clauses_normalized=result.metadata.get("clauses_normalized"),
            appendices_normalized=result.metadata.get("appendices_normalized"),
            units_without_number=result.metadata.get("units_without_number"),
            normalization_duration_ms=duration_ms,
        )
        return result
