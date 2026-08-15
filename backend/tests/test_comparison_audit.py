# =============================================================================
# File: test_comparison_audit.py
# Module/Service: Comparison Service (TASK-CMP-23)
# Layer: Service
# Purpose: Unit tests for append-only comparison audit helpers.
# Responsibilities:
#   - Append never mutates prior events; debounce CLAUSE_OPENED
#   - Review no-op detection via review_status_of
# Dependencies:
#   - pytest, app.services.comparison.audit
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: app.services.comparison.audit
# Important Notes: Audit is not a chat feed and never rewrites analysis.
# =============================================================================

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.services.comparison.audit import (
    AuditError,
    MAX_EVENTS,
    append_event,
    make_event,
    normalize_audit,
    review_status_of,
    should_debounce_open,
    snapshot_text,
)


def test_append_event_does_not_mutate_prior_rows() -> None:
    first = make_event(
        action="CLAUSE_OPENED",
        actor_id=uuid4(),
        actor_name="Alex",
        occurred_at=datetime(2026, 8, 15, tzinfo=UTC),
        clause_id="CLAUSE:8.2",
    )
    existing = [first]
    snapshot_id = first["id"]
    snapshot_action = first["action"]
    second = make_event(
        action="REVIEW_STATUS_CHANGED",
        actor_id=uuid4(),
        actor_name="Alex",
        occurred_at=datetime(2026, 8, 15, 1, tzinfo=UTC),
        clause_id="CLAUSE:8.2",
        before={"status": "OPEN"},
        after={"status": "REVIEWED"},
    )
    next_rows = append_event(existing, second)
    assert len(next_rows) == 2
    assert existing[0]["id"] == snapshot_id
    assert existing[0]["action"] == snapshot_action
    assert len(existing) == 1
    first["action"] = "TAMPERED"
    assert next_rows[0]["action"] == "CLAUSE_OPENED"


def test_normalize_skips_invalid_without_rewriting() -> None:
    actor = uuid4()
    valid = make_event(
        action="COMMENT_ADDED",
        actor_id=actor,
        actor_name="Alex",
        occurred_at=datetime(2026, 8, 15, tzinfo=UTC),
        clause_id="CLAUSE:8.2",
        after={"body": "check cap"},
        comment_id="c1",
    )
    raw = [valid, {"id": "x"}, {"action": "UNKNOWN", "id": "y", "occurred_at": "now"}]
    out = normalize_audit(raw)
    assert len(out) == 1
    assert out[0]["action"] == "COMMENT_ADDED"
    assert raw[0]["id"] == valid["id"]


def test_debounce_open_same_actor_clause() -> None:
    actor = uuid4()
    now = datetime(2026, 8, 15, 12, tzinfo=UTC)
    event = make_event(
        action="CLAUSE_OPENED",
        actor_id=actor,
        actor_name="Alex",
        occurred_at=now,
        clause_id="CLAUSE:8.2",
    )
    assert should_debounce_open(
        [event],
        actor_id=actor,
        clause_id="CLAUSE:8.2",
        occurred_at=now + timedelta(seconds=30),
    )
    assert not should_debounce_open(
        [event],
        actor_id=actor,
        clause_id="CLAUSE:8.2",
        occurred_at=now + timedelta(seconds=61),
    )
    assert not should_debounce_open(
        [event],
        actor_id=uuid4(),
        clause_id="CLAUSE:8.2",
        occurred_at=now + timedelta(seconds=10),
    )


def test_review_status_of_and_snapshot() -> None:
    assert review_status_of({}, "CLAUSE:8.2") == "OPEN"
    assert review_status_of(
        {"CLAUSE:8.2": {"status": "REVIEWED"}}, "CLAUSE:8.2"
    ) == "REVIEWED"
    assert snapshot_text("a" * 600) == "a" * 500


def test_audit_limit() -> None:
    rows = [{"id": str(i), "action": "CLAUSE_OPENED"} for i in range(MAX_EVENTS)]
    with pytest.raises(AuditError) as exc:
        append_event(
            rows,
            make_event(
                action="CLAUSE_OPENED",
                actor_id=uuid4(),
                actor_name="Alex",
                occurred_at=datetime(2026, 8, 15, tzinfo=UTC),
                clause_id="CLAUSE:1",
            ),
        )
    assert exc.value.code == "audit_limit"
    assert len(rows) == MAX_EVENTS
