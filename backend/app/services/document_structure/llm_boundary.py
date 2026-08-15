# =============================================================================
# File: llm_boundary.py
# Module/Service: Deterministic / LLM Separation (FR8 / TASK-CMP-12)
# Layer: Service
# Purpose: Application wrapper for controlled comparison LLM context.
# Responsibilities:
#   - assemble(...) — frozen facts + verified evidence, 0 LLM
#   - validate(...) — schema / citation / immutability checks
#   - explain(...) — optional generate callback; failure keeps facts
#   - Log counts only — never raw contract text
# Dependencies:
#   - llm_boundary_engine, ComparisonCitationVerifier
# Public Exports:
#   - ComparisonLLMBoundary
# Database/Table: N/A (not message_generations; not comparison truth)
# Related Modules: FR8 ComparisonService remains the multi-doc similarities path
# Important Notes:
#   - Default path is no-LLM. Never retrieve, score, or verify citations.
# =============================================================================

from __future__ import annotations

from collections.abc import Callable

from app.ai.document_structure.evidence_types import EvidenceBindingResult
from app.ai.document_structure.exact_types import ExactDiffResult
from app.ai.document_structure.llm_boundary_engine import (
    apply_llm_output,
    assemble_llm_contexts,
    validate_llm_output,
)
from app.ai.document_structure.llm_output_schema import parse_structured_llm_output
from app.ai.document_structure.llm_boundary_prompt import build_comparison_llm_prompts
from app.ai.document_structure.llm_boundary_types import (
    ComparisonLLMContext,
    LLMTask,
    ValidatedLLMResult,
)
from app.ai.document_structure.scoring_types import RiskScoringResult
from app.ai.document_structure.verification_types import ComparisonVerificationResult
from app.core.logging import get_logger

logger = get_logger(__name__)

GenerateFn = Callable[[str, str], object]


class ComparisonLLMBoundary:
    """Gate between deterministic comparison facts and optional LLM wording."""

    def assemble(
        self,
        verification: ComparisonVerificationResult,
        bindings: EvidenceBindingResult | None = None,
        scores: RiskScoringResult | None = None,
        exact: ExactDiffResult | None = None,
        *,
        task: LLMTask = LLMTask.NONE,
    ) -> list[ComparisonLLMContext]:
        logger.info(
            "comparison_llm_boundary_assemble",
            finding_rows=len(verification.findings),
            allowed_task=task.value,
            llm_calls=0,
            retrieval_calls=0,
        )
        return assemble_llm_contexts(
            verification, bindings, scores, exact, task=task
        )

    def prompts(self, context: ComparisonLLMContext) -> tuple[str, str]:
        return build_comparison_llm_prompts(context)

    def parse(self, payload: object):
        return parse_structured_llm_output(payload)

    def validate(
        self,
        context: ComparisonLLMContext,
        payload: object,
        *,
        llm_calls: int = 1,
    ) -> ValidatedLLMResult:
        result = validate_llm_output(context, payload, llm_calls=llm_calls)
        logger.info(
            "comparison_llm_boundary_validated",
            finding_id=context.facts.finding_id,
            status=result.status.value,
            llm_calls=result.llm_calls,
            retrieval_calls=result.retrieval_calls,
        )
        return result

    def explain(
        self,
        context: ComparisonLLMContext,
        *,
        generate: GenerateFn | None = None,
    ) -> ValidatedLLMResult:
        if generate is None or context.allowed_task is LLMTask.NONE:
            return apply_llm_output(
                ComparisonLLMContext(
                    facts=context.facts,
                    verified_evidence=context.verified_evidence,
                    uncertain_evidence=context.uncertain_evidence,
                    allowed_task=LLMTask.NONE,
                    prompt_version=context.prompt_version,
                    context_hash=context.context_hash,
                ),
                lambda _system, _user: None,
            )
        return apply_llm_output(context, generate)
