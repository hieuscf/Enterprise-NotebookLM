# =============================================================================
# File: llm_boundary_engine.py
# Module/Service: Deterministic / LLM Separation (FR8 / TASK-CMP-12)
# Layer: Service
# Purpose: Assemble frozen LLM context and validate LLM output against facts.
# Responsibilities:
#   - Join CMP-08/10/11 into ComparisonLLMContext (verified evidence only as facts)
#   - Validate schema, evidence_ids, fact immutability, absence/numeric/page claims
#   - Never retrieve, score, verify citations, or call an LLM
# Dependencies:
#   - llm_boundary_types, llm_boundary_prompt, CMP-08/10/11 types
# Public Exports:
#   - assemble_llm_context, assemble_llm_contexts, context_hash_for,
#     validate_llm_output, apply_llm_output
# Database/Table: N/A
# Related Modules: ComparisonLLMBoundary; FR8 ComparisonService unchanged
# Important Notes:
#   - 0 retrieval. LLM is optional and never the source of truth.
# =============================================================================

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from app.ai.document_structure.evidence_types import (
    EvidenceBindingResult,
    EvidenceRef,
    FindingEvidence,
)
from app.ai.document_structure.exact_types import ExactChange, ExactDiffResult
from app.ai.document_structure.llm_boundary_prompt import build_comparison_llm_prompts
from app.ai.document_structure.llm_output_schema import (
    StructuredComparisonExplanation,
    parse_structured_llm_output,
)
from app.ai.document_structure.llm_boundary_types import (
    INSUFFICIENT_NEW_ABSENCE_PHRASE,
    INSUFFICIENT_OLD_ABSENCE_PHRASE,
    PROMPT_VERSION,
    ClaimSupport,
    ComparisonLLMContext,
    ComparisonLLMOutput,
    DeterministicFacts,
    LLMClaim,
    LLMEvidenceItem,
    LLMTask,
    LLMValidationReason,
    ValidatedLLMResult,
    ValidationStatus,
)
from app.ai.document_structure.scoring_types import RiskScoreResult, RiskScoringResult
from app.ai.document_structure.verification_types import (
    AbsenceStatus,
    ComparisonVerificationResult,
    EvidenceCheckStatus,
    FindingVerification,
    VerificationStatus,
)

_ECHO_REJECT = (
    LLMValidationReason.INVALID_DETERMINISTIC_FACT_OVERRIDE,
    LLMValidationReason.INVALID_CLAUSE_REFERENCE,
    LLMValidationReason.INVALID_FINDING_REFERENCE,
    LLMValidationReason.INVALID_ENUM,
)
_ABSENCE_FORBIDDEN = (
    "không tồn tại",
    "v1 không có",
    "v2 không có",
    "does not contain",
    "did not exist",
    "no longer contains",
    "had no clause",
)
_PAGE_RE = re.compile(r"\b(?:page|trang)\s+(\d+)\b", re.IGNORECASE)
_CLAUSE_RE = re.compile(
    r"\b(?:điều|dieu|clause|article)\s+(\d+(?:\.\d+)*)\b",
    re.IGNORECASE,
)
_VERSION_RE = re.compile(r"\b(?:v|version[-_ ]?)(\d+)\b", re.IGNORECASE)
_NUMBER_RE = re.compile(r"(?<![\d])(\d{1,3}(?:[.,]\d{3})+|\d+)(?![\d])")
_VN_MILLION_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*triệu", re.IGNORECASE)
_VN_THOUSAND_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:nghìn|ngàn)", re.IGNORECASE)


def context_hash_for(
    facts: DeterministicFacts,
    verified_ids: Sequence[str],
    *,
    prompt_version: str = PROMPT_VERSION,
) -> str:
    payload = {
        "facts": facts.as_dict(),
        "verified_ids": list(verified_ids),
        "prompt_version": prompt_version,
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def assemble_llm_context(
    verification: FindingVerification,
    binding: FindingEvidence | None = None,
    score: RiskScoreResult | None = None,
    changes: Sequence[ExactChange] = (),
    *,
    source_document_id: UUID | None = None,
    target_document_id: UUID | None = None,
    source_version_id: UUID | None = None,
    target_version_id: UUID | None = None,
    task: LLMTask = LLMTask.NONE,
) -> ComparisonLLMContext:
    """Build one frozen context. INVALID evidence is never factual input."""
    refs = {item.evidence_id: item for item in (binding.evidence if binding else [])}
    verified: list[LLMEvidenceItem] = []
    uncertain: list[LLMEvidenceItem] = []
    for row in verification.evidence_results:
        ref = refs.get(row.evidence_id)
        item = _evidence_item(row.evidence_id, row.side.value, row.status.value, ref)
        if (
            row.status is EvidenceCheckStatus.VALID
            and verification.status is not VerificationStatus.INVALID
        ):
            verified.append(item)
        else:
            uncertain.append(item)

    old_value, new_value = _values(changes, verified)
    facts = DeterministicFacts(
        finding_id=verification.finding_id,
        identity_key=verification.identity_key or (binding.identity_key if binding else None),
        change_type=(
            verification.diff_classification.value
            if verification.diff_classification
            else (binding.diff_classification.value if binding and binding.diff_classification else None)
        ),
        risk_category=score.category.value if score and score.category else (
            binding.category.value if binding and binding.category else None
        ),
        risk_score=float(score.risk_score) if score is not None else None,
        risk_level=score.risk_level.value if score is not None else None,
        rule_id=verification.rule_id or (binding.rule_id if binding else None),
        old_document_id=source_document_id,
        new_document_id=target_document_id,
        old_document_version_id=source_version_id,
        new_document_version_id=target_version_id,
        old_value=old_value,
        new_value=new_value,
        verification_status=verification.status.value,
        absence_status=verification.absence_status.value,
        absence_message=verification.human_message,
        evidence_state=verification.status.value,
        reasons=tuple(item.value for item in verification.reasons),
    )
    digest = context_hash_for(facts, [item.evidence_id for item in verified])
    return ComparisonLLMContext(
        facts=facts,
        verified_evidence=tuple(verified),
        uncertain_evidence=tuple(uncertain),
        allowed_task=task,
        prompt_version=PROMPT_VERSION,
        context_hash=digest,
    )


def assemble_llm_contexts(
    verification: ComparisonVerificationResult,
    bindings: EvidenceBindingResult | None = None,
    scores: RiskScoringResult | None = None,
    exact: ExactDiffResult | None = None,
    *,
    task: LLMTask = LLMTask.NONE,
) -> list[ComparisonLLMContext]:
    bound = {row.finding_id: row for row in (bindings.bindings if bindings else [])}
    if bindings:
        for row in bindings.bindings:
            if row.identity_key and row.identity_key not in bound:
                bound[row.identity_key] = row
    scored = {row.identity_key: row for row in (scores.scores if scores else []) if row.identity_key}
    changes = _index_changes(exact)
    rows: list[ComparisonLLMContext] = []
    for item in verification.findings:
        binding = bound.get(item.finding_id) or (
            bound.get(item.identity_key) if item.identity_key else None
        )
        score = scored.get(item.identity_key) if item.identity_key else None
        key_changes = changes.get(item.identity_key or "", ())
        rows.append(
            assemble_llm_context(
                item,
                binding,
                score,
                key_changes,
                source_document_id=verification.source_document_id,
                target_document_id=verification.target_document_id,
                source_version_id=verification.source_version_id,
                target_version_id=verification.target_version_id,
                task=task,
            )
        )
    return rows


def validate_llm_output(
    context: ComparisonLLMContext,
    payload: Mapping[str, Any] | str | None,
    *,
    llm_calls: int = 1,
) -> ValidatedLLMResult:
    """Validate LLM JSON. Facts in the result are always the pre-LLM facts."""
    if payload is None:
        return _result(
            context,
            ValidationStatus.REJECTED,
            None,
            (LLMValidationReason.SCHEMA_INVALID,),
            llm_calls=llm_calls,
        )
    parsed, parse_reason = _parse_schema(payload)
    if parsed is None:
        return _result(
            context,
            ValidationStatus.REJECTED,
            None,
            (parse_reason or LLMValidationReason.SCHEMA_INVALID,),
            llm_calls=llm_calls,
        )

    reasons: list[LLMValidationReason] = []
    reasons.extend(_echo_reasons(context, parsed))
    claim_ids = [item for row in parsed.claims for item in row.evidence_ids]
    all_ids = list(dict.fromkeys([*parsed.evidence_ids, *claim_ids]))
    if any(item not in context.allowed_evidence_ids for item in all_ids):
        return _result(
            context,
            ValidationStatus.REJECTED,
            None,
            tuple(dict.fromkeys([*reasons, LLMValidationReason.UNKNOWN_EVIDENCE_ID])),
            llm_calls=llm_calls,
        )
    claims = tuple(
        LLMClaim(
            text=row.text,
            evidence_ids=tuple(row.evidence_ids),
            support_status=(
                ClaimSupport.SUPPORTED if row.evidence_ids else ClaimSupport.UNSUPPORTED
            ),
        )
        for row in parsed.claims
    )
    output = ComparisonLLMOutput(
        finding_id=context.facts.finding_id,
        identity_key=context.facts.identity_key,
        change_type=context.facts.change_type,
        risk_level=context.facts.risk_level,
        risk_category=context.facts.risk_category,
        explanation=parsed.explanation,
        legal_significance=parsed.legal_significance,
        business_impact=parsed.business_impact,
        recommendation=parsed.recommendation,
        uncertainty=(
            parsed.uncertainty.value
            if parsed.uncertainty
            else _default_uncertainty_code(context)
        ),
        evidence_ids=tuple(item for item in all_ids if item in context.allowed_evidence_ids),
        claims=claims,
    )
    claimed = " ".join(
        part
        for part in (
            output.explanation,
            output.legal_significance,
            output.business_impact,
            output.recommendation,
            parsed.uncertainty.value if parsed.uncertainty else None,
            *(item.text for item in claims),
        )
        if part
    )
    reasons.extend(_absence_reasons(context, claimed))
    reasons.extend(_numeric_reasons(context, claimed))
    reasons.extend(_page_reasons(context, claimed))
    reasons.extend(_clause_reasons(context, claimed))
    reasons.extend(_version_reasons(context, claimed))

    unique = tuple(dict.fromkeys(reasons))
    if any(item in unique for item in _ECHO_REJECT):
        return _result(context, ValidationStatus.REJECTED, None, unique, llm_calls=llm_calls)
    if LLMValidationReason.UNSUPPORTED_ABSENCE_CLAIM in unique:
        return _result(context, ValidationStatus.REJECTED, None, unique, llm_calls=llm_calls)
    if LLMValidationReason.UNKNOWN_EVIDENCE_ID in unique:
        return _result(context, ValidationStatus.REJECTED, None, unique, llm_calls=llm_calls)
    if unique:
        return _result(context, ValidationStatus.FLAGGED, output, unique, llm_calls=llm_calls)
    return _result(
        context,
        ValidationStatus.ACCEPTED,
        output,
        (LLMValidationReason.VALID,),
        llm_calls=llm_calls,
    )


def apply_llm_output(
    context: ComparisonLLMContext,
    generate,
) -> ValidatedLLMResult:
    """Call ``generate(system, user)`` once. On failure, keep deterministic facts."""
    if context.allowed_task is LLMTask.NONE:
        return _result(
            context,
            ValidationStatus.SKIPPED,
            None,
            (LLMValidationReason.TASK_DISABLED,),
            llm_calls=0,
        )
    system, user = build_comparison_llm_prompts(context)
    try:
        raw = generate(system, user)
    except Exception:
        return _result(
            context,
            ValidationStatus.FAILED,
            None,
            (LLMValidationReason.GENERATION_FAILED,),
            llm_calls=1,
        )
    return validate_llm_output(context, raw, llm_calls=1)


def _evidence_item(
    evidence_id: str,
    side: str,
    status: str,
    ref: EvidenceRef | None,
) -> LLMEvidenceItem:
    return LLMEvidenceItem(
        evidence_id=evidence_id,
        side=side,
        verification_status=status,
        document_id=ref.document_id if ref else None,
        document_version_id=ref.document_version_id if ref else None,
        clause_id=ref.clause_id if ref else None,
        identity_key=ref.identity_key if ref else None,
        chunk_id=ref.chunk_id if ref else None,
        page_number=ref.page_number if ref else None,
        start_offset=ref.start_offset if ref else None,
        end_offset=ref.end_offset if ref else None,
        text=ref.display_text if ref and status == EvidenceCheckStatus.VALID.value else None,
    )


def _values(
    changes: Sequence[ExactChange],
    verified: Sequence[LLMEvidenceItem],
) -> tuple[str | None, str | None]:
    old = new = None
    for change in changes:
        if change.old_value and old is None:
            old = change.old_value.raw_text
        if change.new_value and new is None:
            new = change.new_value.raw_text
    if old is None:
        old = next((item.text for item in verified if item.side == "OLD" and item.text), None)
    if new is None:
        new = next((item.text for item in verified if item.side == "NEW" and item.text), None)
    return old, new


def _index_changes(exact: ExactDiffResult | None) -> dict[str, list[ExactChange]]:
    grouped: dict[str, list[ExactChange]] = {}
    if exact is None:
        return grouped
    for change in exact.changes:
        for ref in (change.source_ref, change.target_ref):
            if ref and ref.identity_key:
                grouped.setdefault(ref.identity_key, []).append(change)
                break
    return grouped


def _parse_schema(
    payload: Mapping[str, Any] | str,
) -> tuple[StructuredComparisonExplanation | None, LLMValidationReason | None]:
    try:
        return parse_structured_llm_output(payload), None
    except ValidationError as exc:
        if any(error.get("type") == "enum" for error in exc.errors()):
            return None, LLMValidationReason.INVALID_ENUM
        return None, LLMValidationReason.SCHEMA_INVALID
    except (ValueError, TypeError, json.JSONDecodeError):
        return None, LLMValidationReason.SCHEMA_INVALID


def _echo_reasons(
    context: ComparisonLLMContext,
    parsed: StructuredComparisonExplanation,
) -> list[LLMValidationReason]:
    facts = context.facts
    reasons: list[LLMValidationReason] = []
    if parsed.finding_id and parsed.finding_id != facts.finding_id:
        reasons.append(LLMValidationReason.INVALID_FINDING_REFERENCE)
    if parsed.identity_key and facts.identity_key and parsed.identity_key != facts.identity_key:
        reasons.append(LLMValidationReason.INVALID_CLAUSE_REFERENCE)
    if parsed.clause_id and not _clause_matches(parsed.clause_id, facts.identity_key):
        reasons.append(LLMValidationReason.INVALID_CLAUSE_REFERENCE)
    if parsed.change_type and facts.change_type and parsed.change_type.value != facts.change_type:
        reasons.append(LLMValidationReason.INVALID_DETERMINISTIC_FACT_OVERRIDE)
    if parsed.risk_level and facts.risk_level and parsed.risk_level.value != facts.risk_level:
        reasons.append(LLMValidationReason.INVALID_DETERMINISTIC_FACT_OVERRIDE)
    if parsed.risk_category and facts.risk_category:
        if parsed.risk_category.value != facts.risk_category:
            reasons.append(LLMValidationReason.INVALID_DETERMINISTIC_FACT_OVERRIDE)
    if parsed.rule_id and facts.rule_id and parsed.rule_id != facts.rule_id:
        reasons.append(LLMValidationReason.INVALID_DETERMINISTIC_FACT_OVERRIDE)
    if parsed.risk_score is not None and facts.risk_score is not None:
        if abs(float(parsed.risk_score) - float(facts.risk_score)) > 0.05:
            reasons.append(LLMValidationReason.INVALID_DETERMINISTIC_FACT_OVERRIDE)
    return reasons


def _clause_matches(claimed: str, identity_key: str | None) -> bool:
    token = claimed.strip()
    if not token or not identity_key:
        return False
    if token == identity_key:
        return True
    number = identity_key.split(":", 1)[-1]
    return token == number or token.casefold() == f"clause:{number}".casefold()


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _claims(
    raw: Any, allowed: frozenset[str]
) -> tuple[tuple[LLMClaim, ...], LLMValidationReason | None]:
    if raw is None:
        return (), None
    if not isinstance(raw, list):
        return (), LLMValidationReason.SCHEMA_INVALID
    rows: list[LLMClaim] = []
    for item in raw:
        if not isinstance(item, Mapping):
            return (), LLMValidationReason.SCHEMA_INVALID
        ids = tuple(str(value).strip() for value in (item.get("evidence_ids") or []) if str(value).strip())
        if any(evidence_id not in allowed for evidence_id in ids):
            return (), LLMValidationReason.UNKNOWN_EVIDENCE_ID
        text = _text(item.get("text")) or ""
        rows.append(
            LLMClaim(
                text=text,
                evidence_ids=ids,
                support_status=ClaimSupport.SUPPORTED if ids else ClaimSupport.UNSUPPORTED,
            )
        )
    return tuple(rows), None


def _default_uncertainty_code(context: ComparisonLLMContext) -> str | None:
    if context.facts.verification_status == VerificationStatus.INSUFFICIENT_EVIDENCE.value:
        return "INSUFFICIENT_EVIDENCE"
    if context.facts.absence_status == AbsenceStatus.INSUFFICIENT_EVIDENCE.value:
        return "INSUFFICIENT_EVIDENCE"
    return None


def _absence_reasons(context: ComparisonLLMContext, prose: str) -> list[LLMValidationReason]:
    if context.facts.absence_status == AbsenceStatus.ABSENCE_CONFIRMED.value:
        return []
    folded = prose.casefold()
    if any(phrase in folded for phrase in _ABSENCE_FORBIDDEN):
        if INSUFFICIENT_OLD_ABSENCE_PHRASE.casefold() in folded:
            return []
        if INSUFFICIENT_NEW_ABSENCE_PHRASE.casefold() in folded:
            return []
        return [LLMValidationReason.UNSUPPORTED_ABSENCE_CLAIM]
    return []


def _allowed_numbers(context: ComparisonLLMContext) -> set[str]:
    values: list[str] = []
    facts = context.facts
    for raw in (facts.old_value, facts.new_value, str(facts.risk_score) if facts.risk_score is not None else None):
        if raw:
            values.append(raw)
    for item in context.verified_evidence:
        if item.text:
            values.append(item.text)
    allowed: set[str] = set()
    for raw in values:
        for match in _NUMBER_RE.findall(raw):
            allowed.add(_normalize_number(match))
        for match in _VN_MILLION_RE.findall(raw):
            allowed.add(_normalize_number(str(float(match.replace(",", ".")) * 1_000_000)))
    allowed.discard("")
    return allowed


def _numeric_reasons(context: ComparisonLLMContext, prose: str) -> list[LLMValidationReason]:
    allowed = _allowed_numbers(context)
    if not allowed:
        return []
    found: set[str] = set()
    for match in _NUMBER_RE.findall(prose):
        found.add(_normalize_number(match))
    for match in _VN_MILLION_RE.findall(prose):
        found.add(_normalize_number(str(int(float(match.replace(",", ".")) * 1_000_000))))
    for match in _VN_THOUSAND_RE.findall(prose):
        found.add(_normalize_number(str(int(float(match.replace(",", ".")) * 1_000))))
    extras = {item for item in found if item and item not in allowed and _is_material_number(item)}
    if extras:
        return [LLMValidationReason.UNSUPPORTED_NUMERIC]
    return []


def _page_reasons(context: ComparisonLLMContext, prose: str) -> list[LLMValidationReason]:
    allowed = {
        str(item.page_number)
        for item in context.verified_evidence
        if item.page_number is not None
    }
    if not allowed:
        return []
    mentioned = {match for match in _PAGE_RE.findall(prose)}
    if mentioned - allowed:
        return [LLMValidationReason.UNSUPPORTED_PAGE]
    return []


def _clause_reasons(context: ComparisonLLMContext, prose: str) -> list[LLMValidationReason]:
    allowed: set[str] = set()
    if context.facts.identity_key and ":" in context.facts.identity_key:
        _add_clause_numbers(allowed, context.facts.identity_key.split(":", 1)[1])
    for item in context.verified_evidence:
        if item.identity_key and ":" in item.identity_key:
            _add_clause_numbers(allowed, item.identity_key.split(":", 1)[1])
    if not allowed:
        return []
    mentioned = {match for match in _CLAUSE_RE.findall(prose)}
    if mentioned - allowed:
        return [LLMValidationReason.UNSUPPORTED_CLAUSE]
    return []


def _version_reasons(context: ComparisonLLMContext, prose: str) -> list[LLMValidationReason]:
    allowed = {"1", "2"}
    mentioned = {match for match in _VERSION_RE.findall(prose)}
    if mentioned - allowed:
        return [LLMValidationReason.UNSUPPORTED_VERSION]
    return []


def _add_clause_numbers(allowed: set[str], number: str) -> None:
    allowed.add(number)
    if "." in number:
        allowed.add(number.split(".", 1)[0])


def _normalize_number(raw: str) -> str:
    compact = raw.replace(",", "").replace(" ", "")
    if compact.count(".") == 1 and len(compact.split(".")[-1]) <= 2:
        try:
            return str(int(float(compact)))
        except ValueError:
            return compact
    digits = compact.replace(".", "")
    digits = digits.lstrip("0") or "0"
    return digits if digits.isdigit() else compact


def _is_material_number(value: str) -> bool:
    try:
        number = int(value)
    except ValueError:
        return False
    return number >= 100


def _result(
    context: ComparisonLLMContext,
    status: ValidationStatus,
    output: ComparisonLLMOutput | None,
    reasons: tuple[LLMValidationReason, ...],
    *,
    llm_calls: int,
) -> ValidatedLLMResult:
    return ValidatedLLMResult(
        facts=context.facts,
        status=status,
        output=output,
        reasons=reasons,
        prompt_version=context.prompt_version,
        context_hash=context.context_hash,
        llm_calls=llm_calls,
        retrieval_calls=0,
        metadata={"allowed_task": context.allowed_task.value},
    )
