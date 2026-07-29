# =============================================================================
# File: chunk_planner.py
# Module/Service: Pipeline Worker — Hierarchical Chunking ([AI])
# Layer: Service
# Purpose: Plan heading + content chunks with parent relationships.
# Responsibilities:
#   - Emit one heading chunk per heading node
#   - Emit content chunks parented to their enclosing heading
# Dependencies:
#   - app.ai.hierarchical_chunking.chunk_splitter, constants, types
# Public Exports:
#   - plan_hierarchical_chunks
# Database/Table: document_chunks (planned rows)
# Related Modules: app.ai.hierarchical_chunking.parent_resolver
# Important Notes: DFS pre-order guarantees parents are planned before children.
# =============================================================================

from __future__ import annotations

from uuid import uuid4

from app.ai.hierarchical_chunking.chunk_splitter import split_content_block
from app.ai.hierarchical_chunking.constants import ROOT_NODE_TITLE
from app.ai.hierarchical_chunking.types import ContentBlock, HeadingNode, PlannedChunk
from app.ai.tokens import count_tokens
from app.models.enums import ChunkLayoutType


def plan_hierarchical_chunks(
    root: HeadingNode,
    *,
    max_tokens: int,
    overlap_ratio: float,
) -> list[PlannedChunk]:
    """Build the full planned chunk list for one document version."""
    planned: list[PlannedChunk] = []
    chunk_index = 0

    def append_chunk(
        *,
        content: str,
        layout_type: ChunkLayoutType,
        depth: int,
        heading_path: str | None,
        section: str | None,
        parent_temp_id: str | None,
        page_number: int | None,
        section_index: int | None,
    ) -> str:
        nonlocal chunk_index
        temp_id = str(uuid4())
        planned.append(
            PlannedChunk(
                temp_id=temp_id,
                parent_temp_id=parent_temp_id,
                chunk_index=chunk_index,
                content=content,
                layout_type=layout_type,
                depth=depth,
                heading_path=heading_path,
                section=section,
                page_number=page_number,
                section_index=section_index,
                token_count=count_tokens(content),
            )
        )
        chunk_index += 1
        return temp_id

    def append_content_block(
        block: ContentBlock,
        *,
        parent_temp_id: str | None,
        heading_path: str | None,
        section: str | None,
        depth: int,
    ) -> None:
        pieces = split_content_block(
            block.text,
            max_tokens=max_tokens,
            overlap_ratio=overlap_ratio,
        )
        for piece in pieces:
            append_chunk(
                content=piece,
                layout_type=block.layout_type,
                depth=depth,
                heading_path=heading_path,
                section=section,
                parent_temp_id=parent_temp_id,
                page_number=block.page_number,
                section_index=block.section_index,
            )

    def visit_heading(node: HeadingNode, parent_heading_temp_id: str | None) -> None:
        heading_temp_id: str | None = parent_heading_temp_id
        if node.title != ROOT_NODE_TITLE:
            heading_temp_id = append_chunk(
                content=node.title,
                layout_type=ChunkLayoutType.heading,
                depth=node.depth,
                heading_path=node.heading_path,
                section=node.title,
                parent_temp_id=parent_heading_temp_id,
                page_number=_first_page_number(node.content_blocks),
                section_index=node.section_index,
            )

        content_depth = node.depth + 1 if node.title != ROOT_NODE_TITLE else 0
        for block in node.content_blocks:
            append_content_block(
                block,
                parent_temp_id=heading_temp_id,
                heading_path=node.heading_path or None,
                section=node.title if node.title != ROOT_NODE_TITLE else None,
                depth=content_depth,
            )
        for child in node.children:
            visit_heading(child, heading_temp_id)

    visit_heading(root, None)
    return planned


def _first_page_number(blocks: list[ContentBlock]) -> int | None:
    for block in blocks:
        if block.page_number is not None:
            return block.page_number
    return None


def _first_section_index(blocks: list[ContentBlock]) -> int | None:
    for block in blocks:
        if block.section_index is not None:
            return block.section_index
    return None
