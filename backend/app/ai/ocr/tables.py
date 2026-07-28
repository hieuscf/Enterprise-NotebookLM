# =============================================================================
# File: tables.py
# Module/Service: Pipeline Worker — Document Parsing & Cleaning ([AI])
# Layer: Service
# Purpose: Semantic table format/parse/merge and aligned-line table detection.
# Responsibilities:
#   - Format tables as Column=Value text; parse back for merge
#   - Merge cross-page table fragments; detect column-aligned PDF lines
# Dependencies:
#   - app.ai.ocr.constants, app.ai.ocr.models
# Public Exports:
#   - _format_table_semantic, _format_kv_fallback, _infer_table_col_count,
#     _parse_semantic_table, _tables_can_merge, _merge_two_table_blocks,
#     _merge_cross_page_tables, _count_unmerged_table_candidates,
#     _detect_table_from_aligned_lines
# Database/Table: N/A
# Related Modules: app.ai.ocr.*
# Important Notes: Merge is observability-aware via unmerged candidate counts.
# =============================================================================

from __future__ import annotations

from collections import Counter

from .constants import TABLE_MIN_COLS, TABLE_MIN_ROWS, _ROW_LABEL_RE, _TABLE_KV_RE
from .models import _ParsedBlock


def _format_table_semantic(
    headers: list[str],
    rows: list[list[str]],
    *,
    title: str | None = None,
) -> str:
    """Render a table as ``Column : Value`` rows for better embeddings."""
    parts: list[str] = []
    if title:
        parts.append(title)
    headers = [h.strip() for h in headers]
    for idx, row in enumerate(rows, start=1):
        parts.append(f"Row {idx}")
        for col_i, cell in enumerate(row):
            cell = (cell or "").strip()
            if not cell:
                continue
            if col_i < len(headers) and headers[col_i]:
                parts.append(f"{headers[col_i]} = {cell}")
            else:
                parts.append(f"Column{col_i + 1} = {cell}")
    return "\n".join(parts)


def _format_kv_fallback(rows: list[list[str]]) -> str:
    """Fallback when headers are unknown: ``ColumnA : ValueA`` per cell pair."""
    parts: list[str] = []
    for idx, row in enumerate(rows, start=1):
        cells = [c.strip() for c in row if c and c.strip()]
        if not cells:
            continue
        parts.append(f"Row {idx}")
        if len(cells) == 2:
            parts.append(f"{cells[0]} : {cells[1]}")
        else:
            for i, cell in enumerate(cells, start=1):
                parts.append(f"Column{i} : {cell}")
    return "\n".join(parts)


def _infer_table_col_count(text: str) -> int | None:
    """Infer column count from semantic table text (first data row)."""
    _title, headers, rows = _parse_semantic_table(text)
    if headers:
        return len(headers)
    if rows:
        return max((len(r) for r in rows), default=None)
    return None


def _parse_semantic_table(
    text: str,
) -> tuple[str | None, list[str], list[list[str]]]:
    """Parse ``Row N`` / ``Col = Val`` text back into headers + body rows."""
    title: str | None = None
    headers: list[str] = []
    rows: list[list[str]] = []
    current: list[tuple[str, str]] = []

    def flush() -> None:
        nonlocal current, headers, rows
        if not current:
            return
        if not headers:
            headers = [k for k, _ in current]
        mapping = dict(current)
        rows.append([mapping.get(h, "") for h in headers])
        current = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.lower().startswith("sheet:"):
            title = line
            continue
        if _ROW_LABEL_RE.match(line):
            flush()
            continue
        match = _TABLE_KV_RE.match(line)
        if match:
            current.append((match.group(1).strip(), match.group(2).strip()))
    flush()
    return title, headers, rows


def _tables_can_merge(left: _ParsedBlock, right: _ParsedBlock) -> bool:
    """True when ``right`` continues a table started by ``left`` on the next page."""
    if left.block_type != "table" or right.block_type != "table":
        return False
    if left.page_number is None or right.page_number is None:
        return False
    if right.page_number != left.page_number + 1:
        return False
    if left.section != right.section:
        return False
    left_cols = left.table_col_count or _infer_table_col_count(left.text)
    right_cols = right.table_col_count or _infer_table_col_count(right.text)
    if left_cols is None or right_cols is None:
        return False
    if left_cols != right_cols or left_cols < TABLE_MIN_COLS:
        return False
    return True


def _merge_two_table_blocks(left: _ParsedBlock, right: _ParsedBlock) -> _ParsedBlock:
    """Merge continuation table ``right`` into ``left``, keeping left's header."""
    title_l, headers_l, rows_l = _parse_semantic_table(left.text)
    title_r, headers_r, rows_r = _parse_semantic_table(right.text)

    headers = headers_l or headers_r
    body = list(rows_l)

    for row in rows_r:
        # Drop repeated header row when the continuation reprints column labels.
        if headers and len(row) == len(headers) and all(
            (row[i] if i < len(row) else "") == h for i, h in enumerate(headers)
        ):
            continue
        body.append(row)

    title = title_l or title_r
    if headers:
        text = _format_table_semantic(headers, body, title=title)
        col_count = len(headers)
    else:
        text = _format_kv_fallback(body)
        col_count = left.table_col_count or right.table_col_count

    return _ParsedBlock(
        text=text,
        page_number=left.page_number,
        section=left.section,
        block_type="table",
        bbox=left.bbox,
        font_size=left.font_size,
        font_name=left.font_name,
        is_bold=left.is_bold,
        section_index=left.section_index,
        table_col_count=col_count,
    )


def _merge_cross_page_tables(blocks: list[_ParsedBlock]) -> list[_ParsedBlock]:
    """Merge table fragments split across consecutive PDF pages.

    Conditions: adjacent table blocks, page N then N+1, same column count,
    same section, no non-table block between them.
    """
    if len(blocks) < 2:
        return blocks

    merged: list[_ParsedBlock] = []
    i = 0
    while i < len(blocks):
        current = blocks[i]
        if current.block_type != "table":
            merged.append(current)
            i += 1
            continue

        j = i + 1
        while j < len(blocks) and _tables_can_merge(current, blocks[j]):
            current = _merge_two_table_blocks(current, blocks[j])
            j += 1
        merged.append(current)
        i = j
    return merged


def _count_unmerged_table_candidates(blocks: list[_ParsedBlock]) -> int:
    """Count table pairs that look continuable but have intervening blocks.

    Observability only — does not change merge behavior (P0.2). Used when a
    non-table block sits between table ends on page N and table starts on N+1.
    """
    table_idxs = [i for i, b in enumerate(blocks) if b.block_type == "table"]
    count = 0
    for pos, i in enumerate(table_idxs):
        left = blocks[i]
        for j in table_idxs[pos + 1 :]:
            right = blocks[j]
            if left.page_number is None or right.page_number is None:
                continue
            if right.page_number < left.page_number + 1:
                continue
            if right.page_number > left.page_number + 1:
                break
            # Same next page: candidate if cols/section match but not adjacent.
            if left.section != right.section:
                continue
            left_cols = left.table_col_count or _infer_table_col_count(left.text)
            right_cols = right.table_col_count or _infer_table_col_count(right.text)
            if (
                left_cols is not None
                and right_cols is not None
                and left_cols == right_cols
                and left_cols >= TABLE_MIN_COLS
                and j > i + 1
            ):
                count += 1
            break
    return count


def _detect_table_from_aligned_lines(
    lines: list[tuple[str, list[tuple[float, str]]]],
) -> tuple[str, int] | None:
    """Detect column-aligned text lines and format as semantic table text.

    Returns:
        ``(semantic_text, column_count)`` or ``None`` if not table-like.
    """
    if len(lines) < TABLE_MIN_ROWS:
        return None

    col_counts = [len(spans) for _, spans in lines if len(spans) >= TABLE_MIN_COLS]
    if len(col_counts) < TABLE_MIN_ROWS:
        return None

    # Dominant column count
    n_cols, freq = Counter(col_counts).most_common(1)[0]
    if n_cols < TABLE_MIN_COLS or freq < TABLE_MIN_ROWS:
        return None

    matrix: list[list[str]] = []
    for _, spans in lines:
        if len(spans) != n_cols:
            continue
        matrix.append([t.strip() for _, t in spans])
    if len(matrix) < TABLE_MIN_ROWS:
        return None

    headers = matrix[0]
    body = matrix[1:]
    if body and all(headers):
        return _format_table_semantic(headers, body), n_cols
    return _format_kv_fallback(matrix), n_cols
