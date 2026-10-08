# =============================================================================
# File: __init__.py
# Module/Service: Document Analysis Service
# Layer: Service
# Purpose: Export on-demand analysis application service.
# Public Exports:
#   - AnalysisService, AnalysisServiceError
# =============================================================================

from app.services.analysis.analysis_service import AnalysisService, AnalysisServiceError

__all__ = ["AnalysisService", "AnalysisServiceError"]
