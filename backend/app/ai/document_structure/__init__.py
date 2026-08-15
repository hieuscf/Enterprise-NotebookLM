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
from app.ai.document_structure.exact_config import ExactDiffConfig
from app.ai.document_structure.exact_engine import extract_exact_differences
from app.ai.document_structure.exact_types import (
    ExactChange,
    ExactDiffResult,
    ValueChangeType,
    ValueDirection,
    ValueType,
)
from app.ai.document_structure.evidence_engine import bind_evidence
from app.ai.document_structure.evidence_types import (
    BindingStatus,
    EvidenceBindingResult,
    EvidenceRef,
    FindingEvidence,
)
from app.ai.document_structure.verification_engine import (
    catalog_from_structures,
    inventory_from_structures,
    verify_bindings,
)
from app.ai.document_structure.verification_types import (
    AbsenceStatus,
    ComparisonVerificationResult,
    FindingVerification,
    VerificationReasonCode,
    VerificationStatus,
)
from app.ai.document_structure.scoring_config import RiskScoreConfig
from app.ai.document_structure.scoring_engine import (
    apply_adjustments,
    level_from_score,
    score_taxonomy,
)
from app.ai.document_structure.scoring_types import (
    RiskImpact,
    RiskLevel,
    RiskScoreResult,
    RiskScoringResult,
)
from app.ai.document_structure.taxonomy_config import TaxonomyConfig
from app.ai.document_structure.taxonomy_engine import classify_taxonomy
from app.ai.document_structure.taxonomy_types import (
    ClassificationConfidence,
    RiskCategory,
    TaxonomyAssignment,
    TaxonomyResult,
)
from app.ai.document_structure.semantic_config import SemanticMatchConfig
from app.ai.document_structure.semantic_engine import (
    refine_mapping_semantically,
    combined_semantic_score,
    types_compatible,
)
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
    "ExactChange",
    "ExactDiffConfig",
    "ExactDiffResult",
    "DocumentCorpus",
    "DocumentStructure",
    "ExtractionConfidence",
    "ClauseMapping",
    "MappingConfig",
    "MappingResult",
    "MappingStatus",
    "MappingType",
    "SemanticMatchConfig",
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
    "extract_exact_differences",
    "extract_from_pages",
    "extract_from_text",
    "extract_structure",
    "identity_key_for",
    "map_normalized_structures",
    "mappable_units",
    "normalize_structure",
    "normalize_title",
    "refine_mapping_semantically",
    "score_pair",
    "types_compatible",
    "combined_semantic_score",
    "ValueChangeType",
    "ValueDirection",
    "ValueType",
    "TaxonomyConfig",
    "TaxonomyAssignment",
    "TaxonomyResult",
    "RiskCategory",
    "ClassificationConfidence",
    "classify_taxonomy",
    "RiskScoreConfig",
    "RiskScoreResult",
    "RiskScoringResult",
    "RiskLevel",
    "RiskImpact",
    "level_from_score",
    "score_taxonomy",
    "apply_adjustments",
    "bind_evidence",
    "BindingStatus",
    "EvidenceBindingResult",
    "EvidenceRef",
    "FindingEvidence",
    "verify_bindings",
    "catalog_from_structures",
    "inventory_from_structures",
    "VerificationStatus",
    "AbsenceStatus",
    "VerificationReasonCode",
    "FindingVerification",
    "ComparisonVerificationResult",
]
