# =============================================================================
# File: __init__.py
# Module/Service: Summary Service (FR6)
# Layer: Service
# Purpose: Package exports for AI Summary generation.
# Responsibilities:
#   - Expose SummaryService as the FR6 application entrypoint
# Dependencies:
#   - app.services.summary.summary_service
# Public Exports:
#   - SummaryService, SummaryServiceError, SummaryStyle
# Database/Table: N/A
# Related Modules: app.repositories.summaries, OpenAPI Summaries
# Important Notes: API ``style`` maps to DB ``type`` via SummaryType/SummaryStyle.
# =============================================================================

from app.models.enums import SummaryStyle, SummaryType
from app.services.summary.summary_service import SummaryService, SummaryServiceError

__all__ = [
    "SummaryService",
    "SummaryServiceError",
    "SummaryStyle",
    "SummaryType",
]
