# =============================================================================
# File: constants.py
# Module/Service: Pipeline Worker — Hierarchical Chunking ([AI])
# Layer: Service
# Purpose: Configuration constants for hierarchical Markdown chunking (FR2 v3).
# Responsibilities:
#   - Centralize regex patterns and layout-type mapping defaults
# Dependencies:
#   - app.models.enums.ChunkLayoutType
# Public Exports:
#   - MARKDOWN_HEADING_RE, layout maps, depth helpers
# Database/Table: N/A
# Related Modules: app.ai.hierarchical_chunking.*
# Important Notes: Token budgets live in token_budget.py — not duplicated here.
# =============================================================================

from __future__ import annotations

import re

from app.models.enums import ChunkLayoutType

MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
TABLE_ROW_RE = re.compile(r"^\s*\|.*\|?\s*$")
TABLE_DELIMITER_RE = re.compile(r"^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$")
LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\S")
IMAGE_ONLY_RE = re.compile(r"^\s*!\[[^\]]*\]\([^)]*\)\s*$")

MIN_HEADING_LEVEL = 1
MAX_HEADING_LEVEL = 6

LAYOUT_BLOCK_TYPE_MAP: dict[str, ChunkLayoutType] = {
    "heading": ChunkLayoutType.heading,
    "paragraph": ChunkLayoutType.paragraph,
    "table": ChunkLayoutType.table,
    "list": ChunkLayoutType.list,
    "figure": ChunkLayoutType.figure_caption,
    "figure_caption": ChunkLayoutType.figure_caption,
}

DEFAULT_CONTENT_LAYOUT_TYPE = ChunkLayoutType.paragraph
ROOT_NODE_TITLE = "__root__"

# Block processing priority (document order preserved; one block → one split pass):
# heading (planner) → paragraph → list → table → figure_caption
