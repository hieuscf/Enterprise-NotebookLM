# =============================================================================
# File: heading_tree_builder.py
# Module/Service: Pipeline Worker — Hierarchical Chunking ([AI])
# Layer: Service
# Purpose: Build a nested heading tree from Markdown lines.
# Responsibilities:
#   - Parse ATX headings (# … ######)
#   - Assign line ranges and breadcrumb paths
# Dependencies:
#   - app.ai.hierarchical_chunking.constants, types
# Public Exports:
#   - build_heading_tree, heading_depth, join_heading_path
# Database/Table: N/A
# Related Modules: app.ai.hierarchical_chunking.block_parser
# Important Notes: Preamble lines before the first heading attach to a synthetic root.
# =============================================================================

from __future__ import annotations

from app.ai.hierarchical_chunking.constants import (
    MARKDOWN_HEADING_RE,
    MAX_HEADING_LEVEL,
    MIN_HEADING_LEVEL,
    ROOT_NODE_TITLE,
)
from app.ai.hierarchical_chunking.types import HeadingNode, MarkdownLine


def heading_depth(level: int) -> int:
    """Map Markdown heading level (#=1) to stored depth (# → 0)."""
    clamped = max(MIN_HEADING_LEVEL, min(MAX_HEADING_LEVEL, level))
    return clamped - MIN_HEADING_LEVEL


def join_heading_path(stack: list[tuple[int, str]]) -> str:
    """Build ``Chapter > Marketing > Digital`` from the active heading stack."""
    return " > ".join(title for _, title in stack)


def build_heading_tree(lines: list[MarkdownLine]) -> HeadingNode:
    """Construct the heading hierarchy with line spans for each node."""
    root = HeadingNode(
        title=ROOT_NODE_TITLE,
        level=0,
        depth=-1,
        heading_path="",
        start_line=1,
        end_line=len(lines) if lines else 0,
    )
    if not lines:
        return root

    stack: list[HeadingNode] = [root]
    title_stack: list[tuple[int, str]] = []

    for line in lines:
        match = MARKDOWN_HEADING_RE.match(line.text.strip())
        if not match:
            continue

        level = len(match.group(1))
        title = match.group(2).strip()
        depth = heading_depth(level)

        while len(stack) > 1 and stack[-1].level >= level:
            closing = stack.pop()
            closing.end_line = line.number - 1

        while title_stack and title_stack[-1][0] >= level:
            title_stack.pop()
        title_stack.append((level, title))
        path = join_heading_path(title_stack)

        node = HeadingNode(
            title=title,
            level=level,
            depth=depth,
            heading_path=path,
            start_line=line.number,
            parent=stack[-1],
        )
        stack[-1].children.append(node)
        stack.append(node)

    last_line = lines[-1].number
    for node in stack[1:]:
        if node.end_line == 0:
            node.end_line = last_line
    root.end_line = last_line
    return root
