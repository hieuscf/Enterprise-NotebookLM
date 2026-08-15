# =============================================================================
# File: source_validator.py
# Module/Service: Citation Verification Layer — Source Reference Validator
# Layer: Service
# Purpose: Generic deterministic checks for document/version/chunk/page/span.
# Responsibilities:
#   - Workspace, document, version, page, and character-span integrity
#   - Quote containment against canonical original text
# Dependencies:
#   - citation_verification.text (normalize / snippet_in_source)
# Public Exports:
#   - span_is_valid, page_matches, ids_match, quote_in_source, slice_text
# Database/Table: N/A
# Related Modules: Chat CitationVerificationService; ComparisonCitationVerifier
# Important Notes:
#   - Offsets are Python character indexes, not UTF-8 bytes.
#   - No LLM. No retrieval. Does not decide OLD/NEW or absence.
# =============================================================================

from __future__ import annotations

from uuid import UUID

from app.services.citation_verification.text import snippet_in_source


def ids_match(expected: UUID | None, actual: UUID | None) -> bool:
    """True when either side is unknown or both identities are equal."""
    if expected is None or actual is None:
        return True
    return expected == actual


def page_matches(claimed: int | None, canonical: int | None) -> bool:
    """True when page is optional or both numbers agree. Never infers page."""
    if claimed is None or canonical is None:
        return True
    return claimed == canonical


def span_is_valid(
    start: int | None,
    end: int | None,
    text_length: int | None,
) -> tuple[bool, str | None]:
    """Validate character offsets. Returns (ok, reason_code or None)."""
    if start is None or end is None:
        return False, "SPAN_INVALID"
    if start < 0 or end < start:
        return False, "SPAN_INVALID"
    if text_length is not None and end > text_length:
        return False, "SPAN_OUT_OF_RANGE"
    return True, None


def slice_text(text: str | None, start: int | None, end: int | None) -> str | None:
    """Return text[start:end] when the character span is in range; else None."""
    if text is None or start is None or end is None:
        return None
    if start < 0 or end < start or end > len(text):
        return None
    return text[start:end]


def quote_in_source(*, quote: str | None, source: str | None) -> bool:
    """True when quote is empty/unknown or a contiguous sub-span of source."""
    if not quote:
        return True
    if source is None:
        return False
    if quote in source:
        return True
    return snippet_in_source(snippet=quote, source=source)
