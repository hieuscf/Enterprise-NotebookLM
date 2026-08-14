# =============================================================================
# File: types.py
# Module/Service: Pipeline Worker — Hierarchical Chunking ([AI])
# Layer: Service
# Purpose: Shared datatypes for the hierarchical chunking pipeline.
# Responsibilities:
#   - Define Markdown lines, heading nodes, content blocks, planned chunks
# Dependencies:
#   - app.models.enums.ChunkLayoutType, FileType
# Public Exports:
#   - MarkdownLine, HeadingNode, ContentBlock, PlannedChunk, ChunkingMetrics
# Database/Table: document_chunks (target shape)
# Related Modules: app.ai.hierarchical_chunking.*
# Important Notes: PlannedChunk uses temp IDs until persisted to PostgreSQL.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.ai.hierarchical_chunking.token_budget import ChunkTokenBudget
from app.ai.tokens import get_token_encoding_name
from app.models.enums import ChunkLayoutType, FileType


@dataclass(frozen=True, slots=True)
class MarkdownLine:
    """One source line with its 1-based index in the Markdown file."""

    number: int
    text: str


@dataclass
class ContentBlock:
    """A non-heading content unit scoped under a heading node."""

    text: str
    layout_type: ChunkLayoutType
    start_line: int
    end_line: int
    order_index: int
    page_number: int | None = None
    section_index: int | None = None
    is_code_fence: bool = False


@dataclass
class HeadingNode:
    """One heading in the document outline tree."""

    title: str
    level: int
    depth: int
    heading_path: str
    start_line: int
    end_line: int = 0
    section_index: int | None = None
    parent: HeadingNode | None = None
    children: list[HeadingNode] = field(default_factory=list)
    content_blocks: list[ContentBlock] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class PlannedChunk:
    """In-memory chunk prior to ``document_chunks`` insert."""

    temp_id: str
    parent_temp_id: str | None
    chunk_index: int
    content: str
    layout_type: ChunkLayoutType
    depth: int
    heading_path: str | None
    section: str | None
    page_number: int | None
    section_index: int | None
    token_count: int
    section_number: str | None = None
    parent_section_number: str | None = None
    heading_level: int | None = None


@dataclass(frozen=True, slots=True)
class ChunkingInput:
    """Inputs for one hierarchical chunking run."""

    markdown: str
    layout_metadata: dict[str, Any] | None
    file_type: FileType


@dataclass(frozen=True, slots=True)
class ChunkingMetrics:
    """Observability payload for ``pipeline_stage_logs.metadata``."""

    sections_count: int
    chunks_created: int
    heading_chunk_count: int
    content_chunk_count: int
    max_depth: int
    avg_chunk_tokens: float
    largest_chunk_tokens: int
    smallest_chunk_tokens: int
    tables: int
    lists: int
    paragraphs: int
    figure_captions: int
    avg_chars: float
    max_tokens: int
    overlap_ratio: float
    tokenizer: str

    @classmethod
    def empty(cls, budget: ChunkTokenBudget) -> ChunkingMetrics:
        """Zero-valued metrics when no chunks were produced."""
        return cls(
            sections_count=0,
            chunks_created=0,
            heading_chunk_count=0,
            content_chunk_count=0,
            max_depth=0,
            avg_chunk_tokens=0.0,
            largest_chunk_tokens=0,
            smallest_chunk_tokens=0,
            tables=0,
            lists=0,
            paragraphs=0,
            figure_captions=0,
            avg_chars=0.0,
            max_tokens=budget.hard_limit,
            overlap_ratio=budget.overlap_ratio,
            tokenizer=get_token_encoding_name(),
        )

    def to_pipeline_log(self, processing_time_ms: int) -> dict[str, Any]:
        """Metadata written to ``pipeline_stage_logs`` for hierarchical_chunking."""
        return {
            "sections_count": self.sections_count,
            "chunks_created": self.chunks_created,
            "max_depth": self.max_depth,
            "avg_chunk_tokens": self.avg_chunk_tokens,
            "largest_chunk_tokens": self.largest_chunk_tokens,
            "smallest_chunk_tokens": self.smallest_chunk_tokens,
            "tables": self.tables,
            "lists": self.lists,
            "paragraphs": self.paragraphs,
            "processing_time_ms": processing_time_ms,
            # Legacy / downstream-compatible aliases
            "chunk_count": self.chunks_created,
            "heading_chunk_count": self.heading_chunk_count,
            "content_chunk_count": self.content_chunk_count,
            "avg_tokens": self.avg_chunk_tokens,
            "avg_chars": self.avg_chars,
            "figure_captions": self.figure_captions,
            "max_tokens": self.max_tokens,
            "overlap_ratio": self.overlap_ratio,
            "tokenizer": self.tokenizer,
        }

    def as_dict(self) -> dict[str, Any]:
        """Backward-compatible alias without ``processing_time_ms``."""
        payload = self.to_pipeline_log(processing_time_ms=0)
        payload.pop("processing_time_ms", None)
        return payload
