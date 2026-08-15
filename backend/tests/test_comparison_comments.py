# =============================================================================
# File: test_comparison_comments.py
# Module/Service: Comparison Service (TASK-CMP-22)
# Layer: Service
# Purpose: Unit tests for reviewer comments — analysis result stays immutable.
# Responsibilities:
#   - Target resolution for clause / exact difference / evidence
#   - add/update/delete never write similarities/differences/contract_comparison
# Dependencies:
#   - pytest, app.services.comparison.comments
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: app.services.comparison.comments
# Important Notes: Comments are reviewer context, not system analysis.
# =============================================================================

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.services.comparison.comments import (
    CommentError,
    add_comment,
    delete_comment,
    normalize_comments,
    resolve_comment_target,
    update_comment,
)

RESULT = {
    "similarities": ["Both cap liability."],
    "differences": ["Cap increased."],
    "contract_comparison": {
        "clauses": {
            "modified": [
                {
                    "clause_id": "CLAUSE:8.2",
                    "status": "MODIFIED",
                    "risk": {"risk_level": "CRITICAL", "risk_score": "0.91"},
                    "exact_differences": [
                        {
                            "value_type": "MONEY",
                            "old": {"raw": "480,000,000"},
                            "new": {"raw": "600,000,000"},
                        }
                    ],
                    "evidence": [{"evidence_id": "ev-1", "page_number": 4}],
                    "explanation": {"output": {"explanation": "Cap increased."}},
                }
            ],
            "added": [],
            "removed": [],
            "unchanged": [],
            "unresolved": [],
        }
    },
}


def test_resolve_targets() -> None:
    assert resolve_comment_target(
        RESULT, clause_id="CLAUSE:8.2", target_type="CLAUSE", target_id=None
    ) == ("CLAUSE:8.2", "CLAUSE", None)
    assert resolve_comment_target(
        RESULT, clause_id="CLAUSE:8.2", target_type="FINDING", target_id=None
    ) == ("CLAUSE:8.2", "CLAUSE", None)
    assert resolve_comment_target(
        RESULT, clause_id="CLAUSE:8.2", target_type="EXACT_DIFFERENCE", target_id="0"
    ) == ("CLAUSE:8.2", "EXACT_DIFFERENCE", "0")
    assert resolve_comment_target(
        RESULT, clause_id="CLAUSE:8.2", target_type="EVIDENCE", target_id="ev-1"
    ) == ("CLAUSE:8.2", "EVIDENCE", "ev-1")
    with pytest.raises(CommentError):
        resolve_comment_target(
            RESULT, clause_id="CLAUSE:9", target_type="CLAUSE", target_id=None
        )
    with pytest.raises(CommentError):
        resolve_comment_target(
            RESULT, clause_id="CLAUSE:8.2", target_type="EVIDENCE", target_id="missing"
        )


def test_add_comment_does_not_touch_analysis() -> None:
    snapshot = {
        "similarities": list(RESULT["similarities"]),
        "differences": list(RESULT["differences"]),
        "contract_comparison": RESULT["contract_comparison"],
    }
    author = uuid4()
    rows = add_comment(
        [],
        clause_id="CLAUSE:8.2",
        target_type="CLAUSE",
        target_id=None,
        body="Please confirm whether the new cap is acceptable.",
        author_id=author,
        author_name="Lan",
        created_at=datetime(2026, 8, 15, tzinfo=UTC),
    )
    assert len(rows) == 1
    assert rows[0]["body"].startswith("Please confirm")
    assert snapshot["similarities"] == RESULT["similarities"]
    assert snapshot["differences"] == RESULT["differences"]
    clause = snapshot["contract_comparison"]["clauses"]["modified"][0]
    assert clause["status"] == "MODIFIED"
    assert clause["risk"]["risk_level"] == "CRITICAL"
    assert clause["exact_differences"][0]["old"]["raw"] == "480,000,000"
    assert clause["explanation"]["output"]["explanation"] == "Cap increased."

    updated = update_comment(
        rows,
        comment_id=rows[0]["id"],
        body="Need legal confirmation.",
        author_id=author,
        updated_at=datetime(2026, 8, 15, 12, tzinfo=UTC),
    )
    assert updated[0]["body"] == "Need legal confirmation."
    with pytest.raises(CommentError) as forbidden:
        update_comment(
            updated,
            comment_id=rows[0]["id"],
            body="Hijack",
            author_id=uuid4(),
            updated_at=datetime(2026, 8, 15, 13, tzinfo=UTC),
        )
    assert forbidden.value.status_code == 403

    deleted = delete_comment(
        updated,
        comment_id=rows[0]["id"],
        deleted_at=datetime(2026, 8, 15, 14, tzinfo=UTC),
    )
    assert normalize_comments(deleted) == []
    assert clause["status"] == "MODIFIED"
