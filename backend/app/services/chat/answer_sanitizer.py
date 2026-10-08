# =============================================================================
# File: answer_sanitizer.py
# Module/Service: Chat Service / Citation Verification (FR4, FR5)
# Layer: Service
# Purpose: Keep answer prose free of internal citation/chunk UUIDs.
# Responsibilities:
#   - Rewrite [chunk-uuid] markers to presentation indexes [1], [2], …
#   - Rewrite known UUID lists to adjacent [n][m] chips; strip unknowns
# Dependencies:
#   - N/A (pure string helpers)
# Public Exports:
#   - rewrite_inline_citation_markers
# Database/Table: N/A (operates on in-memory answer before persist/stream)
# Related Modules: answer_generator, message_service
# Important Notes:
#   - citation_ids remain metadata; only presentation indexes may appear in prose.
#   - Call AFTER Citation Verification so indexes match the verified subset.
#   - Deterministic verification. No LLM call.
#   - Must validate workspace/message/retrieval membership.
# =============================================================================

from __future__ import annotations

import re
from collections.abc import Sequence

_UUID = (
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
# Bracketed UUID as commonly emitted by the LLM next to claims.
_BRACKETED_UUID = re.compile(rf"\[\s*({_UUID})\s*\]")
# LLM dump of citation_ids — comma and/or semicolon separators.
_BRACKETED_UUID_LIST = re.compile(
    rf"\[\s*({_UUID}(?:\s*[,;]\s*{_UUID})+)\s*\]"
)
# Collapse whitespace left by removals: "word  ." / "word ."
_SPACE_BEFORE_PUNCT = re.compile(r"[ \t]+([.,;:!?])")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_MULTI_NEWLINE = re.compile(r"\n{3,}")
_UUID_TOKEN = re.compile(_UUID, re.IGNORECASE)


def rewrite_inline_citation_markers(
    answer: str,
    chunk_ids_in_order: Sequence[str],
) -> str:
    """Replace ``[chunk-uuid]`` with ``[n]``; drop unknown bracketed UUIDs.

    ``chunk_ids_in_order`` must match the verified citation order that will be
    persisted (order_index 0 → display ``[1]``). Bracketed UUID *lists*
    (``[uuid, uuid]`` / ``[uuid; uuid]``) become adjacent ``[n][m]`` when
    known, otherwise they are stripped.
    """
    text = (answer or "").strip()
    if not text:
        return ""

    index_by_id = {
        str(cid).strip().lower(): i + 1
        for i, cid in enumerate(chunk_ids_in_order)
        if str(cid).strip()
    }

    def _rewrite_list(match: re.Match[str]) -> str:
        body = match.group(1)
        indexes: list[int] = []
        seen: set[int] = set()
        for token in _UUID_TOKEN.findall(body):
            idx = index_by_id.get(token.lower())
            if idx is None or idx in seen:
                continue
            seen.add(idx)
            indexes.append(idx)
        if not indexes:
            return ""
        return "".join(f"[{i}]" for i in indexes)

    text = _BRACKETED_UUID_LIST.sub(_rewrite_list, text)

    def _replace(match: re.Match[str]) -> str:
        cid = match.group(1).lower()
        idx = index_by_id.get(cid)
        return f"[{idx}]" if idx is not None else ""

    rewritten = _BRACKETED_UUID.sub(_replace, text)
    rewritten = _SPACE_BEFORE_PUNCT.sub(r"\1", rewritten)
    rewritten = _MULTI_SPACE.sub(" ", rewritten)
    rewritten = _MULTI_NEWLINE.sub("\n\n", rewritten)
    # Trim spaces left at line ends after UUID removal.
    rewritten = "\n".join(line.rstrip() for line in rewritten.splitlines())
    return rewritten.strip()
