# =============================================================================
# File: text.py
# Module/Service: Citation Verification Layer (FR5)
# Layer: Service
# Purpose: Deterministic evidence-text normalization and sub-span matching.
# Responsibilities:
#   - normalize_evidence_text() — safe whitespace/Unicode/case folding
#   - snippet_in_source() — exact and sub-span containment after normalize
# Dependencies:
#   - unicodedata, re (stdlib only)
# Public Exports:
#   - normalize_evidence_text, snippet_in_source
# Database/Table: N/A
# Related Modules: citation_verification.service
# Important Notes:
#   - Deterministic verification. No LLM call.
#   - Must validate workspace/message/retrieval membership (caller).
#   - Do not stem, paraphrase, drop punctuation, or call embeddings.
# =============================================================================

from __future__ import annotations

import re
import unicodedata

# Collapse any Unicode whitespace (spaces, tabs, newlines, NBSP, OCR breaks).
_WHITESPACE = re.compile(r"\s+", re.UNICODE)
# "word ," / "word ." → "word," — OCR/punctuation spacing only.
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?])")
# "( word" / "[ word" → "(word"
_SPACE_AFTER_OPEN = re.compile(r"([(\[])\s+")


def normalize_evidence_text(text: str) -> str:
    """Normalize evidence text for deterministic containment checks.

    Applies NFC Unicode, whitespace collapsing (including line breaks / tabs),
    light punctuation-spacing cleanup, strip, and casefold. Does **not**
    remove punctuation, stem, or paraphrase.
    """
    value = unicodedata.normalize("NFC", text or "")
    value = value.replace("\u00a0", " ").replace("\u200b", "")
    value = _WHITESPACE.sub(" ", value)
    value = _SPACE_BEFORE_PUNCT.sub(r"\1", value)
    value = _SPACE_AFTER_OPEN.sub(r"\1", value)
    return value.strip().casefold()


def snippet_in_source(*, snippet: str, source: str) -> bool:
    """Return True when ``snippet`` is the source or a contiguous sub-span.

    Matching is performed on normalized forms so whitespace / Unicode / case
    differences do not produce false negatives.
    """
    needle = normalize_evidence_text(snippet)
    haystack = normalize_evidence_text(source)
    if not needle or not haystack:
        return False
    return needle in haystack
