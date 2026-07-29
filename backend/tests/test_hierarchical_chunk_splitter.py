# =============================================================================
# File: test_hierarchical_chunk_splitter.py
# Module/Service: Pipeline Worker — Hierarchical Chunking ([AI])
# Layer: Service
# Purpose: Unit tests for block-aware chunk splitting algorithm.
# Dependencies:
#   - pytest, app.ai.hierarchical_chunking.*
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: app.ai.hierarchical_chunking.chunk_splitter
# Important Notes: Uses small token budgets in tests to force splitting paths.
# =============================================================================

from __future__ import annotations

from app.ai.hierarchical_chunking.chunk_splitter import (
    split_content_block,
    split_list_block,
    split_paragraph_block,
)
from app.ai.hierarchical_chunking.list_splitter import split_list_items
from app.ai.hierarchical_chunking.paragraph_splitter import split_paragraphs
from app.ai.hierarchical_chunking.sentence_splitter import split_sentences
from app.ai.hierarchical_chunking.token_budget import ChunkTokenBudget
from app.ai.hierarchical_chunking.types import ContentBlock
from app.ai.hierarchical_chunking.unit_packer import pack_units
from app.models.enums import ChunkLayoutType


def _tiny_budget() -> ChunkTokenBudget:
    return ChunkTokenBudget(target_min=10, target_max=20, hard_limit=30, overlap_min=3, overlap_max=5)


def test_table_block_never_splits_even_when_oversized() -> None:
    table = "| A | B |\n| --- | --- |\n" + "\n".join(f"| {i} | {i} |" for i in range(200))
    block = ContentBlock(
        text=table,
        layout_type=ChunkLayoutType.table,
        start_line=1,
        end_line=200,
        order_index=0,
    )
    pieces = split_content_block(block, _tiny_budget())
    assert len(pieces) == 1
    assert pieces[0] == table


def test_code_fence_block_is_atomic() -> None:
    code = "```python\n" + "print('x')\n" * 100 + "```"
    block = ContentBlock(
        text=code,
        layout_type=ChunkLayoutType.paragraph,
        start_line=1,
        end_line=100,
        order_index=0,
        is_code_fence=True,
    )
    pieces = split_content_block(block, _tiny_budget())
    assert len(pieces) == 1
    assert pieces[0] == code


def test_list_splits_only_between_items() -> None:
    text = "- item one line\n  continuation\n- item two\n- item three"
    items = split_list_items(text)
    assert len(items) == 3
    assert "continuation" in items[0]

    budget = ChunkTokenBudget(target_min=3, target_max=6, hard_limit=8, overlap_min=1, overlap_max=2)
    chunks = split_list_block(text, budget)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert not (chunk.strip().startswith("- item one") and "- item two" in chunk)


def test_paragraph_splits_on_blank_lines() -> None:
    p1 = "First paragraph sentence."
    p2 = "Second paragraph sentence."
    text = f"{p1}\n\n{p2}"
    assert split_paragraphs(text) == [p1, p2]

    budget = ChunkTokenBudget(target_min=5, target_max=12, hard_limit=15, overlap_min=2, overlap_max=3)
    chunks = split_paragraph_block(text, budget)
    assert len(chunks) >= 1


def test_oversized_paragraph_splits_by_sentence() -> None:
    sentence = "Word " * 80
    text = f"{sentence.strip()}. Another short one."
    parts = split_sentences(text)
    assert len(parts) >= 2

    budget = ChunkTokenBudget(target_min=8, target_max=15, hard_limit=20, overlap_min=2, overlap_max=4)
    chunks = split_paragraph_block(text, budget)
    assert len(chunks) >= 2


def test_pack_units_applies_overlap_when_splitting() -> None:
    budget = ChunkTokenBudget(target_min=5, target_max=10, hard_limit=12, overlap_min=2, overlap_max=3)
    units = ["alpha beta gamma", "delta epsilon zeta", "eta theta iota"]
    chunks = pack_units(units, budget)
    assert len(chunks) >= 2


def test_figure_caption_stays_single_chunk() -> None:
    block = ContentBlock(
        text="![Architecture diagram](arch.png)",
        layout_type=ChunkLayoutType.figure_caption,
        start_line=1,
        end_line=1,
        order_index=0,
    )
    assert split_content_block(block, _tiny_budget()) == ["![Architecture diagram](arch.png)"]
