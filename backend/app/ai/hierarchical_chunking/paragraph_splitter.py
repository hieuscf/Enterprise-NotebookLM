# =============================================================================
# File: paragraph_splitter.py
# Module/Service: Pipeline Worker — Hierarchical Chunking ([AI])
# Layer: Service
# Purpose: Split text into paragraph units (blank-line boundaries).
# Responsibilities:
#   - Paragraph detection for paragraph-type blocks
# Dependencies:
#   - re only
# Public Exports:
#   - split_paragraphs
# Database/Table: N/A
# Related Modules: app.ai.hierarchical_chunking.chunk_splitter
# Important Notes: O(n) — does not copy the full document, only paragraph strings.
# =============================================================================

from __future__ import annotations

import re

_PARAGRAPH_BREAK_RE = re.compile(r"\n\s*\n+")


def split_paragraphs(text: str) -> list[str]:
    """Split on blank lines; single paragraph returns a one-element list."""
    cleaned = text.strip()
    if not cleaned:
        return []
    parts = [part.strip() for part in _PARAGRAPH_BREAK_RE.split(cleaned) if part.strip()]
    return parts or [cleaned]
