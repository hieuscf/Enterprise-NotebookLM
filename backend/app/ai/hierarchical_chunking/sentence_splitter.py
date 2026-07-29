# =============================================================================
# File: sentence_splitter.py
# Module/Service: Pipeline Worker — Hierarchical Chunking ([AI])
# Layer: Service
# Purpose: Split paragraph text into sentence units without character windows.
# Responsibilities:
#   - Sentence boundary detection for oversized paragraphs
# Dependencies:
#   - re only
# Public Exports:
#   - split_sentences
# Database/Table: N/A
# Related Modules: app.ai.hierarchical_chunking.chunk_splitter
# Important Notes: O(n) single pass over the paragraph string.
# =============================================================================

from __future__ import annotations

import re

_SENTENCE_BOUNDARY_RE = re.compile(
    r"(?<=[.!?…])\s+(?=[\"'“‘(\[]?[A-ZÀ-Ỹ0-9])",
)


def split_sentences(text: str) -> list[str]:
    """Split one paragraph into sentences; return the whole text when unsplittable."""
    cleaned = text.strip()
    if not cleaned:
        return []
    parts = [part.strip() for part in _SENTENCE_BOUNDARY_RE.split(cleaned) if part.strip()]
    return parts or [cleaned]
