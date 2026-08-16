# =============================================================================
# File: test_pipeline_layers.py
# Module/Service: Comparison Service (TASK-CMP-28)
# Layer: Test
# Purpose: Unit-layer V1/V2 checks for mapping, diff, risk, and citation.
# Responsibilities:
#   - Mapping keeps 1.2/1.3/8.2 identity pairs
#   - Diff classifies UNCHANGED/MODIFIED/ADDED without LLM
#   - Risk and citation fields stay structured enums
# Dependencies:
#   - pytest, ClauseMappingEngine, ClauseDiffEngine, orchestrator report
# Public Exports:
#   - pytest test cases
# Database/Table: N/A
# Related Modules: document_structure mapper/differ
# Important Notes: No database. No real LLM credentials.
# =============================================================================

from __future__ import annotations

from app.ai.document_structure.diff_types import DiffClassification
from app.services.document_structure.differ import ClauseDiffEngine
from app.services.document_structure.mapper import ClauseMappingEngine
from tests.comparison.expected import FORBIDDEN_ADDED


def test_mapping_pairs_stable_identities(v1_structure, v2_structure) -> None:
    mapping = ClauseMappingEngine().map_structures(v1_structure, v2_structure)
    pairs = mapping.paired_identity_keys()
    for key in (*FORBIDDEN_ADDED, "CLAUSE:8.2", "CLAUSE:2.1", "CLAUSE:11.2"):
        assert (
            pairs.get(key) == key
        ), f"Clause: {key}\nExpected: mapped to {key}\nActual: {pairs.get(key)}"
    assert mapping.metadata.get("mapping_llm_calls", 0) == 0


def test_diff_classifies_core_v1_v2_leaves(v1_structure, v2_structure) -> None:
    result = ClauseDiffEngine().diff_structures(v1_structure, v2_structure)
    assert result.find_source("CLAUSE:1.2").classification is DiffClassification.UNCHANGED
    assert result.find_source("CLAUSE:1.3").classification is DiffClassification.UNCHANGED
    assert result.find_source("CLAUSE:2.1").classification is DiffClassification.MODIFIED
    assert result.find_source("CLAUSE:8.2").classification is DiffClassification.MODIFIED
    assert result.find_target("CLAUSE:8.3").classification is DiffClassification.ADDED
    assert result.find_target("CLAUSE:1.2").classification is not DiffClassification.ADDED
    assert result.metadata.get("diff_llm_calls", 0) == 0


def test_risk_and_citation_are_structured_not_prose(v1_v2_report) -> None:
    row = v1_v2_report.clause("CLAUSE:8.2")
    assert row is not None
    assert row.risk is not None
    assert row.risk["risk_level"] in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    assert row.risk["risk_category"]
    assert row.risk["triggered_rules"]
    assert "explanation_text" not in row.risk or not row.risk.get("explanation_text")
    verification = row.verification or {}
    assert verification.get("status") in {
        "VERIFIED",
        "PARTIALLY_VERIFIED",
        "UNVERIFIED",
        "INSUFFICIENT_EVIDENCE",
        "INVALID",
    }
