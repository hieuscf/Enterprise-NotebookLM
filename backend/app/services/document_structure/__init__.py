# =============================================================================
# File: __init__.py
# Module/Service: Document Structure Extraction (FR8 / TASK-CMP-01)
# Layer: Service
# Purpose: Package exports for the reusable structure-extraction service.
# Public Exports:
#   - DocumentStructureExtractor, DocumentStructureError,
#     ContractComparisonOrchestrator, ContractComparisonError
# Database/Table: documents, document_versions, document_chunks (read-only)
# Related Modules: Comparison Service (FR8 similarities path remains separate)
# Important Notes: CMP-16 quality-gates CMP-15 reports; engines stay unchanged.
# =============================================================================

from app.services.document_structure.extractor import (
    DocumentStructureError,
    DocumentStructureExtractor,
)
from app.services.document_structure.differ import ClauseDiffEngine
from app.services.document_structure.exact import ClauseExactDiffEngine
from app.services.document_structure.mapper import ClauseMappingEngine
from app.services.document_structure.normalizer import ClauseNormalizer
from app.services.document_structure.semantic import ClauseSemanticMatcher
from app.services.document_structure.evidence import ClauseEvidenceBinder
from app.services.document_structure.scoring import RiskScoringEngine
from app.services.document_structure.taxonomy import LegalRiskTaxonomyEngine
from app.services.document_structure.verification import ComparisonCitationVerifier
from app.services.document_structure.llm_boundary import ComparisonLLMBoundary
from app.services.document_structure.orchestrator import (
    ContractComparisonError,
    ContractComparisonOrchestrator,
)
from app.services.document_structure.quality import ComparisonQualityEvaluator

__all__ = [
    "ClauseDiffEngine",
    "ClauseExactDiffEngine",
    "ClauseMappingEngine",
    "ClauseNormalizer",
    "ClauseSemanticMatcher",
    "DocumentStructureError",
    "DocumentStructureExtractor",
    "LegalRiskTaxonomyEngine",
    "RiskScoringEngine",
    "ClauseEvidenceBinder",
    "ComparisonCitationVerifier",
    "ComparisonLLMBoundary",
    "ContractComparisonError",
    "ContractComparisonOrchestrator",
    "ComparisonQualityEvaluator",
]
