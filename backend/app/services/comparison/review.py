# =============================================================================
# File: review.py
# Module/Service: Comparison Service (TASK-CMP-20)
# Layer: Service
# Purpose: Pure helpers for reviewer decisions attached to comparison findings.
# Responsibilities:
#   - Resolve canonical clause ids from the stored contract_comparison report
#   - Apply review map updates without touching analysis result fields
# Dependencies:
#   - N/A (pure)
# Public Exports:
#   - REVIEW_STATUSES, unwrap_contract_report, canonical_clause_id,
#     find_clause_row, apply_review
# Database/Table: comparisons.review
# Related Modules: ComparisonService.set_review, app.schemas.comparisons
# Important Notes: Never mutate similarities/differences/contract_comparison.
# =============================================================================

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

REVIEW_STATUSES = frozenset(
    {"OPEN", "REVIEWED", "NEEDS_ATTENTION", "ACKNOWLEDGED"}
)
PERSISTED_STATUSES = frozenset(
    {"REVIEWED", "NEEDS_ATTENTION", "ACKNOWLEDGED"}
)
_CLAUSE_BUCKETS = ("modified", "added", "removed", "unchanged", "unresolved")


def unwrap_contract_report(result: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return the clause report object, or None when enrichment is absent."""
    if not isinstance(result, dict):
        return None
    raw = result.get("contract_comparison")
    if not isinstance(raw, dict):
        return None
    nested = raw.get("comparison")
    if isinstance(nested, dict) and (nested.get("clauses") or nested.get("summary")):
        return nested
    if raw.get("clauses") or raw.get("summary"):
        return raw
    return None


def clause_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    clauses = report.get("clauses")
    if not isinstance(clauses, dict):
        return []
    rows: list[dict[str, Any]] = []
    for bucket in _CLAUSE_BUCKETS:
        items = clauses.get(bucket)
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and item.get("clause_id"):
                rows.append(item)
    return rows


def canonical_clause_id(result: dict[str, Any] | None, requested: str) -> str | None:
    """Map a requested id (canonical, v1, or v2) to the report clause_id."""
    key = (requested or "").strip()
    if not key:
        return None
    report = unwrap_contract_report(result)
    if report is None:
        return None
    upper = key.upper()
    for row in clause_rows(report):
        candidates = [
            row.get("clause_id"),
            row.get("v1_clause_id"),
            row.get("v2_clause_id"),
        ]
        ids = [str(item) for item in candidates if item]
        if any(item == key or item.upper() == upper for item in ids):
            return str(row["clause_id"])
    return None


def find_clause_row(result: dict[str, Any] | None, clause_id: str) -> dict[str, Any] | None:
    report = unwrap_contract_report(result)
    if report is None:
        return None
    wanted = str(clause_id)
    for row in clause_rows(report):
        if str(row.get("clause_id") or "") == wanted:
            return row
    return None


def apply_review(
    existing: dict[str, Any] | None,
    *,
    clause_id: str,
    status: str,
    reviewer_id: UUID,
    reviewer_name: str,
    reviewed_at: datetime,
) -> dict[str, Any]:
    """Return a new review map. OPEN removes the clause entry."""
    next_map = dict(existing or {})
    normalized = status.strip().upper()
    if normalized == "OPEN":
        next_map.pop(clause_id, None)
        return next_map
    next_map[clause_id] = {
        "status": normalized,
        "reviewer_id": str(reviewer_id),
        "reviewer_name": reviewer_name,
        "reviewed_at": reviewed_at.isoformat(),
    }
    return next_map
