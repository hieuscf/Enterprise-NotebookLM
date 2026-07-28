# =============================================================================
# File: paragraphs.py
# Module/Service: Pipeline Worker — Document Parsing & Cleaning ([AI])
# Layer: Service
# Purpose: Soft vs hard line-break detection and paragraph reconstruction.
# Responsibilities:
#   - Decide when visual lines should merge; join soft wraps
#   - Rebuild paragraphs from PDF lines using vertical gaps
# Dependencies:
#   - app.ai.ocr.constants
# Public Exports:
#   - _is_soft_line_break, _join_soft_lines, _reconstruct_paragraphs_from_lines
# Database/Table: N/A
# Related Modules: app.ai.ocr.*
# Important Notes: No LLM; used by PDF layout and pipeline segmentization.
# =============================================================================

from __future__ import annotations

from .constants import HARD_BREAK_MIN_GAP_RATIO, SOFT_BREAK_MAX_GAP_RATIO


def _is_soft_line_break(prev: str, nxt: str) -> bool:
    """True when two visual lines should merge into one paragraph."""
    prev = prev.rstrip()
    nxt = nxt.lstrip()
    if not prev or not nxt:
        return False
    if prev.endswith(("-", "\u2010", "\u2011")):
        return True
    if prev[-1] in ".!?:;":
        return False
    if nxt[0].islower():
        return True
    if prev[-1] in ",;:" or prev[-1].isalnum():
        return True
    return False


def _join_soft_lines(lines: list[str]) -> str:
    """Merge soft wraps; preserve hard paragraph gaps as blank lines."""
    if not lines:
        return ""
    parts: list[str] = []
    buf = lines[0].rstrip()
    for nxt in lines[1:]:
        nxt_s = nxt.strip()
        if not nxt_s:
            if buf:
                parts.append(buf)
                buf = ""
            continue
        if not buf:
            buf = nxt_s
            continue
        if _is_soft_line_break(buf, nxt_s):
            if buf.endswith(("-", "\u2010", "\u2011")) and nxt_s and nxt_s[0].islower():
                buf = buf[:-1] + nxt_s
            else:
                buf = f"{buf} {nxt_s}"
        else:
            parts.append(buf)
            buf = nxt_s
    if buf:
        parts.append(buf)
    return "\n\n".join(parts)


def _reconstruct_paragraphs_from_lines(
    line_texts: list[str],
    line_sizes: list[float],
    line_bboxes: list[tuple[float, float, float, float]],
) -> list[str]:
    """Rebuild paragraphs using vertical gaps and soft-wrap heuristics."""
    if not line_texts:
        return []

    groups: list[list[str]] = [[line_texts[0]]]
    for i in range(1, len(line_texts)):
        prev_bbox = line_bboxes[i - 1]
        cur_bbox = line_bboxes[i]
        avg_size = (line_sizes[i - 1] + line_sizes[i]) / 2.0 or 12.0
        gap = cur_bbox[1] - prev_bbox[3]
        prev_text = line_texts[i - 1]
        cur_text = line_texts[i]

        hard = gap > avg_size * HARD_BREAK_MIN_GAP_RATIO
        soft = (
            gap <= avg_size * SOFT_BREAK_MAX_GAP_RATIO
            and _is_soft_line_break(prev_text, cur_text)
        )
        if hard or not soft:
            # Sentence end + capital start with moderate gap → new paragraph
            groups.append([cur_text])
        else:
            groups[-1].append(cur_text)

    return [_join_soft_lines(g) for g in groups if any(t.strip() for t in g)]
