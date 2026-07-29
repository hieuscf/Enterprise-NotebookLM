# =============================================================================
# File: token_window.py
# Module/Service: Pipeline Worker — Hierarchical Chunking ([AI])
# Layer: Service
# Purpose: Token counting helpers for chunk packing (no character splitting).
# Responsibilities:
#   - Count tokens, extract tail overlap windows by token count
# Dependencies:
#   - app.ai.tokens.count_tokens
# Public Exports:
#   - token_count, tail_token_text, join_units
# Database/Table: N/A
# Related Modules: app.ai.hierarchical_chunking.unit_packer
# Important Notes: Overlap uses token boundaries, never raw character offsets.
# =============================================================================

from __future__ import annotations

from app.ai.tokens import count_tokens


def token_count(text: str) -> int:
    """Return token count for ``text`` (0 for empty)."""
    return count_tokens(text)


def join_units(units: list[str], *, separator: str = "\n\n") -> str:
    """Join block units without redundant whitespace."""
    return separator.join(part.strip() for part in units if part and part.strip())


def tail_token_text(text: str, overlap_tokens: int) -> str:
    """Return the trailing ``overlap_tokens`` of ``text`` as a decoded string."""
    if overlap_tokens <= 0 or not text.strip():
        return ""
    enc = _encoding()
    if enc is not None:
        token_ids = enc.encode(text)
        if len(token_ids) <= overlap_tokens:
            return text.strip()
        return enc.decode(token_ids[-overlap_tokens:]).strip()
    overlap_chars = overlap_tokens * 4
    if len(text) <= overlap_chars:
        return text.strip()
    return text[-overlap_chars:].strip()


def _encoding():  # noqa: ANN202
    from app.ai.tokens import _tiktoken_encoding

    return _tiktoken_encoding()
