# =============================================================================
# File: unit_packer.py
# Module/Service: Pipeline Worker — Hierarchical Chunking ([AI])
# Layer: Service
# Purpose: Greedy token-bounded packing of structural units (paragraphs/items).
# Responsibilities:
#   - Target 500–800 tokens, hard cap 1000, overlap 50–100 when forced to split
# Dependencies:
#   - app.ai.hierarchical_chunking.token_budget, token_window
# Public Exports:
#   - pack_units
# Database/Table: N/A
# Related Modules: app.ai.hierarchical_chunking.chunk_splitter
# Important Notes: Never splits a unit — caller supplies atomic pieces.
# =============================================================================

from __future__ import annotations

from app.ai.hierarchical_chunking.token_budget import ChunkTokenBudget
from app.ai.hierarchical_chunking.token_window import join_units, tail_token_text, token_count


def pack_units(
    units: list[str],
    budget: ChunkTokenBudget,
    *,
    separator: str = "\n\n",
) -> list[str]:
    """Pack pre-split units into as few chunks as possible under the token budget."""
    if not units:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    def flush() -> None:
        nonlocal current, current_tokens
        if not current:
            return
        chunks.append(join_units(current, separator=separator))
        current = []
        current_tokens = 0

    for unit in units:
        unit_tokens = token_count(unit)

        if not current:
            current = [unit]
            current_tokens = unit_tokens
            continue

        projected = current_tokens + token_count(separator) + unit_tokens
        if projected <= budget.target_max:
            current.append(unit)
            current_tokens = projected
            continue

        if projected <= budget.hard_limit and current_tokens < budget.target_min:
            current.append(unit)
            current_tokens = projected
            continue

        flush()
        overlap = tail_token_text(chunks[-1], budget.overlap_tokens) if chunks else ""
        if overlap:
            current = [overlap, unit]
            current_tokens = token_count(join_units(current, separator=separator))
        else:
            current = [unit]
            current_tokens = unit_tokens

    flush()
    return chunks
