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


@dataclass(frozen=True, slots=True)
class PersistedChunk:
    """Chunk after DB insert with resolved parent reference."""

    planned: PlannedChunk
    db_id: UUID
    parent_db_id: UUID | None


@dataclass(frozen=True, slots=True)
class ChunkingInput:
    """Inputs for one hierarchical chunking run."""

    markdown: str
    layout_metadata: dict[str, Any] | None
    file_type: FileType


@dataclass(frozen=True, slots=True)
class ChunkingMetrics:
    """Observability payload for ``pipeline_stage_logs.metadata``."""

    chunk_count: int
    heading_chunk_count: int
    content_chunk_count: int
    avg_chars: float
    avg_tokens: float
    max_depth: int
    max_tokens: int
    overlap_ratio: float
    tokenizer: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "chunk_count": self.chunk_count,
            "heading_chunk_count": self.heading_chunk_count,
            "content_chunk_count": self.content_chunk_count,
            "avg_chars": self.avg_chars,
            "avg_tokens": self.avg_tokens,
            "max_depth": self.max_depth,
            "max_tokens": self.max_tokens,
            "overlap_ratio": self.overlap_ratio,
            "tokenizer": self.tokenizer,
        }
