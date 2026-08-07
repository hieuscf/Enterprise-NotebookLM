# =============================================================================
# File: timeline_sort.py
# Module/Service: Extraction Service (FR7)
# Layer: Service
# Purpose: Deterministic chronological sorting for timeline extraction events.
# Responsibilities:
#   - Parse exact dates / year-month / year / textual periods when possible
#   - Fall back to stable chunk_index ordering when chronology is ambiguous
# Dependencies:
#   - datetime, re
# Public Exports:
#   - sort_timeline_events
# Database/Table: N/A
# Related Modules: extraction_service, TimelineExtractionResult
# Important Notes: Never invent exact dates; preserve periods as stated.
# =============================================================================

from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Any

_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_YEAR_MONTH = re.compile(r"^(\d{4})-(\d{2})$")
_YEAR = re.compile(r"^(\d{4})$")
_YEAR_RANGE = re.compile(r"^(\d{4})\s*[–-]\s*(\d{4})$")
_QUARTER = re.compile(r"^Q([1-4])\s+(\d{4})$", re.IGNORECASE)
_MONTH_YEAR = re.compile(
    r"^(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+(\d{4})$",
    re.IGNORECASE,
)

_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def _sort_key(date_or_period: str) -> tuple[int, date | None, str]:
    """Return (precision_rank, sortable_date_or_None, original) for ordering.

    Lower precision_rank sorts earlier within the same date when needed.
    Ambiguous periods get precision_rank=99 and date=None so callers can
    fall back to chunk order.
    """
    text = (date_or_period or "").strip()
    m = _ISO_DATE.match(text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return (0, date(y, mo, d), text)
        except ValueError:
            return (99, None, text)

    m = _YEAR_MONTH.match(text)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        try:
            return (1, date(y, mo, 1), text)
        except ValueError:
            return (99, None, text)

    m = _MONTH_YEAR.match(text)
    if m:
        mo = _MONTHS.get(m.group(1).lower())
        y = int(m.group(2))
        if mo:
            return (1, date(y, mo, 1), text)

    m = _QUARTER.match(text)
    if m:
        q, y = int(m.group(1)), int(m.group(2))
        return (2, date(y, (q - 1) * 3 + 1, 1), text)

    m = _YEAR_RANGE.match(text)
    if m:
        y1 = int(m.group(1))
        return (3, date(y1, 1, 1), text)

    m = _YEAR.match(text)
    if m:
        return (3, date(int(m.group(1)), 1, 1), text)

    return (99, None, text)


def sort_timeline_events(
    events: list[dict[str, Any]],
    *,
    chunk_order: dict[uuid.UUID, int],
) -> list[dict[str, Any]]:
    """Sort events chronologically; ambiguous periods use stable chunk order."""

    def key(ev: dict[str, Any]) -> tuple:
        precision, d, original = _sort_key(str(ev.get("date_or_period") or ""))
        chunk_id = ev.get("source_chunk_id")
        try:
            cid = chunk_id if isinstance(chunk_id, uuid.UUID) else uuid.UUID(str(chunk_id))
        except (TypeError, ValueError):
            cid = uuid.UUID(int=0)
        order = chunk_order.get(cid, 10**9)
        # Sortable dates first by date; unresolved periods after known dates,
        # ordered by chunk_index then original text for stability.
        if d is None:
            return (1, date.max, precision, order, original)
        return (0, d, precision, order, original)

    return sorted(events, key=key)
