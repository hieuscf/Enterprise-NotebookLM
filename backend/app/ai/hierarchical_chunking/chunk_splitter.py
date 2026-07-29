# =============================================================================
# File: chunk_splitter.py
# Module/Service: Pipeline Worker — Hierarchical Chunking ([AI])
# Layer: Service
# Purpose: Split oversized content blocks into token-bounded windows.
# Responsibilities:
#   - Delegate token counting and windowing to app.ai.tokens
# Dependencies:
#   - app.ai.tokens.split_text_by_tokens, count_tokens
# Public Exports:
#   - split_content_block
# Database/Table: N/A
# Related Modules: app.ai.hierarchical_chunking.chunk_planner
# Important Notes: Headings are never split — only body content blocks.
# =============================================================================

from __future__ import annotations

from app.ai.tokens import count_tokens, split_text_by_tokens


def split_content_block(
    text: str,
    *,
    max_tokens: int,
    overlap_ratio: float,
) -> list[str]:
    """Split one block into ordered token windows (single piece when small enough)."""
    cleaned = text.strip()
    if not cleaned:
        return []
    if count_tokens(cleaned) <= max_tokens:
        return [cleaned]
    return split_text_by_tokens(
        cleaned,
        max_tokens=max_tokens,
        overlap_ratio=overlap_ratio,
    )
