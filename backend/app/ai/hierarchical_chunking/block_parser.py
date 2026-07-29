# =============================================================================
# File: block_parser.py
# Module/Service: Pipeline Worker — Hierarchical Chunking ([AI])
# Layer: Service
# Purpose: Parse Markdown content blocks and map layout types from layout_metadata.
# Responsibilities:
#   - Extract paragraph/table/list/figure blocks between headings
#   - Prefer layout_metadata block summaries; infer from Markdown when missing
# Dependencies:
#   - app.ai.hierarchical_chunking.constants, types, heading_tree_builder
#   - app.ai.layout.PAGINATED_FILE_TYPES
# Public Exports:
#   - attach_content_blocks, map_layout_type, infer_layout_type_from_markdown
# Database/Table: N/A
# Related Modules: app.ai.hierarchical_chunking.chunk_planner
# Important Notes: Headings themselves are never emitted as ContentBlock rows here.
# =============================================================================

from __future__ import annotations

from typing import Any

from app.ai.hierarchical_chunking.constants import (
    DEFAULT_CONTENT_LAYOUT_TYPE,
    FENCE_RE,
    IMAGE_ONLY_RE,
    LAYOUT_BLOCK_TYPE_MAP,
    LIST_ITEM_RE,
    MARKDOWN_HEADING_RE,
    TABLE_DELIMITER_RE,
    TABLE_ROW_RE,
)
from app.ai.hierarchical_chunking.types import ContentBlock, HeadingNode, MarkdownLine
from app.ai.layout import PAGINATED_FILE_TYPES
from app.models.enums import ChunkLayoutType, FileType


def attach_content_blocks(
    *,
    root: HeadingNode,
    lines: list[MarkdownLine],
    layout_metadata: dict[str, Any] | None,
    file_type: FileType,
) -> None:
    """Populate ``content_blocks`` on each heading node (and root preamble)."""
    line_map = {line.number: line for line in lines}
    layout_blocks = _layout_block_summaries(layout_metadata)
    paginated = file_type in PAGINATED_FILE_TYPES
    section_counter = 0

    def visit(node: HeadingNode) -> None:
        nonlocal section_counter
        node_section_index: int | None = None
        if not paginated and node.level > 0:
            section_counter += 1
            node_section_index = section_counter
            node.section_index = node_section_index

        body_lines = _body_lines_for_node(node, line_map)
        blocks = _parse_blocks_from_lines(body_lines, layout_blocks, paginated=paginated)
        for block in blocks:
            block.section_index = node_section_index
        node.content_blocks.extend(blocks)

        for child in node.children:
            visit(child)

    visit(root)


def map_layout_type(block_type: str | None) -> ChunkLayoutType:
    """Map layout_metadata block_type to the ChunkLayoutType enum."""
    if not block_type:
        return DEFAULT_CONTENT_LAYOUT_TYPE
    return LAYOUT_BLOCK_TYPE_MAP.get(block_type.strip().lower(), DEFAULT_CONTENT_LAYOUT_TYPE)


def infer_layout_type_from_markdown(text: str) -> ChunkLayoutType:
    """Infer layout type from Markdown syntax when metadata is unavailable."""
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return DEFAULT_CONTENT_LAYOUT_TYPE
    if all(_TABLE_ROW_RE.match(line) for line in lines[:2]):
        return ChunkLayoutType.table
    if all(LIST_ITEM_RE.match(line) for line in lines):
        return ChunkLayoutType.list
    if all(IMAGE_ONLY_RE.match(line) for line in lines):
        return ChunkLayoutType.figure_caption
    return DEFAULT_CONTENT_LAYOUT_TYPE


def _layout_block_summaries(layout_metadata: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not layout_metadata:
        return []
    blocks = layout_metadata.get("blocks")
    if not isinstance(blocks, list):
        return []
    return [block for block in blocks if isinstance(block, dict)]


def _body_lines_for_node(node: HeadingNode, line_map: dict[int, MarkdownLine]) -> list[MarkdownLine]:
    start = node.start_line + 1 if node.level > 0 else node.start_line
    if node.children:
        end = node.children[0].start_line - 1
    else:
        end = node.end_line
    if end < start:
        return []
    return [line_map[n] for n in range(start, end + 1) if n in line_map]


def _parse_blocks_from_lines(
    lines: list[MarkdownLine],
    layout_blocks: list[dict[str, Any]],
    *,
    paginated: bool,
) -> list[ContentBlock]:
    blocks: list[ContentBlock] = []
    index = 0
    order_index = 0
    layout_cursor = 0

    while index < len(lines):
        line = lines[index]
        stripped = line.text.strip()
        if not stripped or MARKDOWN_HEADING_RE.match(stripped):
            index += 1
            continue
        if FENCE_RE.match(stripped):
            end = _skip_fence(lines, index)
            text = "\n".join(entry.text for entry in lines[index:end])
            blocks.append(
                _make_block(
                    text=text,
                    start=line.number,
                    end=lines[end - 1].number,
                    order_index=order_index,
                    layout_blocks=layout_blocks,
                    layout_cursor=layout_cursor,
                    paginated=paginated,
                    is_code_fence=True,
                )
            )
            layout_cursor += 1
            order_index += 1
            index = end
            continue
        if _is_table_start(lines, index):
            end = _skip_table(lines, index)
            text = "\n".join(entry.text for entry in lines[index:end])
            blocks.append(
                _make_block(
                    text=text,
                    start=line.number,
                    end=lines[end - 1].number,
                    order_index=order_index,
                    layout_blocks=layout_blocks,
                    layout_cursor=layout_cursor,
                    paginated=paginated,
                    fallback=ChunkLayoutType.table,
                )
            )
            layout_cursor += 1
            order_index += 1
            index = end
            continue
        if LIST_ITEM_RE.match(stripped):
            end = _skip_list(lines, index)
            text = "\n".join(entry.text for entry in lines[index:end])
            blocks.append(
                _make_block(
                    text=text,
                    start=line.number,
                    end=lines[end - 1].number,
                    order_index=order_index,
                    layout_blocks=layout_blocks,
                    layout_cursor=layout_cursor,
                    paginated=paginated,
                    fallback=ChunkLayoutType.list,
                )
            )
            layout_cursor += 1
            order_index += 1
            index = end
            continue
        if IMAGE_ONLY_RE.match(stripped):
            blocks.append(
                _make_block(
                    text=stripped,
                    start=line.number,
                    end=line.number,
                    order_index=order_index,
                    layout_blocks=layout_blocks,
                    layout_cursor=layout_cursor,
                    paginated=paginated,
                    fallback=ChunkLayoutType.figure_caption,
                )
            )
            layout_cursor += 1
            order_index += 1
            index += 1
            continue

        end = _skip_paragraph(lines, index)
        text = "\n".join(entry.text for entry in lines[index:end]).strip()
        if text:
            blocks.append(
                _make_block(
                    text=text,
                    start=line.number,
                    end=lines[end - 1].number,
                    order_index=order_index,
                    layout_blocks=layout_blocks,
                    layout_cursor=layout_cursor,
                    paginated=paginated,
                )
            )
            layout_cursor += 1
            order_index += 1
        index = end

    return blocks


def _make_block(
    *,
    text: str,
    start: int,
    end: int,
    order_index: int,
    layout_blocks: list[dict[str, Any]],
    layout_cursor: int,
    paginated: bool,
    fallback: ChunkLayoutType | None = None,
    is_code_fence: bool = False,
) -> ContentBlock:
    layout = _layout_at(layout_blocks, layout_cursor)
    layout_type = map_layout_type(layout.get("block_type") if layout else None)
    if layout_type == DEFAULT_CONTENT_LAYOUT_TYPE and fallback is not None:
        layout_type = fallback
    if layout_type == DEFAULT_CONTENT_LAYOUT_TYPE:
        layout_type = infer_layout_type_from_markdown(text)

    page_number = None
    if paginated and layout:
        value = layout.get("page_number")
        if isinstance(value, int) and value > 0:
            page_number = value

    return ContentBlock(
        text=text,
        layout_type=layout_type,
        start_line=start,
        end_line=end,
        order_index=order_index,
        page_number=page_number,
        is_code_fence=is_code_fence,
    )


def _layout_at(layout_blocks: list[dict[str, Any]], cursor: int) -> dict[str, Any] | None:
    if cursor < len(layout_blocks):
        return layout_blocks[cursor]
    return None


def _is_table_start(lines: list[MarkdownLine], index: int) -> bool:
    if not TABLE_ROW_RE.match(lines[index].text):
        return False
    nxt = index + 1
    return (
        nxt < len(lines)
        and TABLE_ROW_RE.match(lines[nxt].text) is not None
        and TABLE_DELIMITER_RE.match(lines[nxt].text) is not None
    )


def _skip_table(lines: list[MarkdownLine], index: int) -> int:
    cursor = index
    while cursor < len(lines) and TABLE_ROW_RE.match(lines[cursor].text):
        cursor += 1
    return cursor


def _skip_fence(lines: list[MarkdownLine], index: int) -> int:
    cursor = index + 1
    while cursor < len(lines):
        if FENCE_RE.match(lines[cursor].text):
            return cursor + 1
        cursor += 1
    return cursor


def _skip_list(lines: list[MarkdownLine], index: int) -> int:
    cursor = index
    while cursor < len(lines):
        stripped = lines[cursor].text.strip()
        if not stripped:
            break
        if MARKDOWN_HEADING_RE.match(stripped):
            break
        if not LIST_ITEM_RE.match(stripped) and cursor > index:
            break
        cursor += 1
    return cursor


def _skip_paragraph(lines: list[MarkdownLine], index: int) -> int:
    cursor = index
    while cursor < len(lines):
        stripped = lines[cursor].text.strip()
        if not stripped:
            break
        if MARKDOWN_HEADING_RE.match(stripped):
            break
        if _is_table_start(lines, cursor) or LIST_ITEM_RE.match(stripped) or FENCE_RE.match(stripped):
            break
        cursor += 1
    return max(cursor, index + 1)


_TABLE_ROW_RE = TABLE_ROW_RE
