# =============================================================================
# File: pipeline.py
# Module/Service: Pipeline Worker — Hierarchical Chunking ([AI])
# Layer: Service
# Purpose: Orchestrate pure hierarchical chunking steps (no I/O).
# Responsibilities:
#   - Wire parser → tree → blocks → planner → metrics
# Dependencies:
#   - app.ai.hierarchical_chunking.* submodules
# Public Exports:
#   - run_hierarchical_chunking
# Database/Table: N/A
# Related Modules: app.services.hierarchical_chunking
# Important Notes: Rule-based only — no LLM / embedding / graph calls.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass

from app.ai.hierarchical_chunking.block_parser import attach_content_blocks
from app.ai.hierarchical_chunking.chunk_planner import plan_hierarchical_chunks
from app.ai.hierarchical_chunking.heading_tree_builder import build_heading_tree
from app.ai.hierarchical_chunking.markdown_parser import parse_markdown_lines
from app.ai.hierarchical_chunking.metrics_collector import collect_chunking_metrics
from app.ai.hierarchical_chunking.token_budget import ChunkTokenBudget
from app.ai.hierarchical_chunking.types import ChunkingInput, ChunkingMetrics, PlannedChunk


@dataclass(frozen=True, slots=True)
class HierarchicalChunkingPlan:
    """Pure planning output consumed by the persistence service."""

    planned_chunks: list[PlannedChunk]
    metrics: ChunkingMetrics


def run_hierarchical_chunking(
    chunk_input: ChunkingInput,
    *,
    budget: ChunkTokenBudget | None = None,
    max_tokens: int | None = None,
    overlap_ratio: float | None = None,
) -> HierarchicalChunkingPlan:
    """Execute the rule-based hierarchical chunking pipeline."""
    token_budget = budget or ChunkTokenBudget.default()
    lines = parse_markdown_lines(chunk_input.markdown)
    root = build_heading_tree(lines)
    attach_content_blocks(
        root=root,
        lines=lines,
        layout_metadata=chunk_input.layout_metadata,
        file_type=chunk_input.file_type,
    )
    planned = plan_hierarchical_chunks(
        root,
        budget=token_budget,
    )
    metrics = collect_chunking_metrics(
        planned,
        budget=token_budget,
    )
    return HierarchicalChunkingPlan(planned_chunks=planned, metrics=metrics)
