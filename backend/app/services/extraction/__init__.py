# =============================================================================
# File: __init__.py
# Module/Service: Extraction Service (FR7)
# Layer: Service
# Purpose: Package exports for Information Extraction.
# Responsibilities:
#   - Re-export ExtractionService / ExtractionServiceError
# Dependencies:
#   - extraction_service
# Public Exports:
#   - ExtractionService, ExtractionServiceError
# Database/Table: extractions
# Related Modules: app.api (Part 5)
# Important Notes: entities reuse Graph data by default (0 LLM).
# =============================================================================

from app.services.extraction.extraction_service import (
    ExtractionService,
    ExtractionServiceError,
)

__all__ = ["ExtractionService", "ExtractionServiceError"]
