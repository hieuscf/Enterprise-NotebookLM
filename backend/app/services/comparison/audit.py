# =============================================================================
# File: audit.py
# Module/Service: Comparison Service (TASK-CMP-23 / TASK-CMP-27)
# Layer: Service
# Purpose: Pure helpers for an append-only comparison audit trail
#   (review actions + comparison lifecycle milestones).
# Responsibilities:
#   - Build immutable audit events (who, what, which finding, when, metadata)
#   - Append-only list; never edit or delete prior events
#   - Debounce repeated CLAUSE_OPENED from the same actor
#   - Sanitize lifecycle metadata; one-shot lifecycle idempotency
#   - Derive pipeline milestones from a persisted contract_comparison report
# Dependencies:
#   - app.services.comparison.review.unwrap_contract_report (milestones only)
# Public Exports:
#   - AUDIT_ACTIONS, REVIEW_ACTIONS, LIFECYCLE_ACTIONS, ONE_SHOT_ACTIONS
#   - append_event, make_event, normalize_audit, review_status_of
#   - should_debounce_open, has_action, is_one_shot, sanitize_metadata
#   - pipeline_milestones, stage_for_error_code
# Database/Table: comparisons.audit
# Related Modules: ComparisonService, ReportService (best-effort user actions)
# Important Notes:
#   - Audit is not the comparison source of truth and never mutates result.
#   - Deterministic only; no LLM calls. Do not store prompts, secrets, or
#     full contract text. "Not retrieved" is never recorded as "not exists".
# =============================================================================

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

REVIEW_ACTIONS = frozenset(
    {
        "CLAUSE_OPENED",
        "REVIEW_STATUS_CHANGED",
        "COMMENT_ADDED",
        "COMMENT_EDITED",
        "COMMENT_DELETED",
    }
)
LIFECYCLE_ACTIONS = frozenset(
    {
        "COMPARISON_CREATED",
        "COMPARISON_STARTED",
        "STRUCTURE_EXTRACTION_COMPLETED",
        "CLAUSE_NORMALIZATION_COMPLETED",
        "CLAUSE_MAPPING_COMPLETED",
        "DIFF_COMPLETED",
        "RISK_DETECTION_COMPLETED",
        "LLM_EXPLANATION_COMPLETED",
        "CITATION_VERIFICATION_COMPLETED",
        "COMPARISON_COMPLETED",
        "COMPARISON_FAILED",
        "COMPARISON_CANCELLED",
        "COMPARISON_REPORT_CREATED",
        "COMPARISON_EXPORTED",
    }
)
REPEATABLE_LIFECYCLE_ACTIONS = frozenset(
    {
        "COMPARISON_REPORT_CREATED",
        "COMPARISON_EXPORTED",
    }
)
ONE_SHOT_ACTIONS = LIFECYCLE_ACTIONS - REPEATABLE_LIFECYCLE_ACTIONS
AUDIT_ACTIONS = REVIEW_ACTIONS | LIFECYCLE_ACTIONS
EVENT_STATUSES = frozenset({"STARTED", "COMPLETED", "FAILED", "CANCELLED"})
SYSTEM_ACTOR_NAME = "system"
MAX_EVENTS = 5000
OPEN_DEBOUNCE = timedelta(seconds=60)
SNAPSHOT_LIMIT = 500
METADATA_KEY_LIMIT = 24
METADATA_STRING_LIMIT = 200
METADATA_LIST_LIMIT = 32
PERSISTED_REVIEW = frozenset({"REVIEWED", "NEEDS_ATTENTION", "ACKNOWLEDGED"})
_BLOCKED_KEY_PARTS = (
    "token",
    "secret",
    "password",
    "api_key",
    "apikey",
    "authorization",
    "prompt",
    "stack",
    "credential",
    "jwt",
    "cookie",
    "private_key",
    "access_token",
    "refresh_token",
)
_ERROR_STAGES = {
    "llm_not_configured": "llm",
    "llm_failed": "llm",
    "insufficient_context": "context",
    "enqueue_failed": "enqueue",
    "too_few_documents": "request",
    "mapping_failed": "mapping",
    "diff_failed": "diff",
    "risk_analysis_failed": "risk_detection",
    "citation_verification_failed": "citation_verification",
    "structure_extraction_failed": "structure_extraction",
}


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


def is_one_shot(action: str) -> bool:
    return (action or "").strip().upper() in ONE_SHOT_ACTIONS


def has_action(existing: object, action: str) -> bool:
    key = (action or "").strip().upper()
    return any(str(item.get("action") or "").upper() == key for item in _as_rows(existing))


def stage_for_error_code(code: str | None) -> str:
    key = (code or "").strip().lower()
    if key in _ERROR_STAGES:
        return _ERROR_STAGES[key]
    if key and key.replace("_", "").isalnum() and len(key) <= 64:
        return key
    return "processing"


def _is_blocked_key(name: str) -> bool:
    lowered = name.lower()
    return any(part in lowered for part in _BLOCKED_KEY_PARTS)


def _sanitize_value(value: object, *, depth: int = 0) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        return snapshot_text(value, limit=METADATA_STRING_LIMIT)
    if isinstance(value, UUID):
        return str(value)
    if depth >= 2:
        return None
    if isinstance(value, list):
        cleaned: list[Any] = []
        for item in value[:METADATA_LIST_LIMIT]:
            next_value = _sanitize_value(item, depth=depth + 1)
            if next_value is not None or item is None:
                cleaned.append(next_value)
        return cleaned
    if isinstance(value, dict):
        return sanitize_metadata(value) or {}
    return snapshot_text(value, limit=METADATA_STRING_LIMIT)


def sanitize_metadata(raw: object) -> dict[str, Any] | None:
    """Keep a small deterministic metadata dict. Secrets and prompts are dropped."""
    if not isinstance(raw, dict) or not raw:
        return None
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if len(out) >= METADATA_KEY_LIMIT:
            break
        name = str(key).strip()
        if not name or _is_blocked_key(name):
            continue
        cleaned = _sanitize_value(value)
        if cleaned is None and value is not None:
            continue
        out[name] = cleaned
    return out or None


def make_event(
    *,
    action: str,
    occurred_at: datetime,
    actor_id: UUID | None = None,
    actor_name: str | None = None,
    clause_id: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    comment_id: str | None = None,
    status: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    key = (action or "").strip().upper()
    if key not in AUDIT_ACTIONS:
        raise AuditError("invalid_audit_action", "Unsupported audit action")
    if key in REVIEW_ACTIONS and actor_id is None:
        raise AuditError("invalid_audit_actor", "Review audit actions require an actor")
    status_key = (status or "").strip().upper() or None
    if status_key is not None and status_key not in EVENT_STATUSES:
        raise AuditError("invalid_audit_status", "Unsupported audit status")
    name = (actor_name or "").strip()
    if not name:
        name = SYSTEM_ACTOR_NAME if actor_id is None else "Reviewer"
    event: dict[str, Any] = {
        "id": str(uuid4()),
        "action": key,
        "actor_id": str(actor_id) if actor_id is not None else None,
        "actor_name": name,
        "occurred_at": occurred_at.isoformat(),
        "clause_id": (clause_id or "").strip() or None,
        "before": dict(before) if isinstance(before, dict) else None,
        "after": dict(after) if isinstance(after, dict) else None,
        "target_type": (target_type or "").strip().upper() or None,
        "target_id": (target_id or "").strip() or None,
        "comment_id": (comment_id or "").strip() or None,
        "status": status_key,
        "metadata": sanitize_metadata(metadata),
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
        status = str(item.get("status") or "").strip().upper() or None
        if status is not None and status not in EVENT_STATUSES:
            status = None
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
                "status": status,
                "metadata": sanitize_metadata(item.get("metadata")),
            }
        )
    return out


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _risk_metadata(statistics: dict[str, Any]) -> dict[str, Any]:
    raw = statistics.get("risk_counts")
    counts = raw if isinstance(raw, dict) else {}

    def count_of(*names: str) -> int:
        for name in names:
            value = _as_int(counts.get(name))
            if value is not None:
                return value
        return 0

    critical = count_of("critical", "CRITICAL")
    high = count_of("high", "HIGH")
    medium = count_of("medium", "MEDIUM")
    low = count_of("low", "LOW")
    return {
        "stage": "risk_detection",
        "risk_count": critical + high + medium + low,
        "critical_count": critical,
        "high_count": high,
        "medium_count": medium,
        "low_count": low,
    }


def _compact(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _citation_metadata(report: dict[str, Any], statistics: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {"stage": "citation_verification"}
    rate = _as_float(statistics.get("citation_verification_rate"))
    if rate is not None:
        payload["citation_verification_rate"] = rate
    citations = report.get("citations")
    if isinstance(citations, list):
        verified = 0
        unverified = 0
        known = 0
        for item in citations:
            if not isinstance(item, dict):
                continue
            raw_status = item.get("status") or item.get("verification_status")
            verification = item.get("verification")
            if raw_status is None and isinstance(verification, dict):
                raw_status = verification.get("status")
            status = str(raw_status or "").upper()
            if status in {"VERIFIED", "VALID", "PASSED"}:
                verified += 1
                known += 1
            elif status in {"UNVERIFIED", "INVALID", "FAILED", "REJECTED"}:
                unverified += 1
                known += 1
        payload["total_citations"] = len(citations)
        if known:
            payload["verified"] = verified
            payload["unverified"] = unverified
    return payload


def _ref_ids(ref: object, *keys: str) -> list[str]:
    if not isinstance(ref, dict):
        return []
    out: list[str] = []
    for key in keys:
        value = ref.get(key)
        if value:
            out.append(str(value))
    return out


def pipeline_milestones(result: dict[str, Any] | None) -> list[tuple[str, dict[str, Any], str]]:
    """Return completed contract-pipeline milestones from a persisted report.

    FR8-only results (no contract_comparison) yield no stage events. Stages are
    recorded only when the persisted report proves they produced output.
    LLM_EXPLANATION_COMPLETED is omitted unless statistics.llm_calls > 0.
    """
    from app.services.comparison.review import unwrap_contract_report

    report = unwrap_contract_report(result)
    if report is None:
        return []
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    statistics = (
        report.get("statistics") if isinstance(report.get("statistics"), dict) else {}
    )
    metadata = report.get("metadata") if isinstance(report.get("metadata"), dict) else {}
    document_ids = _ref_ids(metadata.get("document_v1"), "document_id") + _ref_ids(
        metadata.get("document_v2"), "document_id"
    )
    version_ids = _ref_ids(metadata.get("document_v1"), "document_version_id") + _ref_ids(
        metadata.get("document_v2"), "document_version_id"
    )
    clause_count = _as_int(summary.get("total_clauses"))
    mapped = _as_int(statistics.get("mapped_clauses"))
    events: list[tuple[str, dict[str, Any], str]] = [
        (
            "STRUCTURE_EXTRACTION_COMPLETED",
            _compact(
                {
                    "document_count": 2 if document_ids else None,
                    "document_ids": document_ids or None,
                    "source_version_ids": version_ids or None,
                }
            ),
            "COMPLETED",
        ),
        (
            "CLAUSE_NORMALIZATION_COMPLETED",
            _compact({"clause_count": clause_count}),
            "COMPLETED",
        ),
        (
            "CLAUSE_MAPPING_COMPLETED",
            _compact(
                {
                    "clause_count": clause_count,
                    "mapped_clauses": mapped,
                }
            ),
            "COMPLETED",
        ),
        (
            "DIFF_COMPLETED",
            _compact(
                {
                    "clause_count": clause_count,
                    "modified_count": _as_int(summary.get("modified")),
                    "added_count": _as_int(summary.get("added")),
                    "removed_count": _as_int(summary.get("removed")),
                    "unchanged_count": _as_int(summary.get("unchanged")),
                }
            ),
            "COMPLETED",
        ),
        (
            "RISK_DETECTION_COMPLETED",
            _risk_metadata(statistics),
            "COMPLETED",
        ),
    ]
    llm_calls = _as_int(statistics.get("llm_calls")) or 0
    if llm_calls > 0:
        events.append(
            (
                "LLM_EXPLANATION_COMPLETED",
                {"llm_calls": llm_calls},
                "COMPLETED",
            )
        )
    events.append(
        (
            "CITATION_VERIFICATION_COMPLETED",
            _citation_metadata(report, statistics),
            "COMPLETED",
        )
    )
    return events
