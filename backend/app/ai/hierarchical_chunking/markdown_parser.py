# =============================================================================
# File: markdown_parser.py
# Module/Service: Pipeline Worker — Hierarchical Chunking ([AI])
# Layer: Service
# Purpose: Split Markdown source into numbered lines for downstream parsers.
# Responsibilities:
#   - Normalize newlines; emit 1-based line numbers
# Dependencies:
#   - app.ai.hierarchical_chunking.types
# Public Exports:
#   - parse_markdown_lines
# Database/Table: N/A
# Related Modules: app.ai.hierarchical_chunking.heading_tree_builder
# Important Notes: Pure function — no heading or block inference here.
# =============================================================================

from __future__ import annotations

from app.ai.hierarchical_chunking.types import MarkdownLine


def parse_markdown_lines(markdown: str) -> list[MarkdownLine]:
    """Return logical lines with stable 1-based line numbers."""
    normalized = markdown.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.strip():
        return []
    return [
        MarkdownLine(number=index + 1, text=line)
        for index, line in enumerate(normalized.split("\n"))
    ]
