# =============================================================================
# File: test_comparison_audit.py
# Module/Service: Comparison Service (TASK-CMP-23)
# Layer: Service
# Purpose: Unit tests for append-only comparison review + lifecycle audit helpers.
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
    has_action,
    is_one_shot,
    make_event,
    normalize_audit,
    pipeline_milestones,
    review_status_of,
    sanitize_metadata,
    should_debounce_open,
    snapshot_text,
    stage_for_error_code,
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


def test_lifecycle_event_allows_system_actor_and_metadata() -> None:
    event = make_event(
        action="DIFF_COMPLETED",
        occurred_at=datetime(2026, 8, 16, tzinfo=UTC),
        status="COMPLETED",
        metadata={
            "modified_count": 3,
            "api_key": "sk-secret",
            "prompt": "full prompt",
            "stack_trace": "traceback",
        },
    )
    assert event["actor_id"] is None
    assert event["actor_name"] == "system"
    assert event["status"] == "COMPLETED"
    assert event["metadata"]["modified_count"] == 3
    assert "api_key" not in event["metadata"]
    assert "prompt" not in event["metadata"]
    assert "stack_trace" not in event["metadata"]


def test_review_event_requires_actor() -> None:
    with pytest.raises(AuditError) as exc:
        make_event(
            action="CLAUSE_OPENED",
            occurred_at=datetime(2026, 8, 16, tzinfo=UTC),
            clause_id="CLAUSE:8.2",
        )
    assert exc.value.code == "invalid_audit_actor"


def test_sanitize_metadata_and_idempotency_helpers() -> None:
    cleaned = sanitize_metadata(
        {
            "document_count": 2,
            "access_token": "abc",
            "authorization": "Bearer x",
            "nested": {"password": "p", "clause_count": 4},
        }
    )
    assert cleaned is not None
    assert cleaned["document_count"] == 2
    assert "access_token" not in cleaned
    assert "authorization" not in cleaned
    assert cleaned["nested"] == {"clause_count": 4}
    assert is_one_shot("DIFF_COMPLETED")
    assert not is_one_shot("COMPARISON_EXPORTED")
    assert not is_one_shot("CLAUSE_OPENED")
    existing = [{"action": "COMPARISON_CREATED"}]
    assert has_action(existing, "COMPARISON_CREATED")
    assert not has_action(existing, "COMPARISON_FAILED")
    assert stage_for_error_code("llm_not_configured") == "llm"
    assert stage_for_error_code("???") == "processing"


def test_normalize_keeps_lifecycle_and_skips_unknown() -> None:
    created = make_event(
        action="COMPARISON_CREATED",
        actor_id=uuid4(),
        actor_name="Alex",
        occurred_at=datetime(2026, 8, 16, tzinfo=UTC),
        status="COMPLETED",
        metadata={"document_count": 2},
    )
    raw = [
        created,
        {
            "id": "x",
            "action": "UNKNOWN_STAGE",
            "occurred_at": "2026-08-16T00:00:00+00:00",
        },
    ]
    out = normalize_audit(raw)
    assert [item["action"] for item in out] == ["COMPARISON_CREATED"]
    assert out[0]["metadata"]["document_count"] == 2
    assert created["action"] == "COMPARISON_CREATED"


def test_pipeline_milestones_from_persisted_report_only() -> None:
    assert pipeline_milestones(None) == []
    assert pipeline_milestones({"similarities": ["a"], "differences": ["b"]}) == []
    report = {
        "contract_comparison": {
            "metadata": {
                "document_v1": {
                    "document_id": "d1",
                    "document_version_id": "v1",
                },
                "document_v2": {
                    "document_id": "d2",
                    "document_version_id": "v2",
                },
            },
            "summary": {
                "total_clauses": 12,
                "unchanged": 8,
                "modified": 3,
                "added": 1,
                "removed": 0,
            },
            "statistics": {
                "mapped_clauses": 12,
                "risk_counts": {"critical": 2, "high": 1, "medium": 0, "low": 1},
                "llm_calls": 0,
                "citation_verification_rate": 0.875,
            },
            "citations": [
                {"status": "VERIFIED"},
                {"status": "UNVERIFIED"},
            ],
        }
    }
    actions = [item[0] for item in pipeline_milestones(report)]
    assert "LLM_EXPLANATION_COMPLETED" not in actions
    assert actions == [
        "STRUCTURE_EXTRACTION_COMPLETED",
        "CLAUSE_NORMALIZATION_COMPLETED",
        "CLAUSE_MAPPING_COMPLETED",
        "DIFF_COMPLETED",
        "RISK_DETECTION_COMPLETED",
        "CITATION_VERIFICATION_COMPLETED",
    ]
    with_llm = dict(report)
    inner = dict(report["contract_comparison"])
    stats = dict(inner["statistics"])
    stats["llm_calls"] = 2
    inner["statistics"] = stats
    with_llm["contract_comparison"] = inner
    assert "LLM_EXPLANATION_COMPLETED" in [item[0] for item in pipeline_milestones(with_llm)]
    diff_meta = next(item[1] for item in pipeline_milestones(report) if item[0] == "DIFF_COMPLETED")
    assert "does not exist" not in str(diff_meta).lower()
    assert diff_meta["modified_count"] == 3
