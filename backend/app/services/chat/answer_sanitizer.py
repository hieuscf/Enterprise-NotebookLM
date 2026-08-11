# =============================================================================
# File: answer_sanitizer.py
# Module/Service: Chat Service / Citation Verification (FR4, FR5)
# Layer: Service
# Purpose: Keep answer prose free of internal citation/chunk UUIDs.
# Responsibilities:
#   - Rewrite [chunk-uuid] markers to presentation indexes [1], [2], …
#   - Strip unrecognized bracketed UUIDs from answer text
# Dependencies:
#   - N/A (pure string helpers)
# Public Exports:
#   - rewrite_inline_citation_markers
# Database/Table: N/A (operates on in-memory answer before persist/stream)
# Related Modules: answer_generator, message_service
# Important Notes:
#   - citation_ids remain metadata; only presentation indexes may appear in prose.
#   - Does not change retrieval, verification, or LLM call count.
# =============================================================================

from __future__ import annotations

import re
from collections.abc import Sequence

# Bracketed UUID as commonly emitted by the LLM next to claims.
_BRACKETED_UUID = re.compile(
    r"\[\s*([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\s*\]"
)
# Collapse whitespace left by removals: "word  ." / "word ."
_SPACE_BEFORE_PUNCT = re.compile(r"[ \t]+([.,;:!?])")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")


def rewrite_inline_citation_markers(
    answer: str,
    chunk_ids_in_order: Sequence[str],
) -> str:
    """Replace ``[chunk-uuid]`` with ``[n]``; drop unknown bracketed UUIDs.

    ``chunk_ids_in_order`` must match the verified citation order that will be
    persisted (order_index 0 → display ``[1]``).
    """
    text = (answer or "").strip()
    if not text:
        return ""

    index_by_id = {
        str(cid).strip().lower(): i + 1
        for i, cid in enumerate(chunk_ids_in_order)
        if str(cid).strip()
    }

    def _replace(match: re.Match[str]) -> str:
        cid = match.group(1).lower()
        idx = index_by_id.get(cid)
        return f"[{idx}]" if idx is not None else ""

    rewritten = _BRACKETED_UUID.sub(_replace, text)
    rewritten = _SPACE_BEFORE_PUNCT.sub(r"\1", rewritten)
    rewritten = _MULTI_SPACE.sub(" ", rewritten)
    # Trim spaces left at line ends after UUID removal.
    rewritten = "\n".join(line.rstrip() for line in rewritten.splitlines())
    return rewritten.strip()
