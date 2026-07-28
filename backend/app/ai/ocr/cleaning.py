# =============================================================================
# File: cleaning.py
# Module/Service: Pipeline Worker — Document Parsing & Cleaning ([AI])
# Layer: Service
# Purpose: Unicode / punctuation normalization and paragraph / block typing.
# Responsibilities:
#   - Clean text (NFKC, zero-width, quotes, dashes, bullets, whitespace)
#   - Split hard paragraphs; infer list/caption/heading block types
# Dependencies:
#   - app.ai.ocr.constants, app.ai.ocr.heading
# Public Exports:
#   - _clean_text, _normalize_bullets, _split_paragraphs, _infer_block_type
# Database/Table: N/A
# Related Modules: app.ai.ocr.*
# Important Notes: No LLM; applied after format parsers emit blocks.
# =============================================================================

from __future__ import annotations

import re
import unicodedata

from .constants import (
    BULLET_CHARS,
    DASH_TRANSLATION,
    QUOTE_TRANSLATION,
    ZERO_WIDTH_CHARS,
    BlockType,
    _BLANK_RE,
    _CAPTION_RE,
    _CTRL_RE,
    _LIST_ITEM_RE,
    _WS_RE,
)
from .heading import _looks_like_heading_text


def _clean_text(text: str) -> str:
    """Normalize encoding, punctuation, and whitespace for RAG-friendly text."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    for ch in ZERO_WIDTH_CHARS:
        if ch in text:
            text = text.replace(ch, "")
    text = text.replace("\u00a0", " ")
    text = text.translate(QUOTE_TRANSLATION)
    text = text.translate(DASH_TRANSLATION)
    text = _normalize_bullets(text)
    text = _CTRL_RE.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WS_RE.sub(" ", text)
    text = _BLANK_RE.sub("\n\n", text)
    return text.strip()


def _normalize_bullets(text: str) -> str:
    """Map decorative bullet glyphs to a single ASCII bullet."""
    if not text:
        return text
    out: list[str] = []
    for line in text.split("\n"):
        stripped = line.lstrip()
        if stripped and stripped[0] in BULLET_CHARS:
            indent = line[: len(line) - len(stripped)]
            rest = stripped[1:].lstrip()
            out.append(f"{indent}* {rest}" if rest else f"{indent}*")
        else:
            out.append(line)
    return "\n".join(out)


def _split_paragraphs(text: str) -> list[str]:
    """Split a block into paragraph-sized pieces (hard breaks only)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []
    return [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]


def _infer_block_type(text: str) -> BlockType:
    if _CAPTION_RE.match(text):
        return "caption"
    if _LIST_ITEM_RE.match(text):
        return "list"
    if _looks_like_heading_text(text):
        return "heading"
    return "paragraph"
