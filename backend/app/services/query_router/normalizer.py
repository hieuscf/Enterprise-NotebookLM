# =============================================================================
# File: normalizer.py
# Module/Service: Query Router — Query Classifier (FR11)
# Layer: Service
# Purpose: Canonical query text normalization for classification and hashing.
# Responsibilities:
#   - Lowercase, Unicode NFKC, trim, collapse whitespace, strip punctuation
# Dependencies:
#   - stdlib unicodedata / re
# Public Exports:
#   - normalize_query
# Database/Table: N/A
# Related Modules: app.services.query_router.rule_classifier, cache
# Important Notes: Classifier must never inline normalize — always call here.
# =============================================================================

from __future__ import annotations

import re
import unicodedata

# Keep letters/numbers/spaces (Unicode-aware); drop punctuation / symbols.
_PUNCT_RE = re.compile(r"[^\w\s]+", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")
# Possessive / curly apostrophe before punctuation strip (Apple's → apple).
_APOSTROPHE_S_RE = re.compile(r"[''′]s\b", re.IGNORECASE | re.UNICODE)
_APOSTROPHE_RE = re.compile(r"[''′]", re.UNICODE)


def normalize_query(query_text: str) -> str:
    """Normalize raw query text for rule matching and embedding.

    Steps (in order):
      1. Unicode NFKC normalize
      2. Lowercase
      3. Trim leading/trailing whitespace
      4. Drop possessives / apostrophes (``Apple's`` → ``apple``)
      5. Remove basic punctuation / symbols
      6. Collapse multiple spaces

    Args:
        query_text: Raw user query (may be empty / None-like).

    Returns:
        Normalized string. Empty input yields ``""``.

    Examples:
        >>> normalize_query("What is Apple's CEO?")
        'what is apple ceo'
    """
    text = unicodedata.normalize("NFKC", query_text or "")
    text = text.lower().strip()
    text = _APOSTROPHE_S_RE.sub(" ", text)
    text = _APOSTROPHE_RE.sub(" ", text)
    text = _PUNCT_RE.sub(" ", text)
    text = _SPACE_RE.sub(" ", text).strip()
    return text
