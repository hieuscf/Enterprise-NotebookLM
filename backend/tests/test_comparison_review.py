# =============================================================================
# File: test_comparison_review.py
# Module/Service: Comparison Service (TASK-CMP-20)
# Layer: Service
# Purpose: Unit tests for review helpers — analysis result stays immutable.
# Responsibilities:
#   - Canonical clause id resolution; OPEN removes the decision
#   - apply_review never writes similarities/differences/contract_comparison
# Dependencies:
#   - pytest, app.services.comparison.review
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: app.services.comparison.review
# Important Notes: Frontend must not infer review from risk or verification.
# =============================================================================

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.services.comparison.review import (
    apply_review,
    canonical_clause_id,
    unwrap_contract_report,
)

RESULT = {
    "similarities": ["Both cap liability."],
    "differences": ["Cap increased."],
    "contract_comparison": {
        "clauses": {
            "modified": [
                {
                    "clause_id": "CLAUSE:8.2",
                    "v1_clause_id": "CLAUSE:8.2",
                    "v2_clause_id": "CLAUSE:8.2",
                    "status": "MODIFIED",
                    "risk": {"risk_level": "CRITICAL"},
                }
            ],
            "added": [{"clause_id": "CLAUSE:8.3", "status": "ADDED"}],
            "removed": [],
            "unchanged": [{"clause_id": "CLAUSE:1", "status": "UNCHANGED"}],
            "unresolved": [],
        }
    },
}


def test_unwrap_and_canonical_ids() -> None:
    assert unwrap_contract_report(RESULT) is not None
    assert canonical_clause_id(RESULT, "CLAUSE:8.2") == "CLAUSE:8.2"
    assert canonical_clause_id(RESULT, "8.2") is None
    assert canonical_clause_id(RESULT, "missing") is None
    assert unwrap_contract_report({"similarities": [], "differences": []}) is None


def test_apply_review_does_not_touch_analysis() -> None:
    snapshot = {
        "similarities": list(RESULT["similarities"]),
        "differences": list(RESULT["differences"]),
        "contract_comparison": RESULT["contract_comparison"],
    }
    reviewer = uuid4()
    reviewed = apply_review(
        {},
        clause_id="CLAUSE:8.2",
        status="REVIEWED",
        reviewer_id=reviewer,
        reviewer_name="Lan",
        reviewed_at=datetime(2026, 8, 15, tzinfo=UTC),
    )
    assert reviewed["CLAUSE:8.2"]["status"] == "REVIEWED"
    assert reviewed["CLAUSE:8.2"]["reviewer_name"] == "Lan"
    assert snapshot["similarities"] == RESULT["similarities"]
    assert snapshot["differences"] == RESULT["differences"]
    assert snapshot["contract_comparison"]["clauses"]["modified"][0]["status"] == "MODIFIED"
    assert snapshot["contract_comparison"]["clauses"]["modified"][0]["risk"]["risk_level"] == "CRITICAL"

    needs = apply_review(
        reviewed,
        clause_id="CLAUSE:8.2",
        status="NEEDS_ATTENTION",
        reviewer_id=reviewer,
        reviewer_name="Lan",
        reviewed_at=datetime(2026, 8, 15, tzinfo=UTC),
    )
    assert needs["CLAUSE:8.2"]["status"] == "NEEDS_ATTENTION"
    opened = apply_review(
        needs,
        clause_id="CLAUSE:8.2",
        status="OPEN",
        reviewer_id=reviewer,
        reviewer_name="Lan",
        reviewed_at=datetime(2026, 8, 15, tzinfo=UTC),
    )
    assert "CLAUSE:8.2" not in opened
