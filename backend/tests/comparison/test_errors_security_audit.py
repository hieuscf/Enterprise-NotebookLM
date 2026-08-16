# =============================================================================
# File: test_errors_security_audit.py
# Module/Service: Comparison Service (TASK-CMP-28)
# Layer: Test
# Purpose: Error, workspace isolation, and CMP-27 audit non-interference tests.
# Responsibilities:
#   - Invalid pairs return Error{code, message} without leaking internals
#   - Cross-workspace structures are rejected
#   - Audit event derivation does not mutate comparison classifications
# Dependencies:
#   - pytest, ContractComparisonOrchestrator, comparison audit helpers
# Public Exports:
#   - pytest test cases
# Database/Table: N/A
# Related Modules: Comparison Service audit (CMP-27)
# Important Notes: Does not duplicate the full CMP-27 audit suite.
# =============================================================================

from __future__ import annotations

import uuid

import pytest

from app.services.comparison.audit import append_event, make_event, pipeline_milestones
from app.services.document_structure.orchestrator import (
    ContractComparisonError,
    ContractComparisonOrchestrator,
)
from tests.comparison.conftest import normalize_contract
from tests.comparison.expected import classification_snapshot


def test_same_document_version_is_rejected(v1_txt) -> None:
    v1 = normalize_contract(v1_txt, title="V1")
    with pytest.raises(ContractComparisonError) as exc:
        ContractComparisonOrchestrator().compare_structures(v1, v1)
    assert exc.value.code == "invalid_document_pair"
    assert "traceback" not in exc.value.message.lower()
    assert "sql" not in exc.value.message.lower()
    assert "\\" not in exc.value.message


def test_cross_workspace_structures_are_rejected(v1_txt, v2_txt) -> None:
    v1 = normalize_contract(v1_txt, title="V1")
    v2 = normalize_contract(v2_txt, title="V2")
    v1.workspace_id = uuid.uuid4()
    v2.workspace_id = uuid.uuid4()
    with pytest.raises(ContractComparisonError) as exc:
        ContractComparisonOrchestrator().compare_structures(v1, v2)
    assert exc.value.code == "not_found"
    assert exc.value.status_code in {403, 404}


def test_audit_milestones_do_not_change_classifications(v1_v2_report) -> None:
    before = classification_snapshot(v1_v2_report)
    before_summary = v1_v2_report.summary.as_dict()
    payload = {
        "similarities": [],
        "differences": [],
        "contract_comparison": v1_v2_report.as_dict(include_text=False)["comparison"],
    }
    events = pipeline_milestones(payload)
    assert events
    assert "LLM_EXPLANATION_COMPLETED" not in [item[0] for item in events]
    trail = []
    from datetime import UTC, datetime

    for action, metadata, status in events:
        trail = append_event(
            trail,
            make_event(
                action=action,
                occurred_at=datetime.now(UTC),
                status=status,
                metadata=metadata,
            ),
        )
    assert classification_snapshot(v1_v2_report) == before
    assert v1_v2_report.summary.as_dict() == before_summary
    assert v1_v2_report.statistics.llm_calls == 0


def test_client_error_shape_has_code_and_message() -> None:
    err = ContractComparisonError("not_found", "Comparison source not found", status_code=404)
    assert err.code == "not_found"
    assert err.message
    assert "secret" not in err.message.lower()
    assert "api_key" not in err.message.lower()
