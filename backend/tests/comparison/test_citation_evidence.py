# =============================================================================
# File: test_citation_evidence.py
# Module/Service: Comparison Service (TASK-CMP-28)
# Layer: Test
# Purpose: Citation verification and evidence traceability regression.
# Responsibilities:
#   - Modified/added findings have verified citations bound to evidence
#   - Evidence carries document/version/clause/page or span when present
#   - Missing retrieval is never asserted as "V1 does not contain"
# Dependencies:
#   - pytest, comparison/expected, verification types
# Public Exports:
#   - pytest test cases
# Database/Table: N/A
# Related Modules: Comparison Citation Verification
# Important Notes: Do not snapshot LLM prose. Do not invent absence facts.
# =============================================================================

from __future__ import annotations

from app.ai.document_structure.diff_types import DiffClassification
from app.ai.document_structure.verification_types import INSUFFICIENT_OLD_ABSENCE_MESSAGE
from tests.comparison.expected import GOLDEN


def test_modified_and_added_findings_are_verified(v1_v2_report) -> None:
    for row in (*v1_v2_report.clauses["modified"], *v1_v2_report.clauses["added"]):
        verification = row.verification or {}
        status = verification.get("status")
        assert status in {
            "VERIFIED",
            "PARTIALLY_VERIFIED",
            "INSUFFICIENT_EVIDENCE",
            "UNVERIFIED",
            "INVALID",
        }, f"Clause: {row.clause_id}\nExpected: verification status\nActual: {status}"
        if status in {"VERIFIED", "PARTIALLY_VERIFIED"}:
            assert row.citations, f"Clause: {row.clause_id}\nExpected: citations\nActual: []"
            verified_ids = set(verification.get("verified_evidence_ids") or [])
            for citation in row.citations:
                assert citation.get("evidence_id"), row.clause_id
                assert citation.get("document_id"), row.clause_id
                if verified_ids:
                    assert citation.get("evidence_id") in verified_ids
                if row.status is DiffClassification.ADDED:
                    assert citation.get("side") != "OLD"
        if status == "INVALID":
            assert row.citations == []
        if status == "INSUFFICIENT_EVIDENCE":
            blob = str(verification)
            assert "does not contain" not in blob.lower()
            assert "không có điều khoản" not in blob.lower()


def test_added_leaves_do_not_claim_v1_absence_as_fact(v1_v2_report) -> None:
    for key in GOLDEN.added_leaves:
        row = v1_v2_report.clause(key)
        assert row is not None
        assert row.v1_clause_id is None
        blob = str(row.verification or {}) + str(row.evidence) + str(row.citations)
        assert "V1 does not contain" not in blob
        assert "không tồn tại" not in blob.lower()
        if (row.verification or {}).get("status") == "INSUFFICIENT_EVIDENCE":
            assert INSUFFICIENT_OLD_ABSENCE_MESSAGE.split()[0] in str(row.verification)


def test_evidence_is_traceable_to_source_location(v1_v2_report) -> None:
    for key in ("CLAUSE:8.2", "CLAUSE:3.1", "CLAUSE:11.2"):
        row = v1_v2_report.clause(key)
        assert row is not None, key
        assert row.evidence, f"Clause: {key}\nExpected: evidence\nActual: []"
        for item in row.evidence:
            assert (
                item.get("document_id") or item.get("document_version_id") or item.get("clause_id")
            ), item
            locator = (
                item.get("page")
                or item.get("page_number")
                or item.get("chunk_id")
                or item.get("text_span")
                or item.get("span")
                or item.get("start")
            )
            assert locator is not None or item.get("evidence_id"), item


def test_citation_verification_rate_is_complete_on_regression(v1_v2_report) -> None:
    rate = v1_v2_report.statistics.citation_verification_rate
    assert rate == 1.0, (
        f"Expected: citation_verification_rate 1.0\nActual: {rate}\n"
        "Reason to investigate:\nA finding lost verification on the golden pair."
    )
