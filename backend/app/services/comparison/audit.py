# =============================================================================
# File: audit.py
# Module/Service: Comparison Service (TASK-CMP-23)
# Layer: Service
# Purpose: Pure helpers for an append-only comparison review audit trail.
# Responsibilities:
#   - Build immutable audit events (who, what, which finding, when, what changed)
#   - Append-only list; never edit or delete prior events
#   - Debounce repeated CLAUSE_OPENED from the same actor
# Dependencies:
#   - N/A (pure)
# Public Exports:
#   - AUDIT_ACTIONS, append_event, make_event, normalize_audit,
#     review_status_of, should_debounce_open
# Database/Table: comparisons.audit
# Related Modules: ComparisonService.record_clause_opened, set_review, comments
# Important Notes: Audit is not a chat feed. Never mutate result, review, or comments.
# =============================================================================

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

AUDIT_ACTIONS = frozenset(
    {
        "CLAUSE_OPENED",
        "REVIEW_STATUS_CHANGED",
        "COMMENT_ADDED",
        "COMMENT_EDITED",
        "COMMENT_DELETED",
    }
)
MAX_EVENTS = 5000
OPEN_DEBOUNCE = timedelta(seconds=60)
SNAPSHOT_LIMIT = 500
PERSISTED_REVIEW = frozenset({"REVIEWED", "NEEDS_ATTENTION", "ACKNOWLEDGED"})


class AuditError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def snapshot_text(value: object, *, limit: int = SNAPSHOT_LIMIT) -> str:
    text = str(value or "")
    if len(text) > limit:
        return text[:limit]
    return text


def review_status_of(review: object, clause_id: str) -> str:
    if not isinstance(review, dict):
        return "OPEN"
    item = review.get(clause_id)
    if not isinstance(item, dict):
        return "OPEN"
    status = str(item.get("status") or "").upper()
    if status in PERSISTED_REVIEW:
        return status
    return "OPEN"


def make_event(
    *,
    action: str,
    actor_id: UUID,
    actor_name: str,
    occurred_at: datetime,
    clause_id: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    comment_id: str | None = None,
) -> dict[str, Any]:
    key = (action or "").strip().upper()
    if key not in AUDIT_ACTIONS:
        raise AuditError("invalid_audit_action", "Unsupported audit action")
    event: dict[str, Any] = {
        "id": str(uuid4()),
        "action": key,
        "actor_id": str(actor_id),
        "actor_name": (actor_name or "").strip() or "Reviewer",
        "occurred_at": occurred_at.isoformat(),
        "clause_id": (clause_id or "").strip() or None,
        "before": dict(before) if isinstance(before, dict) else None,
        "after": dict(after) if isinstance(after, dict) else None,
        "target_type": (target_type or "").strip().upper() or None,
        "target_id": (target_id or "").strip() or None,
        "comment_id": (comment_id or "").strip() or None,
    }
    return event


def _as_rows(existing: object) -> list[dict[str, Any]]:
    if not isinstance(existing, list):
        return []
    return [item for item in existing if isinstance(item, dict)]


def ensure_can_append(existing: object) -> None:
    if len(_as_rows(existing)) >= MAX_EVENTS:
        raise AuditError(
            "audit_limit",
            "Audit trail is full for this comparison",
            409,
        )


def append_event(existing: object, event: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a new list with event appended. Prior events are not mutated."""
    ensure_can_append(existing)
    rows = [dict(item) for item in _as_rows(existing)]
    rows.append(dict(event))
    return rows


def _parse_occurred_at(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def should_debounce_open(
    existing: object,
    *,
    actor_id: UUID,
    clause_id: str,
    occurred_at: datetime,
) -> bool:
    wanted_actor = str(actor_id)
    wanted_clause = (clause_id or "").strip()
    for item in reversed(_as_rows(existing)):
        if str(item.get("action") or "").upper() != "CLAUSE_OPENED":
            continue
        if str(item.get("actor_id") or "") != wanted_actor:
            continue
        if str(item.get("clause_id") or "") != wanted_clause:
            continue
        previous = _parse_occurred_at(item.get("occurred_at"))
        if previous is None:
            return False
        if previous.tzinfo is None and occurred_at.tzinfo is not None:
            previous = previous.replace(tzinfo=occurred_at.tzinfo)
        return occurred_at - previous < OPEN_DEBOUNCE
    return False


def normalize_audit(raw: object) -> list[dict[str, Any]]:
    """Return a read-only chronological copy. Invalid rows are skipped, never rewritten."""
    out: list[dict[str, Any]] = []
    for item in _as_rows(raw):
        action = str(item.get("action") or "").upper()
        event_id = str(item.get("id") or "").strip()
        occurred = str(item.get("occurred_at") or "").strip()
        if not event_id or action not in AUDIT_ACTIONS or not occurred:
            continue
        before = item.get("before")
        after = item.get("after")
        out.append(
            {
                "id": event_id,
                "action": action,
                "clause_id": str(item.get("clause_id") or "").strip() or None,
                "actor_id": str(item.get("actor_id") or "").strip() or None,
                "actor_name": str(item.get("actor_name") or "").strip() or None,
                "occurred_at": occurred,
                "before": dict(before) if isinstance(before, dict) else None,
                "after": dict(after) if isinstance(after, dict) else None,
                "target_type": str(item.get("target_type") or "").strip().upper() or None,
                "target_id": str(item.get("target_id") or "").strip() or None,
                "comment_id": str(item.get("comment_id") or "").strip() or None,
            }
        )
    return out
