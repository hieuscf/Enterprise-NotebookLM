# =============================================================================
# File: metrics_collector.py
# Module/Service: Pipeline Worker — Hierarchical Chunking ([AI])
# Layer: Service
# Purpose: Aggregate chunking statistics for pipeline_stage_logs metadata.
# Responsibilities:
#   - Count heading vs content chunks, averages, max depth
# Dependencies:
#   - app.ai.hierarchical_chunking.types, app.ai.tokens
# Public Exports:
#   - collect_chunking_metrics
# Database/Table: N/A
# Related Modules: app.services.hierarchical_chunking
# Important Notes: Pure function — no I/O.
# =============================================================================

from __future__ import annotations

from app.ai.hierarchical_chunking.types import ChunkingMetrics, PlannedChunk
from app.ai.tokens import get_token_encoding_name
from app.models.enums import ChunkLayoutType


def collect_chunking_metrics(
    planned: list[PlannedChunk],
    *,
    max_tokens: int,
    overlap_ratio: float,
) -> ChunkingMetrics:
    """Summarize a planned chunk list for observability."""
    if not planned:
        return ChunkingMetrics(
            chunk_count=0,
            heading_chunk_count=0,
            content_chunk_count=0,
            avg_chars=0.0,
            avg_tokens=0.0,
            max_depth=0,
            max_tokens=max_tokens,
            overlap_ratio=overlap_ratio,
            tokenizer=get_token_encoding_name(),
        )

    heading_count = sum(1 for chunk in planned if chunk.layout_type == ChunkLayoutType.heading)
    content_count = len(planned) - heading_count
    total_chars = sum(len(chunk.content) for chunk in planned)
    total_tokens = sum(chunk.token_count for chunk in planned)
    max_depth = max(chunk.depth for chunk in planned)

    return ChunkingMetrics(
        chunk_count=len(planned),
        heading_chunk_count=heading_count,
        content_chunk_count=content_count,
        avg_chars=round(total_chars / len(planned), 2),
        avg_tokens=round(total_tokens / len(planned), 2),
        max_depth=max_depth,
        max_tokens=max_tokens,
        overlap_ratio=overlap_ratio,
        tokenizer=get_token_encoding_name(),
    )
