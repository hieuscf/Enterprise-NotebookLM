# =============================================================================
# File: __init__.py
# Module/Service: Search Service / Hybrid Retrieval
# Layer: Service
# Purpose: Package exports for the shared Hybrid Retrieval layer (FR3).
# Responsibilities:
#   - Expose HybridRetrievalService as the sole retrieval entrypoint
# Dependencies:
#   - app.services.retrieval.hybrid_retrieval_service
# Public Exports:
#   - HybridRetrievalService, RetrievalCandidate, RetrievalResult,
#     RetrievalUnavailableError, MetadataSearch, Reranker,
#     compute_confidence / ConfidenceConfig / ConfidenceResult
# Database/Table: N/A
# Related Modules: Search API, Query Router, Chat Service, Citation Service
# Important Notes: 0 LLM calls. Do not duplicate retrieval logic outside this package.
# =============================================================================

from app.services.retrieval.confidence_engine import (
    ConfidenceConfig,
    ConfidenceResult,
    RerankedItem,
    build_confidence_config,
    compute_confidence,
    should_compute_confidence,
)
from app.services.retrieval.exceptions import RetrievalUnavailableError
from app.services.retrieval.hybrid_retrieval_service import HybridRetrievalService
from app.services.retrieval.metadata_search import MetadataSearch
from app.services.retrieval.reranker import Reranker
from app.services.retrieval.schemas import RetrievalCandidate, RetrievalResult

__all__ = [
    "ConfidenceConfig",
    "ConfidenceResult",
    "HybridRetrievalService",
    "MetadataSearch",
    "RerankedItem",
    "Reranker",
    "RetrievalCandidate",
    "RetrievalResult",
    "RetrievalUnavailableError",
    "build_confidence_config",
    "compute_confidence",
    "should_compute_confidence",
]
