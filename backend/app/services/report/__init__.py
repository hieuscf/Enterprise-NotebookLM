# =============================================================================
# File: __init__.py
# Module/Service: Report Service (FR9 / TASK-CMP-24)
# Layer: Service
# Purpose: Package for report-domain builders used by FR9 aggregation/render.
# Responsibilities:
#   - Re-export comparison report builder
# Dependencies:
#   - comparison_report_builder
# Public Exports:
#   - build_comparison_report_content
# Database/Table: N/A
# Related Modules: report_aggregation, renderers
# Important Notes: Builders render stored knowledge; they do not compare.
# =============================================================================

from app.services.report.comparison_report_builder import build_comparison_report_content

__all__ = ["build_comparison_report_content"]
