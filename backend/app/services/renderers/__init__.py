# =============================================================================
# File: __init__.py
# Module/Service: Report Service (FR9) — Renderers
# Layer: Service
# Purpose: Package exports for Markdown / DOCX report renderers.
# Responsibilities:
#   - Re-export public render entrypoints and result types
# Dependencies:
#   - markdown_renderer, docx_renderer
# Public Exports:
#   - render_markdown, MarkdownRenderResult, render_docx, DocxRenderResult
# Database/Table: N/A
# Related Modules: report_aggregation.AggregatedReportBlock
# Important Notes: Renderers do not mutate AggregatedReportBlock input schema.
# =============================================================================

from app.services.renderers.docx_renderer import DocxRenderResult, render_docx
from app.services.renderers.markdown_renderer import MarkdownRenderResult, render_markdown

__all__ = [
    "DocxRenderResult",
    "MarkdownRenderResult",
    "render_docx",
    "render_markdown",
]
