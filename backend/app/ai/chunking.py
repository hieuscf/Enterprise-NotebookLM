# =============================================================================
# File: chunking.py
# Module/Service: Pipeline Worker — Chunking ([AI])
# Layer: Service
# Purpose: Structure-aware chunking with page/section metadata (FR2).
# Responsibilities:
#   - Split cleaned pages into overlapping text chunks; estimate token_count
# Dependencies:
#   - app.ai.ocr.CleanedPage
# Public Exports:
#   - TextChunk, run_chunking
# Database/Table: document_chunks (persisted by worker)
# Related Modules: app.workers.pipeline (stage_chunking)
# Important Notes: Chunks keyed later by document_version_id (not document_id).
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass

from app.ai.ocr import CleanedPage


@dataclass(frozen=True, slots=True)
class TextChunk:
    chunk_index: int
    content: str
    page_number: int | None
    section: str | None
    token_count: int


def _estimate_tokens(text: str) -> int:
    # Lightweight approx (~4 chars/token) — enough for metadata without tiktoken.
    return max(1, len(text) // 4)


def run_chunking(
    pages: list[CleanedPage],
    *,
    max_chars: int = 1200,
    overlap_chars: int = 150,
) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    index = 0
    for page in pages:
        text = page.text.strip()
        if not text:
            continue
        if len(text) <= max_chars:
            chunks.append(
                TextChunk(
                    chunk_index=index,
                    content=text,
                    page_number=page.page_number,
                    section=page.section,
                    token_count=_estimate_tokens(text),
                )
            )
            index += 1
            continue

        start = 0
        while start < len(text):
            end = min(len(text), start + max_chars)
            piece = text[start:end].strip()
            if piece:
                chunks.append(
                    TextChunk(
                        chunk_index=index,
                        content=piece,
                        page_number=page.page_number,
                        section=page.section,
                        token_count=_estimate_tokens(piece),
                    )
                )
                index += 1
            if end >= len(text):
                break
            start = max(0, end - overlap_chars)
    return chunks
