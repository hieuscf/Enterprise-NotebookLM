# =============================================================================
# File: __init__.py
# Module/Service: Document Structure Extraction (FR8 / TASK-CMP-01)
# Layer: Service
# Purpose: Package exports for the reusable structure-extraction service.
# Public Exports:
#   - DocumentStructureExtractor, DocumentStructureError
# Database/Table: documents, document_versions, document_chunks (read-only)
# Related Modules: Comparison Service (downstream consumer)
# Important Notes: Not wired into ComparisonService in this task (CMP-01 only).
# =============================================================================

from app.services.document_structure.extractor import (
    DocumentStructureError,
    DocumentStructureExtractor,
)
from app.services.document_structure.normalizer import ClauseNormalizer

__all__ = [
    "ClauseNormalizer",
    "DocumentStructureError",
    "DocumentStructureExtractor",
]
