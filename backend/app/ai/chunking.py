# =============================================================================
# File: chunking.py
# Module/Service: Pipeline Worker — Chunking ([AI])
# Layer: Service
# Purpose: Structure-aware document chunking for Hybrid Retrieval / LightRAG (FR2).
# Responsibilities:
#   - Heading → Paragraph → Sentence → Adaptive packing (no naive fixed windows)
#   - Preserve page/section/heading/offsets for citation, highlight, re-ranking
# Dependencies:
#   - app.ai.ocr.CleanedPage (stdlib only — no LangChain/LlamaIndex/spaCy/NLTK)
# Public Exports:
#   - TextChunk, run_chunking, estimate_tokens
# Database/Table: document_chunks (persisted by worker; version_id attached later)
# Related Modules: app.workers.pipeline (stage_chunking), graph/topic extraction
# Important Notes:
#   - Do not store document_id; document_version_id is bound in the pipeline.
#   - Semantic overlap uses trailing sentences; char overlap only on long-sentence fallback.
# =============================================================================

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.ai.ocr import CleanedPage

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TextChunk:
    """One retrieval-ready chunk with structure metadata and character offsets.

    Attributes:
        chunk_index: Zero-based order within the version pipeline run.
        content: Chunk text (never mid-sentence unless fixed-window fallback).
        page_number: Primary page for display / highlight (first page covered).
        section: Coarse section label from OCR when available.
        heading: Nearest heading that scopes this chunk.
        paragraph_index: First source paragraph index included in the chunk.
        start_offset: Inclusive char offset in the concatenated document text.
        end_offset: Exclusive char offset in the concatenated document text.
        token_count: Lightweight token estimate (replaceable via ``estimate_tokens``).
        metadata: Citation/highlight helpers ``{page, heading, section, paragraph}``.
    """

    chunk_index: int
    content: str
    page_number: int | None
    section: str | None
    heading: str | None
    paragraph_index: int | None
    start_offset: int
    end_offset: int
    token_count: int
    metadata: dict[str, Any]


# ---------------------------------------------------------------------------
# Token estimation (swap for tiktoken later without touching packing logic)
# ---------------------------------------------------------------------------


def estimate_tokens(text: str) -> int:
    """Estimate token count (tiktoken when installed, else char heuristic).

    Delegates to ``app.ai.tokens.count_tokens`` so chunking and embedding share
    one tokenizer policy.

    Args:
        text: Input string.

    Returns:
        Token count (0 for empty text).
    """
    from app.ai.tokens import count_tokens

    return count_tokens(text)


# Keep private alias used historically inside this module / tests.
_estimate_tokens = estimate_tokens


# ---------------------------------------------------------------------------
# Internal structural units
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Paragraph:
    """A paragraph (or heading line) located in the concatenated document."""

    text: str
    page_number: int | None
    section: str | None
    heading: str | None
    paragraph_index: int
    start_offset: int
    end_offset: int
    is_heading: bool


@dataclass(frozen=True, slots=True)
class _Sentence:
    """A sentence span with absolute offsets into the concatenated document."""

    text: str
    start_offset: int
    end_offset: int


# Sentence boundary: punctuation + whitespace + start of next sentence.
_SENTENCE_SPLIT_RE = re.compile(
    r"(?<=[.!?…])\s+(?=[\"'“‘(\[]?[A-ZÀ-Ỹ0-9])",
)
# Soft paragraph break: one or more blank lines.
_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n+")
# Markdown / outline headings.
_MD_HEADING_RE = re.compile(r"^#{1,6}\s+\S")
# Collapse runs of spaces/tabs but keep newlines for structure detection.
_INLINE_WS_RE = re.compile(r"[ \t]+")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_chunking(
    pages: list[CleanedPage],
    *,
    max_chars: int = 1200,
    overlap_chars: int = 150,
    sentence_overlap: int = 1,
    min_merge_chars: int = 200,
) -> list[TextChunk]:
    """Structure-aware chunking: Heading → Paragraph → Sentence → Adaptive.

    Packing rules:
        1. Prefer keeping whole paragraphs under the same heading.
        2. Merge consecutive small paragraphs until ``max_chars``.
        3. Split oversized paragraphs on sentence boundaries.
        4. Overlap by trailing sentences (semantic), not by character count.
        5. Only if a single sentence exceeds ``max_chars``, fall back to a
           fixed character window using ``overlap_chars``.

    Args:
        pages: Cleaned OCR pages (order preserved).
        max_chars: Soft upper bound on chunk character length.
        overlap_chars: Character overlap **only** for the long-sentence fallback.
        sentence_overlap: Number of trailing sentences kept when packing the
            next sentence-based chunk (clamped to ``>= 0``).
        min_merge_chars: Prefer merging a trailing small paragraph when the
            current buffer is below this size (still respecting ``max_chars``).

    Returns:
        Ordered ``TextChunk`` list with offsets relative to the concatenated
        document text (pages joined by ``\\n\\n``). Empty pages are skipped.
    """
    if max_chars < 1:
        raise ValueError("max_chars must be >= 1")
    sentence_overlap = max(0, sentence_overlap)
    overlap_chars = max(0, overlap_chars)

    paragraphs = _extract_paragraphs(pages)
    if not paragraphs:
        return []

    return _adaptive_pack(
        paragraphs,
        max_chars=max_chars,
        overlap_chars=overlap_chars,
        sentence_overlap=sentence_overlap,
        min_merge_chars=min_merge_chars,
    )


# ---------------------------------------------------------------------------
# Structure extraction
# ---------------------------------------------------------------------------


def _extract_paragraphs(pages: list[CleanedPage]) -> list[_Paragraph]:
    """Parse pages into heading/paragraph units with absolute offsets.

    Args:
        pages: OCR cleaned pages.

    Returns:
        Flattened paragraph list in reading order.
    """
    paragraphs: list[_Paragraph] = []
    cursor = 0
    para_index = 0
    active_heading: str | None = None

    for page_i, page in enumerate(pages):
        if page_i > 0:
            cursor += 2  # account for the ``\n\n`` joiner between pages

        raw = (page.text or "").replace("\r\n", "\n").replace("\r", "\n")
        raw = _INLINE_WS_RE.sub(" ", raw)
        if not raw.strip():
            cursor += len(raw)
            continue

        # Prefer OCR-provided section as the initial heading for the page.
        if page.section:
            active_heading = page.section.strip() or active_heading

        blocks = _split_paragraph_blocks(raw)
        search_from = 0
        for block in blocks:
            local_start = raw.find(block, search_from)
            if local_start < 0:
                local_start = search_from
            local_end = local_start + len(block)
            search_from = local_end

            text = block.strip()
            if not text:
                continue

            abs_start = cursor + local_start
            abs_end = cursor + local_end
            is_heading = _looks_like_heading(text)
            if is_heading:
                active_heading = _normalize_heading(text)

            paragraphs.append(
                _Paragraph(
                    text=text,
                    page_number=page.page_number,
                    section=page.section,
                    heading=active_heading,
                    paragraph_index=para_index,
                    start_offset=abs_start,
                    end_offset=abs_end,
                    is_heading=is_heading,
                )
            )
            para_index += 1

        cursor += len(raw)

    return paragraphs


def _split_paragraph_blocks(text: str) -> list[str]:
    """Split page text into paragraph-sized blocks.

    Blank-line separated blocks are preferred. Single newlines are kept inside
    a block so short list items stay together until sentence packing.

    Args:
        text: Page text.

    Returns:
        Non-empty block strings (may still need ``strip``).
    """
    if not text.strip():
        return []
    parts = _PARAGRAPH_SPLIT_RE.split(text)
    return [p for p in parts if p.strip()]


def _looks_like_heading(text: str) -> bool:
    """Heuristic heading detector (Markdown, ALL-CAPS, title-case lines).

    Args:
        text: Candidate paragraph.

    Returns:
        True when the line is likely a structural heading.
    """
    line = text.strip()
    if not line or "\n" in line:
        return False
    if len(line) > 120:
        return False
    if _MD_HEADING_RE.match(line):
        return True

    words = line.split()
    if not words or len(words) > 12:
        return False

    if line.isupper() and len(words) >= 2:
        return True

    # Title-like: no terminal sentence punctuation, mostly capitalized words.
    if line.endswith((".", "!", "?", ",", ";", ":")):
        return False
    if len(line) > 80:
        return False

    capitalised = sum(1 for w in words if w[:1].isupper())
    return capitalised >= max(1, len(words) - 1) and len(words) <= 10


def _normalize_heading(text: str) -> str:
    """Strip Markdown markers from a heading line."""
    return re.sub(r"^#{1,6}\s*", "", text.strip()).strip() or text.strip()


# ---------------------------------------------------------------------------
# Sentence splitting
# ---------------------------------------------------------------------------


def _split_sentences(paragraph: _Paragraph) -> list[_Sentence]:
    """Split a paragraph into sentences with absolute offsets.

    Args:
        paragraph: Source paragraph.

    Returns:
        Sentence list covering ``paragraph.text`` (fallback: one sentence).
    """
    text = paragraph.text
    if not text:
        return []

    parts = _SENTENCE_SPLIT_RE.split(text)
    if len(parts) <= 1:
        return [
            _Sentence(
                text=text,
                start_offset=paragraph.start_offset,
                end_offset=paragraph.end_offset,
            )
        ]

    sentences: list[_Sentence] = []
    search_from = 0
    for part in parts:
        piece = part.strip()
        if not piece:
            continue
        rel = text.find(piece, search_from)
        if rel < 0:
            rel = search_from
        abs_start = paragraph.start_offset + rel
        abs_end = abs_start + len(piece)
        sentences.append(_Sentence(text=piece, start_offset=abs_start, end_offset=abs_end))
        search_from = rel + len(piece)
    return sentences or [
        _Sentence(
            text=text,
            start_offset=paragraph.start_offset,
            end_offset=paragraph.end_offset,
        )
    ]


# ---------------------------------------------------------------------------
# Adaptive packing
# ---------------------------------------------------------------------------


def _adaptive_pack(
    paragraphs: list[_Paragraph],
    *,
    max_chars: int,
    overlap_chars: int,
    sentence_overlap: int,
    min_merge_chars: int,
) -> list[TextChunk]:
    """Pack paragraphs into structure-aware chunks.

    Args:
        paragraphs: Extracted structural units.
        max_chars: Soft character budget per chunk.
        overlap_chars: Fixed-window overlap for oversize sentences.
        sentence_overlap: Trailing sentences reused across sentence packs.
        min_merge_chars: Merge threshold for undersized buffers.

    Returns:
        Final ``TextChunk`` list.
    """
    chunks: list[TextChunk] = []
    buffer: list[_Paragraph] = []

    def flush_buffer() -> None:
        nonlocal buffer
        if not buffer:
            return
        chunks.extend(
            _pack_paragraph_group(
                buffer,
                start_index=len(chunks),
                max_chars=max_chars,
                overlap_chars=overlap_chars,
                sentence_overlap=sentence_overlap,
            )
        )
        buffer = []

    for para in paragraphs:
        # Headings are metadata anchors: attach to following content, not alone.
        if para.is_heading:
            if buffer and _buffer_chars(buffer) >= min_merge_chars:
                flush_buffer()
            # Do not emit heading-only chunks; update context via heading field
            # on subsequent paragraphs (already set during extraction).
            continue

        if not buffer:
            buffer.append(para)
            continue

        same_heading = buffer[-1].heading == para.heading
        projected = _buffer_chars(buffer) + 1 + len(para.text)  # +1 for join space/newline

        if same_heading and projected <= max_chars:
            buffer.append(para)
            continue

        # Different heading or would exceed budget → flush, then start new.
        if (
            _buffer_chars(buffer) < min_merge_chars
            and same_heading
            and projected <= max_chars * 1.1
        ):
            # Allow a soft overrun to avoid tiny leftover chunks.
            buffer.append(para)
            flush_buffer()
            continue

        flush_buffer()
        buffer.append(para)

    flush_buffer()
    # Re-number sequentially (sentence packs may emit multiple chunks).
    return [
        TextChunk(
            chunk_index=i,
            content=c.content,
            page_number=c.page_number,
            section=c.section,
            heading=c.heading,
            paragraph_index=c.paragraph_index,
            start_offset=c.start_offset,
            end_offset=c.end_offset,
            token_count=c.token_count,
            metadata=c.metadata,
        )
        for i, c in enumerate(chunks)
    ]


def _buffer_chars(buffer: list[_Paragraph]) -> int:
    """Total characters in a paragraph buffer including single-space joins."""
    if not buffer:
        return 0
    return sum(len(p.text) for p in buffer) + max(0, len(buffer) - 1)


def _pack_paragraph_group(
    group: list[_Paragraph],
    *,
    start_index: int,
    max_chars: int,
    overlap_chars: int,
    sentence_overlap: int,
) -> list[TextChunk]:
    """Emit one or more chunks from a coherent paragraph group.

    Args:
        group: Paragraphs sharing a packing decision.
        start_index: Next chunk_index to assign (temporary; renumbered later).
        max_chars: Character budget.
        overlap_chars: Fallback window overlap.
        sentence_overlap: Semantic sentence overlap.

    Returns:
        One or more ``TextChunk`` instances.
    """
    total = _buffer_chars(group)
    if total <= max_chars:
        return [_build_chunk_from_paragraphs(group, chunk_index=start_index)]

    # Oversized group → sentence-level packing across the group.
    sentences: list[_Sentence] = []
    for para in group:
        sentences.extend(_split_sentences(para))

    return _pack_sentences(
        sentences,
        template=group[0],
        start_index=start_index,
        max_chars=max_chars,
        overlap_chars=overlap_chars,
        sentence_overlap=sentence_overlap,
    )


def _pack_sentences(
    sentences: list[_Sentence],
    *,
    template: _Paragraph,
    start_index: int,
    max_chars: int,
    overlap_chars: int,
    sentence_overlap: int,
) -> list[TextChunk]:
    """Pack sentences into chunks with semantic overlap.

    Args:
        sentences: Ordered sentences.
        template: Paragraph providing heading/section/page metadata.
        start_index: Starting chunk index.
        max_chars: Character budget.
        overlap_chars: Fixed-window overlap for giant sentences.
        sentence_overlap: Trailing sentences carried into the next chunk.

    Returns:
        Chunk list covering all sentences.
    """
    if not sentences:
        return []

    out: list[TextChunk] = []
    i = 0
    chunk_i = start_index

    while i < len(sentences):
        # Single sentence longer than budget → fixed-window fallback.
        if len(sentences[i].text) > max_chars:
            out.extend(
                _fixed_window_chunks(
                    sentences[i],
                    template=template,
                    start_index=chunk_i,
                    max_chars=max_chars,
                    overlap_chars=overlap_chars,
                )
            )
            chunk_i = start_index + len(out)
            i += 1
            continue

        window: list[_Sentence] = []
        size = 0
        j = i
        while j < len(sentences):
            piece = sentences[j]
            add = len(piece.text) if not window else len(piece.text) + 1
            if window and size + add > max_chars:
                break
            if not window and len(piece.text) > max_chars:
                break
            window.append(piece)
            size += add
            j += 1

        if not window:
            # Safety: should not happen, but avoid infinite loop.
            out.extend(
                _fixed_window_chunks(
                    sentences[i],
                    template=template,
                    start_index=chunk_i,
                    max_chars=max_chars,
                    overlap_chars=overlap_chars,
                )
            )
            chunk_i = start_index + len(out)
            i += 1
            continue

        out.append(_build_chunk_from_sentences(window, template=template, chunk_index=chunk_i))
        chunk_i += 1

        if j >= len(sentences):
            break
        # Semantic overlap: keep last N sentences for the next window start.
        step = max(1, len(window) - sentence_overlap)
        i += step

    return out


def _fixed_window_chunks(
    sentence: _Sentence,
    *,
    template: _Paragraph,
    start_index: int,
    max_chars: int,
    overlap_chars: int,
) -> list[TextChunk]:
    """Last-resort character windows for a single oversize sentence.

    Args:
        sentence: Oversize sentence.
        template: Metadata source.
        start_index: First chunk index.
        max_chars: Window size.
        overlap_chars: Character overlap between windows.

    Returns:
        Fixed-window chunks covering the sentence text.
    """
    text = sentence.text
    chunks: list[TextChunk] = []
    start = 0
    idx = start_index
    step = max(1, max_chars - overlap_chars)

    while start < len(text):
        end = min(len(text), start + max_chars)
        piece = text[start:end].strip()
        if piece:
            abs_start = sentence.start_offset + start
            abs_end = sentence.start_offset + end
            chunks.append(
                _make_chunk(
                    chunk_index=idx,
                    content=piece,
                    page_number=template.page_number,
                    section=template.section,
                    heading=template.heading,
                    paragraph_index=template.paragraph_index,
                    start_offset=abs_start,
                    end_offset=abs_end,
                )
            )
            idx += 1
        if end >= len(text):
            break
        start += step
    return chunks


# ---------------------------------------------------------------------------
# Chunk builders
# ---------------------------------------------------------------------------


def _build_chunk_from_paragraphs(group: list[_Paragraph], *, chunk_index: int) -> TextChunk:
    """Join whole paragraphs into a single chunk."""
    content = "\n\n".join(p.text for p in group)
    first, last = group[0], group[-1]
    return _make_chunk(
        chunk_index=chunk_index,
        content=content,
        page_number=first.page_number,
        section=first.section,
        heading=first.heading,
        paragraph_index=first.paragraph_index,
        start_offset=first.start_offset,
        end_offset=last.end_offset,
    )


def _build_chunk_from_sentences(
    sentences: list[_Sentence],
    *,
    template: _Paragraph,
    chunk_index: int,
) -> TextChunk:
    """Join sentences into a single chunk."""
    content = " ".join(s.text for s in sentences)
    return _make_chunk(
        chunk_index=chunk_index,
        content=content,
        page_number=template.page_number,
        section=template.section,
        heading=template.heading,
        paragraph_index=template.paragraph_index,
        start_offset=sentences[0].start_offset,
        end_offset=sentences[-1].end_offset,
    )


def _make_chunk(
    *,
    chunk_index: int,
    content: str,
    page_number: int | None,
    section: str | None,
    heading: str | None,
    paragraph_index: int | None,
    start_offset: int,
    end_offset: int,
) -> TextChunk:
    """Construct a ``TextChunk`` with normalized metadata."""
    meta = {
        "page": page_number,
        "heading": heading,
        "section": section,
        "paragraph": paragraph_index,
    }
    return TextChunk(
        chunk_index=chunk_index,
        content=content,
        page_number=page_number,
        section=section,
        heading=heading,
        paragraph_index=paragraph_index,
        start_offset=start_offset,
        end_offset=end_offset,
        token_count=estimate_tokens(content),
        metadata=meta,
    )


# ---------------------------------------------------------------------------
# Segment-based API (OCR Step 3 → Chunking Step 4)
# ---------------------------------------------------------------------------


def run_chunking_from_segments(
    segments: list[Any],
    *,
    max_tokens: int = 512,
    overlap_ratio: float = 0.12,
) -> list[TextChunk]:
    """Chunk OCR segments while preserving section/page boundaries.

    Strategy:
        1. Never merge segments across different ``section`` values
           (heading / sheet / slide boundaries from OCR).
        2. Within a section, pack consecutive segments until ``max_tokens``.
        3. Oversized segments are split with token overlap (``overlap_ratio``).

    Args:
        segments: ``OcrSegment`` instances or dicts with keys
            ``text``, ``page_number``, ``section``, ``order_index``.
        max_tokens: Soft token budget per chunk.
        overlap_ratio: Token overlap between windows of a split segment (0.10–0.15).

    Returns:
        Ordered ``TextChunk`` list ready for ``document_chunks`` persistence.
    """
    from app.ai.tokens import count_tokens, split_text_by_tokens

    normalized = [_normalize_segment(s) for s in segments]
    normalized = [s for s in normalized if s["text"].strip()]
    if not normalized:
        return []

    chunks: list[TextChunk] = []
    buffer: list[dict[str, Any]] = []

    def flush() -> None:
        nonlocal buffer
        if not buffer:
            return
        content = "\n\n".join(s["text"] for s in buffer)
        first = buffer[0]
        chunks.append(
            _make_chunk(
                chunk_index=len(chunks),
                content=content,
                page_number=first["page_number"],
                section=first["section"],
                heading=first["section"],
                paragraph_index=first["order_index"],
                start_offset=0,
                end_offset=len(content),
            )
        )
        buffer = []

    for seg in normalized:
        tok = count_tokens(seg["text"])
        if tok > max_tokens:
            flush()
            for piece in split_text_by_tokens(
                seg["text"],
                max_tokens=max_tokens,
                overlap_ratio=overlap_ratio,
            ):
                chunks.append(
                    _make_chunk(
                        chunk_index=len(chunks),
                        content=piece,
                        page_number=seg["page_number"],
                        section=seg["section"],
                        heading=seg["section"],
                        paragraph_index=seg["order_index"],
                        start_offset=0,
                        end_offset=len(piece),
                    )
                )
            continue

        if not buffer:
            buffer.append(seg)
            continue

        same_section = buffer[-1]["section"] == seg["section"]
        projected = count_tokens("\n\n".join(s["text"] for s in buffer) + "\n\n" + seg["text"])
        if same_section and projected <= max_tokens:
            buffer.append(seg)
        else:
            flush()
            buffer.append(seg)

    flush()
    return [
        TextChunk(
            chunk_index=i,
            content=c.content,
            page_number=c.page_number,
            section=c.section,
            heading=c.heading,
            paragraph_index=c.paragraph_index,
            start_offset=c.start_offset,
            end_offset=c.end_offset,
            token_count=c.token_count,
            metadata=c.metadata,
        )
        for i, c in enumerate(chunks)
    ]


def _normalize_segment(segment: Any) -> dict[str, Any]:
    """Accept OcrSegment dataclass or artifact dict."""
    if isinstance(segment, dict):
        return {
            "text": str(segment.get("text") or "").strip(),
            "page_number": segment.get("page_number"),
            "section": segment.get("section"),
            "order_index": int(segment.get("order_index") or 0),
        }
    return {
        "text": str(getattr(segment, "text", "") or "").strip(),
        "page_number": getattr(segment, "page_number", None),
        "section": getattr(segment, "section", None),
        "order_index": int(getattr(segment, "order_index", 0) or 0),
    }
