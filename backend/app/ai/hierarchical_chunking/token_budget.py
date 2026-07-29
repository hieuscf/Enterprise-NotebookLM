# =============================================================================
# File: token_budget.py
# Module/Service: Pipeline Worker — Hierarchical Chunking ([AI])
# Layer: Service
# Purpose: Token budget constants for block-aware hierarchical chunking.
# Responsibilities:
#   - Define target/hard limits and overlap bounds (no magic numbers elsewhere)
# Dependencies:
#   - dataclasses only
# Public Exports:
#   - ChunkTokenBudget
# Database/Table: N/A
# Related Modules: app.ai.hierarchical_chunking.chunk_splitter
# Important Notes: Values follow FR2 v3 hierarchical chunking spec (500–800 target).
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChunkTokenBudget:
    """Token windows for block-level chunk packing."""

    target_min: int = 500
    target_max: int = 800
    hard_limit: int = 1000
    overlap_min: int = 50
    overlap_max: int = 100

    @classmethod
    def default(cls) -> ChunkTokenBudget:
        """Return the production chunking budget."""
        return cls()

    @property
    def overlap_tokens(self) -> int:
        """Overlap applied only when a block must span multiple chunks."""
        return self.overlap_max

    @property
    def overlap_ratio(self) -> float:
        """Ratio form for pipeline_stage_logs metadata."""
        return round(self.overlap_tokens / self.hard_limit, 4)
