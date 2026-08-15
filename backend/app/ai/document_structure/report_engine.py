# =============================================================================
# File: report_engine.py
# Module/Service: Contract Comparison Orchestration (FR8 / TASK-CMP-15)
# Layer: Adapter
# Purpose: Deterministic aggregation of CMP-03..13 outputs into one report.
# Responsibilities:
#   - Build per-clause results from the complete DiffResult (not top-k)
#   - Derive summary / risk / verification statistics from those rows
# Dependencies:
#   - report_types; diff/exact/scoring/evidence/verification/llm types
# Public Exports:
#   - build_comparison_report, summarize_clauses
# Database/Table: N/A
# Related Modules: ContractComparisonOrchestrator
# Important Notes:
#   - Does not call LLM, retrieval, or mutate engine results.
#   - ADDED/REMOVED come only from CMP-04 on the full clause inventory.
# =============================================================================

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.ai.document_structure.diff_types import ClauseDiff, DiffClassification, DiffResult
from app.ai.document_structure.evidence_types import EvidenceBindingResult, FindingEvidence
from app.ai.document_structure.exact_types import ExactDiffResult
from app.ai.document_structure.llm_boundary_types import (
    ValidatedLLMResult,
    ValidationStatus,
)
from app.ai.document_structure.mapping_types import MappingResult
from app.ai.document_structure.report_types import (
    AuditableComparisonReport,
    ClauseComparisonResult,
    ComparisonStatistics,
    ComparisonSummary,
    DocumentRef,
    ReportStatus,
    bucket_name,
    empty_clause_buckets,
    empty_risk_counts,
)
from app.ai.document_structure.scoring_types import (
    RiskScoreResult,
    RiskScoringResult,
    RiskStatus,
)
from app.ai.document_structure.taxonomy_types import TaxonomyAssignment, TaxonomyResult
from app.ai.document_structure.verification_types import (
    ComparisonVerificationResult,
    FindingVerification,
    VerificationStatus,
)

_VERIFIED = frozenset(
    {
        VerificationStatus.VERIFIED,
        VerificationStatus.PARTIALLY_VERIFIED,
    }
)
_LLM_INCOMPLETE = frozenset(
    {
        ValidationStatus.FAILED,
        ValidationStatus.REJECTED,
    }
)


def summarize_clauses(
    rows: Sequence[ClauseComparisonResult],
) -> tuple[ComparisonSummary, dict[str, int]]:
    """Count UNCHANGED/MODIFIED/ADDED/REMOVED from aggregated clause rows."""
    unchanged = modified = added = removed = unresolved = 0
    for row in rows:
        if row.status is DiffClassification.UNCHANGED:
            unchanged += 1
        elif row.status is DiffClassification.MODIFIED:
            modified += 1
        elif row.status is DiffClassification.ADDED:
            added += 1
        elif row.status is DiffClassification.REMOVED:
            removed += 1
        else:
            unresolved += 1
    summary = ComparisonSummary(
        total_clauses=unchanged + modified + added + removed,
        unchanged=unchanged,
        modified=modified,
        added=added,
        removed=removed,
    )
    return summary, {"unresolved": unresolved}


def build_comparison_report(
    *,
    diff: DiffResult,
    exact: ExactDiffResult,
    scores: RiskScoringResult,
    bindings: EvidenceBindingResult,
    verification: ComparisonVerificationResult,
    taxonomy: TaxonomyResult | None = None,
    mapping: MappingResult | None = None,
    explanations: Sequence[ValidatedLLMResult] = (),
    workspace_id: UUID | None = None,
    source_title: str | None = None,
    target_title: str | None = None,
    comparison_id: UUID | None = None,
    processing_time_ms: int = 0,
    llm_calls: int = 0,
    llm_tokens: int = 0,
    metadata: dict[str, Any] | None = None,
) -> AuditableComparisonReport:
    """Aggregate pipeline outputs. Classification is copied from CMP-04."""
    score_index = _index_scores(scores)
    exact_index = _index_exact(exact)
    bind_index = _index_bindings(bindings)
    verify_index = _index_verification(verification)
    explain_index = _index_explanations(explanations)
    taxonomy_index = _index_taxonomy(taxonomy)

    buckets = empty_clause_buckets()
    rows: list[ClauseComparisonResult] = []
    for item in diff.diffs:
        row = _clause_result(
            item,
            scores=score_index,
            exact=exact_index,
            bindings=bind_index,
            verification=verify_index,
            explanations=explain_index,
            taxonomy=taxonomy_index,
        )
        buckets[bucket_name(row.status)].append(row)
        rows.append(row)

    summary, extra = summarize_clauses(rows)
    risk_counts = empty_risk_counts()
    risk_rows: list[dict[str, Any]] = []
    for score in scores.scores:
        if score.status is RiskStatus.NOT_APPLICABLE:
            continue
        if score.diff_classification is DiffClassification.UNCHANGED:
            continue
        assignment = None
        if score.identity_key:
            assignment = taxonomy_index.get(score.identity_key)
        payload = _risk_payload(score, assignment=assignment)
        risk_rows.append(payload)
        level = score.risk_level.value.lower()
        if level in risk_counts:
            risk_counts[level] += 1

    citations = _collect_citations(rows)
    verified_findings = sum(
        1 for item in verification.findings if item.status in _VERIFIED
    )
    finding_total = len(verification.findings)
    verification_rate = (
        round(verified_findings / finding_total, 4) if finding_total else 1.0
    )
    incomplete = any(item.status in _LLM_INCOMPLETE for item in explanations)
    mapped = 0
    if mapping is not None:
        mapped = int(mapping.metadata.get("exact_mappings") or 0) + int(
            mapping.metadata.get("high_confidence_mappings") or 0
        ) + int(mapping.metadata.get("medium_confidence_mappings") or 0)
    else:
        mapped = int(diff.metadata.get("mapped_count") or 0)

    statistics = ComparisonStatistics(
        total_clauses_compared=summary.total_clauses,
        unchanged=summary.unchanged,
        modified=summary.modified,
        added=summary.added,
        removed=summary.removed,
        unresolved=int(extra["unresolved"]),
        mapped_clauses=mapped,
        risk_counts=risk_counts,
        llm_calls=llm_calls,
        llm_tokens=llm_tokens,
        processing_time_ms=processing_time_ms,
        verification_rate=verification_rate,
        citation_verification_rate=verification_rate,
    )
    return AuditableComparisonReport(
        comparison_id=comparison_id or uuid4(),
        workspace_id=workspace_id,
        document_v1=DocumentRef(
            document_id=diff.source_document_id,
            document_version_id=diff.source_version_id,
            title=source_title,
            workspace_id=workspace_id,
        ),
        document_v2=DocumentRef(
            document_id=diff.target_document_id,
            document_version_id=diff.target_version_id,
            title=target_title,
            workspace_id=workspace_id,
        ),
        created_at=datetime.now(UTC),
        status=(
            ReportStatus.PARTIAL_EXPLANATION
            if incomplete
            else ReportStatus.COMPLETED
        ),
        summary=summary,
        statistics=statistics,
        clauses=buckets,
        risks=risk_rows,
        citations=citations,
        explanation_incomplete=incomplete,
        metadata=dict(metadata or {}),
    )


def _clause_result(
    diff: ClauseDiff,
    *,
    scores: dict[str, RiskScoreResult],
    exact: dict[str, list[dict[str, Any]]],
    bindings: dict[str, FindingEvidence],
    verification: dict[str, FindingVerification],
    explanations: dict[str, ValidatedLLMResult],
    taxonomy: dict[str, TaxonomyAssignment],
) -> ClauseComparisonResult:
    key = _identity_key(diff)
    v1_id = (
        diff.source_unit.identity_key
        if diff.source_unit is not None
        else (diff.source_ref.identity_key if diff.source_ref else None)
    )
    v2_id = (
        diff.target_unit.identity_key
        if diff.target_unit is not None
        else (diff.target_ref.identity_key if diff.target_ref else None)
    )
    if diff.classification is DiffClassification.ADDED:
        v1_id = None
    elif diff.classification is DiffClassification.REMOVED:
        v2_id = None

    score = _lookup_score(key, v1_id, v2_id, scores)
    binding = _lookup_binding(key, v1_id, v2_id, bindings)
    verified = _lookup_verification(key, v1_id, v2_id, verification)
    explained = _lookup_explanation(key, binding, explanations)

    evidence_rows = [item.as_dict() for item in (binding.evidence if binding else [])]
    if diff.classification is DiffClassification.ADDED:
        evidence_rows = [item for item in evidence_rows if item.get("side") != "OLD"]
    elif diff.classification is DiffClassification.REMOVED:
        evidence_rows = [item for item in evidence_rows if item.get("side") != "NEW"]

    citations: list[dict[str, Any]] = []
    if verified is not None:
        allowed = set(verified.verified_evidence_ids)
        citations = [
            item for item in evidence_rows if item.get("evidence_id") in allowed
        ]

    explanation_payload: dict[str, Any] | None = None
    if explained is not None:
        explanation_payload = {
            "status": explained.status.value,
            "reasons": [item.value for item in explained.reasons],
            "output": explained.output.as_dict() if explained.output else None,
            "llm_calls": explained.llm_calls,
        }
        if explained.status in _LLM_INCOMPLETE:
            explanation_payload["unavailable"] = True

    return ClauseComparisonResult(
        clause_id=key,
        v1_clause_id=v1_id,
        v2_clause_id=v2_id,
        status=diff.classification,
        mapping_confidence=(
            None
            if diff.mapping_confidence is None
            else round(diff.mapping_confidence, 4)
        ),
        subtree_status=diff.subtree_classification,
        exact_differences=list(exact.get(key, [])),
        risk=(
            _risk_payload(
                score,
                assignment=_lookup_taxonomy(key, v1_id, v2_id, taxonomy),
                rule_id=binding.rule_id if binding is not None else None,
            )
            if score is not None
            else None
        ),
        explanation=explanation_payload,
        evidence=evidence_rows,
        citations=citations,
        verification=verified.as_dict() if verified is not None else None,
        v1_text=diff.source_unit.original_text if diff.source_unit else None,
        v2_text=diff.target_unit.original_text if diff.target_unit else None,
        v1_normalized=diff.source_unit.normalized_body if diff.source_unit else None,
        v2_normalized=diff.target_unit.normalized_body if diff.target_unit else None,
        finding_id=binding.finding_id if binding is not None else (
            verified.finding_id if verified is not None else None
        ),
    )


def _identity_key(diff: ClauseDiff) -> str:
    if diff.source_unit is not None and diff.source_unit.identity_key:
        return diff.source_unit.identity_key
    if diff.target_unit is not None and diff.target_unit.identity_key:
        return diff.target_unit.identity_key
    if diff.source_ref is not None and diff.source_ref.identity_key:
        return diff.source_ref.identity_key
    if diff.target_ref is not None and diff.target_ref.identity_key:
        return diff.target_ref.identity_key
    if diff.source_ref is not None and diff.source_ref.source_id:
        return diff.source_ref.source_id
    if diff.target_ref is not None and diff.target_ref.source_id:
        return diff.target_ref.source_id
    return "UNKNOWN"


def _index_scores(scores: RiskScoringResult) -> dict[str, RiskScoreResult]:
    index: dict[str, RiskScoreResult] = {}
    for row in scores.scores:
        if row.identity_key:
            index.setdefault(row.identity_key, row)
        if row.source_ref and row.source_ref.identity_key:
            index.setdefault(row.source_ref.identity_key, row)
        if row.target_ref and row.target_ref.identity_key:
            index.setdefault(row.target_ref.identity_key, row)
    return index


def _index_exact(exact: ExactDiffResult) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for change in exact.changes:
        keys: list[str] = []
        if change.source_ref and change.source_ref.identity_key:
            keys.append(change.source_ref.identity_key)
        if change.target_ref and change.target_ref.identity_key:
            keys.append(change.target_ref.identity_key)
        payload = change.as_dict()
        for key in dict.fromkeys(keys):
            index.setdefault(key, []).append(payload)
    return index


def _index_bindings(bindings: EvidenceBindingResult) -> dict[str, FindingEvidence]:
    index: dict[str, FindingEvidence] = {}
    for row in bindings.bindings:
        if row.identity_key:
            index.setdefault(row.identity_key, row)
        index.setdefault(row.finding_id, row)
    return index


def _index_verification(
    verification: ComparisonVerificationResult,
) -> dict[str, FindingVerification]:
    index: dict[str, FindingVerification] = {}
    for row in verification.findings:
        if row.identity_key:
            index.setdefault(row.identity_key, row)
        index.setdefault(row.finding_id, row)
    return index


def _index_explanations(
    explanations: Sequence[ValidatedLLMResult],
) -> dict[str, ValidatedLLMResult]:
    index: dict[str, ValidatedLLMResult] = {}
    for row in explanations:
        index.setdefault(row.facts.finding_id, row)
        if row.facts.identity_key:
            index.setdefault(row.facts.identity_key, row)
    return index


def _lookup_score(
    key: str,
    v1_id: str | None,
    v2_id: str | None,
    scores: dict[str, RiskScoreResult],
) -> RiskScoreResult | None:
    for candidate in (key, v1_id, v2_id):
        if candidate and candidate in scores:
            return scores[candidate]
    return None


def _lookup_binding(
    key: str,
    v1_id: str | None,
    v2_id: str | None,
    bindings: dict[str, FindingEvidence],
) -> FindingEvidence | None:
    for candidate in (key, v1_id, v2_id):
        if candidate and candidate in bindings:
            return bindings[candidate]
    return None


def _lookup_verification(
    key: str,
    v1_id: str | None,
    v2_id: str | None,
    verification: dict[str, FindingVerification],
) -> FindingVerification | None:
    for candidate in (key, v1_id, v2_id):
        if candidate and candidate in verification:
            return verification[candidate]
    return None


def _index_taxonomy(
    taxonomy: TaxonomyResult | None,
) -> dict[str, TaxonomyAssignment]:
    index: dict[str, TaxonomyAssignment] = {}
    if taxonomy is None:
        return index
    for row in taxonomy.assignments:
        if row.identity_key:
            index.setdefault(row.identity_key, row)
        if row.source_ref and row.source_ref.identity_key:
            index.setdefault(row.source_ref.identity_key, row)
        if row.target_ref and row.target_ref.identity_key:
            index.setdefault(row.target_ref.identity_key, row)
    return index


def _lookup_taxonomy(
    key: str,
    v1_id: str | None,
    v2_id: str | None,
    taxonomy: dict[str, TaxonomyAssignment],
) -> TaxonomyAssignment | None:
    for candidate in (key, v1_id, v2_id):
        if candidate and candidate in taxonomy:
            return taxonomy[candidate]
    return None


def _lookup_explanation(
    key: str,
    binding: FindingEvidence | None,
    explanations: dict[str, ValidatedLLMResult],
) -> ValidatedLLMResult | None:
    if binding is not None and binding.finding_id in explanations:
        return explanations[binding.finding_id]
    return explanations.get(key)


def _risk_payload(
    score: RiskScoreResult,
    *,
    assignment: TaxonomyAssignment | None = None,
    rule_id: str | None = None,
) -> dict[str, Any]:
    rules: list[str] = []
    if rule_id:
        rules.append(rule_id)
    if assignment is not None and assignment.rule_id:
        rules.append(assignment.rule_id)
    for item in score.pending_adjustments:
        rules.append(item.rule_id)
    unique_rules = list(dict.fromkeys(item for item in rules if item))
    reason = None
    if assignment is not None and assignment.matched_signals:
        reason = ", ".join(assignment.matched_signals)
    return {
        "risk_category": score.category.value,
        "risk_level": score.risk_level.value,
        "risk_score": score.as_dict()["risk_score"],
        "risk_impact": score.risk_impact.value,
        "status": score.status.value,
        "triggered_rules": unique_rules,
        "identity_key": score.identity_key,
        "reason": reason or score.category.value,
    }


def _collect_citations(
    rows: Sequence[ClauseComparisonResult],
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    citations: list[dict[str, Any]] = []
    for row in rows:
        for item in row.citations:
            evidence_id = item.get("evidence_id")
            if not isinstance(evidence_id, str) or evidence_id in seen:
                continue
            seen.add(evidence_id)
            citations.append(item)
    return citations
