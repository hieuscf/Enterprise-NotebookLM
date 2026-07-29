# =============================================================================
# File: metrics_collector.py
# Module/Service: Pipeline Worker — Hierarchical Chunking ([AI])
# Layer: Service
# Purpose: Aggregate chunking statistics for pipeline_stage_logs metadata.
# Responsibilities:
#   - Count sections, layout types, token min/max/avg for observability
# Dependencies:
#   - app.ai.hierarchical_chunking.types, token_budget, app.ai.tokens
# Public Exports:
#   - collect_chunking_metrics
# Database/Table: N/A
# Related Modules: app.services.hierarchical_chunking
# Important Notes: Pure function — no I/O.
# =============================================================================

from __future__ import annotations

from app.ai.hierarchical_chunking.token_budget import ChunkTokenBudget
from app.ai.hierarchical_chunking.types import ChunkingMetrics, PlannedChunk
from app.ai.tokens import get_token_encoding_name
from app.models.enums import ChunkLayoutType


def collect_chunking_metrics(
    planned: list[PlannedChunk],
    *,
    budget: ChunkTokenBudget,
) -> ChunkingMetrics:
    """Summarize a planned chunk list for observability."""
    if not planned:
        return ChunkingMetrics.empty(budget)

    heading_count = sum(1 for chunk in planned if chunk.layout_type == ChunkLayoutType.heading)
    content_count = len(planned) - heading_count
    token_counts = [chunk.token_count for chunk in planned]
    total_tokens = sum(token_counts)
    total_chars = sum(len(chunk.content) for chunk in planned)
    max_depth = max(chunk.depth for chunk in planned)

    return ChunkingMetrics(
        sections_count=heading_count,
        chunks_created=len(planned),
        heading_chunk_count=heading_count,
        content_chunk_count=content_count,
        max_depth=max_depth,
        avg_chunk_tokens=round(total_tokens / len(planned), 2),
        largest_chunk_tokens=max(token_counts),
        smallest_chunk_tokens=min(token_counts),
        tables=_count_layout(planned, ChunkLayoutType.table),
        lists=_count_layout(planned, ChunkLayoutType.list),
        paragraphs=_count_layout(planned, ChunkLayoutType.paragraph),
        figure_captions=_count_layout(planned, ChunkLayoutType.figure_caption),
        avg_chars=round(total_chars / len(planned), 2),
        max_tokens=budget.hard_limit,
        overlap_ratio=budget.overlap_ratio,
        tokenizer=get_token_encoding_name(),
    )


def _count_layout(planned: list[PlannedChunk], layout_type: ChunkLayoutType) -> int:
    return sum(1 for chunk in planned if chunk.layout_type == layout_type)
