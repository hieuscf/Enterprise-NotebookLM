# =============================================================================
# File: tokens.py
# Module/Service: Pipeline Worker — Chunking / Embedding ([AI])
# Layer: Service
# Purpose: Token count + window split with optional tiktoken (FR2 Step 4).
# Responsibilities:
#   - count_tokens / split_text_by_tokens with overlap_ratio (10–15%)
#   - Prefer tiktoken (cl100k_base); fall back to ~4 chars/token estimator
# Dependencies:
#   - tiktoken (optional); stdlib fallback
# Public Exports:
#   - count_tokens, split_text_by_tokens, get_token_encoding_name
# Database/Table: N/A
# Related Modules: app.ai.chunking, app.ai.hierarchical_chunking
# Important Notes: Embedding model tokenizers may differ; cl100k_base is default.
# =============================================================================

from __future__ import annotations

from functools import lru_cache

_CHARS_PER_TOKEN = 4


@lru_cache(maxsize=1)
def _tiktoken_encoding():  # noqa: ANN202
    try:
        import tiktoken

        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None


def get_token_encoding_name() -> str:
    """Return active tokenizer id for metadata / observability."""
    return "cl100k_base" if _tiktoken_encoding() is not None else "char_approx_v1"


def count_tokens(text: str) -> int:
    """Count tokens using tiktoken when available, else char heuristic."""
    if not text:
        return 0
    enc = _tiktoken_encoding()
    if enc is not None:
        return len(enc.encode(text))
    return max(1, len(text) // _CHARS_PER_TOKEN)


def split_text_by_tokens(
    text: str,
    *,
    max_tokens: int,
    overlap_ratio: float = 0.12,
) -> list[str]:
    """Split ``text`` into windows of at most ``max_tokens`` with token overlap.

    Args:
        text: Source string (already structure-bounded by the caller).
        max_tokens: Soft upper bound per window (>= 1).
        overlap_ratio: Fraction of ``max_tokens`` kept as overlap (0–0.5).

    Returns:
        Non-empty text windows in order. Overlap is by tokens, not characters.
    """
    if max_tokens < 1:
        raise ValueError("max_tokens must be >= 1")
    overlap_ratio = min(max(overlap_ratio, 0.0), 0.5)
    overlap = max(0, int(max_tokens * overlap_ratio))
    step = max(1, max_tokens - overlap)

    text = text.strip()
    if not text:
        return []

    enc = _tiktoken_encoding()
    if enc is not None:
        token_ids = enc.encode(text)
        if len(token_ids) <= max_tokens:
            return [text]
        windows: list[str] = []
        start = 0
        while start < len(token_ids):
            end = min(len(token_ids), start + max_tokens)
            piece = enc.decode(token_ids[start:end]).strip()
            if piece:
                windows.append(piece)
            if end >= len(token_ids):
                break
            start += step
        return windows

    # Char fallback approximating tokens.
    max_chars = max_tokens * _CHARS_PER_TOKEN
    overlap_chars = overlap * _CHARS_PER_TOKEN
    step_chars = max(1, max_chars - overlap_chars)
    if len(text) <= max_chars:
        return [text]
    windows = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        piece = text[start:end].strip()
        if piece:
            windows.append(piece)
        if end >= len(text):
            break
        start += step_chars
    return windows
