# =============================================================================
# File: __init__.py
# Module/Service: Pipeline Worker — Hierarchical Chunking ([AI])
# Layer: Service
# Purpose: Public exports for hierarchical Markdown chunking.
# Public Exports:
#   - run_hierarchical_chunking, HierarchicalChunkingPlan
# =============================================================================

from app.ai.hierarchical_chunking.pipeline import HierarchicalChunkingPlan, run_hierarchical_chunking

__all__ = ["HierarchicalChunkingPlan", "run_hierarchical_chunking"]
