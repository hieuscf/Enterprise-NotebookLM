# =============================================================================
# File: __init__.py
# Module/Service: Comparison Service (FR8)
# Layer: Service
# Purpose: Package exports for multi-document comparison.
# Responsibilities:
#   - Expose ComparisonService as the FR8 application entrypoint
# Dependencies:
#   - comparison_service
# Public Exports:
#   - ComparisonService, ComparisonServiceError
# Database/Table: comparisons, comparison_documents
# Related Modules: OpenAPI Comparisons, UC7
# Important Notes: Uses strong model tier (complex query); one LLM call.
# =============================================================================

from app.services.comparison.comparison_service import (
    ComparisonService,
    ComparisonServiceError,
)

__all__ = ["ComparisonService", "ComparisonServiceError"]
