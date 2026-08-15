# =============================================================================
# File: mapping_similarity.py
# Module/Service: Clause Identity & Mapping (FR8 / TASK-CMP-03)
# Layer: Service
# Purpose: Deterministic title/lexical/vector similarity for mapping candidates.
# Responsibilities:
#   - Token Jaccard (same Unicode token class as retrieval reranker heuristic)
#   - Title equality after CMP-02 normalization
#   - Optional cosine on caller-supplied embeddings
# Dependencies:
#   - stdlib math / re / difflib
# Public Exports:
#   - lexical_similarity, title_similarity, cosine_similarity, last_number_part
# Database/Table: N/A
# Related Modules: mapping_engine; app.services.retrieval.reranker (token class)
# Important Notes:
#   - Does not call Elasticsearch BM25 (that API is query/workspace retrieval).
#   - Does not call LLM. Derived scores only — originals are never rewritten.
# =============================================================================

from __future__ import annotations

import math
import re
from difflib import SequenceMatcher

# Matches app.services.retrieval.reranker._TOKEN_RE (Vietnamese-aware tokens).
_TOKEN_RE = re.compile(
    r"[a-z0-9àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]+",
    re.I,
)


def tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").casefold()))


def lexical_similarity(left: str, right: str) -> float:
    """Jaccard overlap of Unicode word tokens (in-memory lexical score)."""
    left_tokens = tokenize(left)
    right_tokens = tokenize(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def title_similarity(left: str, right: str) -> float:
    """1.0 on exact normalized titles; else token Jaccard / SequenceMatcher."""
    a = (left or "").strip()
    b = (right or "").strip()
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    jaccard = lexical_similarity(a, b)
    ratio = SequenceMatcher(None, a, b).ratio()
    return max(jaccard, ratio)


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for x, y in zip(left, right, strict=True):
        dot += x * y
        left_norm += x * x
        right_norm += y * y
    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / math.sqrt(left_norm * right_norm)))


def last_number_part(number: str | None) -> str | None:
    if not number:
        return None
    return number.rsplit(".", 1)[-1]
