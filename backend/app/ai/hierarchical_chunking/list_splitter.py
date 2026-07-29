# =============================================================================
# File: list_splitter.py
# Module/Service: Pipeline Worker — Hierarchical Chunking ([AI])
# Layer: Service
# Purpose: Split list blocks on item boundaries only.
# Responsibilities:
#   - Never cut inside a list item; continuation lines stay with their item
# Dependencies:
#   - app.ai.hierarchical_chunking.constants.LIST_ITEM_RE
# Public Exports:
#   - split_list_items
# Database/Table: N/A
# Related Modules: app.ai.hierarchical_chunking.chunk_splitter
# Important Notes: O(n) over lines of one list block.
# =============================================================================

from __future__ import annotations

from app.ai.hierarchical_chunking.constants import LIST_ITEM_RE


def split_list_items(text: str) -> list[str]:
    """Return one string per top-level list item (may span multiple lines)."""
    lines = text.splitlines()
    if not lines:
        return []

    items: list[str] = []
    buffer: list[str] = []

    for line in lines:
        if LIST_ITEM_RE.match(line):
            if buffer:
                items.append("\n".join(buffer).strip())
            buffer = [line]
            continue
        if buffer:
            buffer.append(line)

    if buffer:
        items.append("\n".join(buffer).strip())
    return [item for item in items if item]
