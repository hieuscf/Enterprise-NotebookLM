# =============================================================================
# File: chunk_splitter.py
# Module/Service: Pipeline Worker — Hierarchical Chunking ([AI])
# Layer: Service
# Purpose: Block-aware chunk splitting — never split mid-table/list/code/figure.
# Responsibilities:
#   - Dispatch by layout_type; paragraph → sentences → token fallback
#   - Respect ChunkTokenBudget target/hard limits and optional overlap
# Dependencies:
#   - app.ai.hierarchical_chunking.* splitters and unit_packer
# Public Exports:
#   - split_content_block, split_atomic_block, split_paragraph_block, split_list_block
# Database/Table: N/A
# Related Modules: app.ai.hierarchical_chunking.chunk_planner
# Important Notes: Chunk by block structure — not by raw character windows.
# =============================================================================

from __future__ import annotations

from app.ai.hierarchical_chunking.list_splitter import split_list_items
from app.ai.hierarchical_chunking.paragraph_splitter import split_paragraphs
from app.ai.hierarchical_chunking.sentence_splitter import split_sentences
from app.ai.hierarchical_chunking.token_budget import ChunkTokenBudget
from app.ai.hierarchical_chunking.token_window import token_count
from app.ai.hierarchical_chunking.types import ContentBlock
from app.ai.hierarchical_chunking.unit_packer import pack_units
from app.ai.tokens import split_text_by_tokens
from app.models.enums import ChunkLayoutType


def split_content_block(block: ContentBlock, budget: ChunkTokenBudget) -> list[str]:
    """Split one content block according to its layout type and token budget."""
    text = block.text.strip()
    if not text:
        return []

    if _is_atomic_block(block):
        return split_atomic_block(text)
    if block.layout_type == ChunkLayoutType.list:
        return split_list_block(text, budget)
    return split_paragraph_block(text, budget)


def split_atomic_block(text: str) -> list[str]:
    """Keep table / figure / code blocks intact even when they exceed hard_limit."""
    cleaned = text.strip()
    return [cleaned] if cleaned else []


def split_paragraph_block(text: str, budget: ChunkTokenBudget) -> list[str]:
    """Split paragraph blocks on blank lines, then sentences when needed."""
    if token_count(text) <= budget.hard_limit:
        return [text]

    result: list[str] = []
    batch: list[str] = []
    for paragraph in split_paragraphs(text):
        if token_count(paragraph) > budget.hard_limit:
            if batch:
                result.extend(pack_units(batch, budget))
                batch = []
            result.extend(_expand_oversized_paragraph(paragraph, budget))
            continue
        batch.append(paragraph)
    if batch:
        result.extend(pack_units(batch, budget))
    return result


def split_list_block(text: str, budget: ChunkTokenBudget) -> list[str]:
    """Split list blocks only between items — never inside an item."""
    items = split_list_items(text)
    if not items:
        return split_paragraph_block(text, budget)

    result: list[str] = []
    batch: list[str] = []
    for item in items:
        if token_count(item) > budget.hard_limit:
            if batch:
                result.extend(pack_units(batch, budget, separator="\n"))
                batch = []
            result.extend(split_paragraph_block(item, budget))
            continue
        batch.append(item)
    if batch:
        result.extend(pack_units(batch, budget, separator="\n"))
    return result


def _is_atomic_block(block: ContentBlock) -> bool:
    return block.is_code_fence or block.layout_type in {
        ChunkLayoutType.table,
        ChunkLayoutType.figure_caption,
    }


def _expand_oversized_paragraph(paragraph: str, budget: ChunkTokenBudget) -> list[str]:
    """Break one oversized paragraph into sentence-sized chunks under the budget."""
    sentences = split_sentences(paragraph)
    if len(sentences) == 1:
        return _token_fallback_split(paragraph, budget)

    result: list[str] = []
    batch: list[str] = []
    for sentence in sentences:
        if token_count(sentence) > budget.hard_limit:
            if batch:
                result.extend(pack_units(batch, budget, separator=" "))
                batch = []
            result.extend(_token_fallback_split(sentence, budget))
            continue
        batch.append(sentence)
    if batch:
        result.extend(pack_units(batch, budget, separator=" "))
    return result


def _token_fallback_split(text: str, budget: ChunkTokenBudget) -> list[str]:
    """Last resort when a single sentence still exceeds hard_limit."""
    overlap_ratio = budget.overlap_tokens / budget.hard_limit
    return split_text_by_tokens(
        text,
        max_tokens=budget.hard_limit,
        overlap_ratio=overlap_ratio,
    )
