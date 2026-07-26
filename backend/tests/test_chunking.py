# =============================================================================
# File: test_chunking.py
# Module/Service: Pipeline Worker — Chunking ([AI])
# Layer: Service
# Purpose: Unit tests for structure-aware chunking (FR2).
# Responsibilities:
#   - Heading/paragraph/sentence packing, offsets, semantic overlap, fallback
# Dependencies:
#   - pytest, app.ai.chunking, app.ai.ocr.CleanedPage
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: app.ai.chunking
# Important Notes: Stdlib-only algorithm — no LangChain/spaCy.
# =============================================================================

from __future__ import annotations

from app.ai.chunking import estimate_tokens, run_chunking
from app.ai.ocr import CleanedPage


def test_small_document_keeps_paragraph_structure() -> None:
    pages = [
        CleanedPage(
            page_number=1,
            section="Overview",
            text=(
                "Enterprise NotebookLM\n\n"
                "Acme Corporation uses LightRAG for Dual-level Graph retrieval. "
                "Vector Retrieval indexes Document Chunks in Qdrant."
            ),
        )
    ]
    chunks = run_chunking(pages, max_chars=1200)
    assert len(chunks) >= 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].page_number == 1
    assert chunks[0].heading is not None
    assert chunks[0].token_count == estimate_tokens(chunks[0].content)
    assert chunks[0].start_offset < chunks[0].end_offset
    assert chunks[0].metadata["page"] == 1
    assert "paragraph" in chunks[0].metadata


def test_merge_small_paragraphs_under_same_heading() -> None:
    pages = [
        CleanedPage(
            page_number=1,
            text=(
                "## Introduction\n\n"
                "Short para one.\n\n"
                "Short para two.\n\n"
                "Short para three."
            ),
        )
    ]
    chunks = run_chunking(pages, max_chars=500, min_merge_chars=50)
    assert len(chunks) == 1
    assert "Short para one" in chunks[0].content
    assert "Short para three" in chunks[0].content
    assert chunks[0].heading == "Introduction"


def test_oversized_paragraph_splits_on_sentences() -> None:
    sentences = [
        f"This is sentence number {i} about enterprise knowledge retrieval systems."
        for i in range(1, 40)
    ]
    pages = [CleanedPage(page_number=2, text=" ".join(sentences))]
    chunks = run_chunking(pages, max_chars=200, sentence_overlap=1)
    assert len(chunks) > 1
    # No mid-word garbage from fixed windows for normal sentences.
    for chunk in chunks:
        assert chunk.content.endswith(".")
        assert chunk.start_offset < chunk.end_offset


def test_sentence_overlap_is_semantic() -> None:
    sentences = [
        f"Alpha sentence {i} provides retrieval context for NotebookLM systems."
        for i in range(1, 20)
    ]
    pages = [CleanedPage(page_number=1, text=" ".join(sentences))]
    chunks = run_chunking(pages, max_chars=180, sentence_overlap=1)
    assert len(chunks) >= 2
    # With sentence_overlap=1, consecutive chunks should share at least one sentence.
    shared = False
    for left, right in zip(chunks, chunks[1:], strict=False):
        left_parts = left.content.split(". ")
        if left_parts[-1].rstrip(".") in right.content:
            shared = True
            break
    assert shared


def test_giant_sentence_falls_back_to_fixed_window() -> None:
    giant = "Word " * 800  # no sentence boundary
    pages = [CleanedPage(page_number=3, text=giant.strip())]
    chunks = run_chunking(pages, max_chars=100, overlap_chars=20)
    assert len(chunks) > 1
    assert all(len(c.content) <= 100 for c in chunks)


def test_offsets_are_monotonic_across_chunks() -> None:
    pages = [
        CleanedPage(page_number=1, text="First page paragraph about policies.\n\nMore text here."),
        CleanedPage(page_number=2, text="Second page continues the discussion with details."),
    ]
    chunks = run_chunking(pages, max_chars=80, sentence_overlap=0)
    assert chunks
    for i in range(1, len(chunks)):
        assert chunks[i].start_offset >= chunks[i - 1].start_offset


def test_empty_pages_return_empty_list() -> None:
    assert run_chunking([]) == []
    assert run_chunking([CleanedPage(page_number=1, text="   ")]) == []
