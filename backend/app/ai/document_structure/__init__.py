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

from app.ai.document_structure.diff_config import DiffConfig
from app.ai.document_structure.diff_engine import (
    classify_pair,
    diff_mapping_result,
    diff_normalized_structures,
)
from app.ai.document_structure.diff_types import (
    ChangeType,
    ClauseDiff,
    DiffClassification,
    DiffResult,
    DiffVerificationStatus,
)
from app.ai.document_structure.mapping_config import MappingConfig
from app.ai.document_structure.mapping_engine import (
    map_normalized_structures,
    mappable_units,
    score_pair,
)
from app.ai.document_structure.mapping_types import (
    ClauseMapping,
    MappingResult,
    MappingStatus,
    MappingType,
)
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
    "ChangeType",
    "ClauseDiff",
    "CorpusChunk",
    "DiffClassification",
    "DiffConfig",
    "DiffResult",
    "DiffVerificationStatus",
    "DocumentCorpus",
    "DocumentStructure",
    "ExtractionConfidence",
    "ClauseMapping",
    "MappingConfig",
    "MappingResult",
    "MappingStatus",
    "MappingType",
    "NormalizedDocumentStructure",
    "NormalizedUnit",
    "SourceSpan",
    "StructuralUnit",
    "StructuralUnitType",
    "added_canonical_keys",
    "build_aliases",
    "canonical_key",
    "classify_pair",
    "diff_mapping_result",
    "diff_normalized_structures",
    "extract_from_pages",
    "extract_from_text",
    "extract_structure",
    "identity_key_for",
    "map_normalized_structures",
    "mappable_units",
    "normalize_structure",
    "normalize_title",
    "score_pair",
]
