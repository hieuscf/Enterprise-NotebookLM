# =============================================================================
# File: __init__.py
# Module/Service: Document Structure Extraction (FR8 / TASK-CMP-01)
# Layer: Service
# Purpose: Public exports for the deterministic document-structure pipeline.
# Public Exports:
#   - extract_structure, extract_from_text, extract_from_pages,
#     added_canonical_keys, DocumentStructure, StructuralUnit, ...
# Important Notes: Pure functions — no DB, no LLM, no retrieval.
# =============================================================================

from app.ai.document_structure.normalization import (
    NormalizedDocumentStructure,
    NormalizedUnit,
    build_aliases,
    identity_key_for,
    normalize_structure,
    normalize_title,
)
from app.ai.document_structure.pipeline import (
    added_canonical_keys,
    extract_from_pages,
    extract_from_text,
    extract_structure,
)
from app.ai.document_structure.types import (
    CorpusChunk,
    DocumentCorpus,
    DocumentStructure,
    ExtractionConfidence,
    SourceSpan,
    StructuralUnit,
    StructuralUnitType,
    canonical_key,
)

__all__ = [
    "CorpusChunk",
    "DocumentCorpus",
    "DocumentStructure",
    "ExtractionConfidence",
    "NormalizedDocumentStructure",
    "NormalizedUnit",
    "SourceSpan",
    "StructuralUnit",
    "StructuralUnitType",
    "added_canonical_keys",
    "build_aliases",
    "canonical_key",
    "extract_from_pages",
    "extract_from_text",
    "extract_structure",
    "identity_key_for",
    "normalize_structure",
    "normalize_title",
]
