# =============================================================================
# File: test_canonical_locator.py
# Module/Service: Document Intelligence / Citation
# Layer: Test
# Purpose: Unit tests for Canonical Markdown locator (sub-span, multi-block).
# Responsibilities:
#   - Exact / normalized snippet match
#   - Sub-span of chunk is not whole-chunk highlight
#   - Stable block ids + markdown spans
# Dependencies:
#   - pytest, app.ai.canonical_locator, app.ai.layout
# Public Exports: N/A
# Database/Table: N/A
# Related Modules: Knowledge View, CitationResponse.locator
# Important Notes: Deterministic — no LLM / no PDF.
# =============================================================================

from __future__ import annotations

from app.ai.canonical_locator import (
    attach_markdown_spans,
    make_block_id,
    resolve_canonical_locator,
)
from app.ai.layout import build_layout_analysis


MARKDOWN = """# Báo cáo tài chính

## Hoạt động kinh doanh

Hoạt động chính trong kỳ của Công ty và các công ty con là cung cấp dịch vụ.

Các hoạt động khác trong kỳ.
"""


def test_make_block_id_stable() -> None:
    assert make_block_id(0) == "b0000"
    assert make_block_id(17) == "b0017"


def test_layout_analysis_assigns_ids_and_spans() -> None:
    analysis = build_layout_analysis(markdown=MARKDOWN, item_pages=[])
    assert analysis.blocks
    assert all(b.id and b.id.startswith("b") for b in analysis.blocks)
    with_spans = [b for b in analysis.blocks if b.markdown_start is not None]
    assert with_spans, "expected at least one block with markdown spans"
    # Heading tree carries block_id
    assert analysis.heading_tree
    assert analysis.heading_tree[0].get("block_id")


def test_citation_subspan_not_whole_chunk() -> None:
    analysis = build_layout_analysis(markdown=MARKDOWN, item_pages=[])
    blocks = [b.as_dict() for b in analysis.blocks]
    chunk = (
        "## Hoạt động kinh doanh\n\n"
        "Hoạt động chính trong kỳ của Công ty và các công ty con là cung cấp dịch vụ.\n\n"
        "Các hoạt động khác trong kỳ."
    )
    snippet = "Hoạt động chính trong kỳ của Công ty và các công ty con là cung cấp dịch vụ."
    locator = resolve_canonical_locator(
        markdown=MARKDOWN,
        blocks=blocks,
        text_snippet=snippet,
        chunk_content=chunk,
    )
    assert locator.confidence == "exact"
    assert locator.markdown_start is not None
    assert locator.markdown_end is not None
    assert MARKDOWN[locator.markdown_start : locator.markdown_end] == snippet
    assert locator.ranges
    # Highlight range length equals snippet, not whole chunk
    total = sum(r.end - r.start for r in locator.ranges)
    assert total == len(snippet)
    assert total < len(chunk)


def test_attach_spans_backfills_legacy_blocks() -> None:
    raw = [
        {"order_index": 0, "block_type": "heading", "text": "Báo cáo tài chính"},
        {
            "order_index": 1,
            "block_type": "paragraph",
            "text": "Hoạt động chính trong kỳ của Công ty và các công ty con là cung cấp dịch vụ.",
        },
    ]
    enriched = attach_markdown_spans(MARKDOWN, raw)
    assert enriched[0]["id"] == "b0000"
    assert enriched[1]["markdown_start"] is not None
    assert enriched[1]["markdown_end"] is not None
