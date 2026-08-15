# =============================================================================
# File: orchestrator.py
# Module/Service: Contract Comparison Orchestration (FR8 / TASK-CMP-15)
# Layer: Service
# Purpose: End-to-end coordinator for the deterministic contract-comparison
#   pipeline and auditable report. Reuses CMP-01..13; does not reimplement them.
# Responsibilities:
#   - Validate workspace / document pair / ingestion readiness
#   - Run structure → normalize → map → diff → exact → taxonomy → score
#     → evidence → citation verify → optional LLM explanation
#   - Aggregate a report; log counts only (never contract body / PII)
#   - Apply CMP-16 quality gate; record in-process comparison metrics
# Dependencies:
#   - DocumentStructureExtractor and CMP-02..13 service wrappers
#   - report_engine.build_comparison_report; evaluation_engine.apply_quality_gate
# Public Exports:
#   - ContractComparisonError, ContractComparisonOrchestrator
# Database/Table: documents, document_versions, document_chunks (read-only)
# Related Modules: FR8 ComparisonService (similarities/differences) is unchanged
# Important Notes:
#   - Default LLM task is NONE (0 extra LLM calls). CMP-14 optimizer is absent.
#   - Clause existence uses the full CMP-01/02 inventory, never top-k retrieval.
#   - Does not write comparisons.result (OpenAPI extra=forbid similarities-only).
#   - Quality FAIL is attached to the report; critical stage errors still raise.
# =============================================================================

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Sequence

from app.ai.document_structure.diff_types import DiffClassification
from app.ai.document_structure.evidence_types import EvidenceContext, SourceRecord
from app.ai.document_structure.llm_boundary_types import (
    DeterministicFacts,
    LLMTask,
    LLMValidationReason,
    ValidatedLLMResult,
    ValidationStatus,
)
from app.ai.document_structure.evaluation_engine import apply_quality_gate
from app.ai.document_structure.normalization import NormalizedDocumentStructure
from app.ai.document_structure.quality_metrics import get_contract_comparison_metrics
from app.ai.document_structure.report_engine import build_comparison_report
from app.ai.document_structure.report_types import AuditableComparisonReport
from app.ai.document_structure.verification_engine import (
    catalog_from_structures,
    inventory_from_structures,
)
from app.ai.tokens import count_tokens
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.enums import DocumentVersionStatus
from app.repositories.documents import DocumentRepository
from app.services.document_structure.differ import ClauseDiffEngine
from app.services.document_structure.evidence import ClauseEvidenceBinder
from app.services.document_structure.exact import ClauseExactDiffEngine
from app.services.document_structure.extractor import (
    DocumentStructureError,
    DocumentStructureExtractor,
)
from app.services.document_structure.llm_boundary import ComparisonLLMBoundary
from app.services.document_structure.mapper import ClauseMappingEngine
from app.services.document_structure.scoring import RiskScoringEngine
from app.services.document_structure.taxonomy import LegalRiskTaxonomyEngine
from app.services.document_structure.verification import ComparisonCitationVerifier

logger = get_logger(__name__)

GenerateFn = Callable[[str, str], object]

_CONTENT_STATUSES = frozenset(
    {
        DiffClassification.MODIFIED,
        DiffClassification.ADDED,
        DiffClassification.REMOVED,
    }
)


class ContractComparisonError(Exception):
    """Domain error for the contract-comparison orchestrator."""

    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ContractComparisonOrchestrator:
    """Coordinate CMP-01..13 into one auditable comparison run."""

    def __init__(
        self,
        *,
        extractor: DocumentStructureExtractor | None = None,
        documents: DocumentRepository | None = None,
        mapper: ClauseMappingEngine | None = None,
        differ: ClauseDiffEngine | None = None,
        exact: ClauseExactDiffEngine | None = None,
        taxonomy: LegalRiskTaxonomyEngine | None = None,
        scoring: RiskScoringEngine | None = None,
        binder: ClauseEvidenceBinder | None = None,
        verifier: ComparisonCitationVerifier | None = None,
        llm_boundary: ComparisonLLMBoundary | None = None,
        max_llm_calls: int | None = None,
    ) -> None:
        self._extractor = extractor
        self._documents = documents
        if documents is None and extractor is not None:
            self._documents = getattr(extractor, "_documents", None)
        self._mapper = mapper or ClauseMappingEngine(extractor=extractor)
        self._differ = differ or ClauseDiffEngine(mapper=self._mapper, extractor=extractor)
        self._exact = exact or ClauseExactDiffEngine(differ=self._differ)
        self._taxonomy = taxonomy or LegalRiskTaxonomyEngine(differ=self._differ)
        self._scoring = scoring or RiskScoringEngine(differ=self._differ)
        self._binder = binder or ClauseEvidenceBinder(differ=self._differ)
        self._verifier = verifier or ComparisonCitationVerifier(
            differ=self._differ, binder=self._binder
        )
        self._llm = llm_boundary or ComparisonLLMBoundary()
        self._max_llm_calls = (
            max_llm_calls
            if max_llm_calls is not None
            else int(get_settings().contract_comparison_max_llm_calls)
        )

    def compare_structures(
        self,
        source: NormalizedDocumentStructure,
        target: NormalizedDocumentStructure,
        *,
        workspace_id: uuid.UUID | None = None,
        llm_task: LLMTask = LLMTask.NONE,
        generate: GenerateFn | None = None,
        sources: Sequence[SourceRecord] | None = None,
        comparison_id: uuid.UUID | None = None,
    ) -> AuditableComparisonReport:
        """Run the full pipeline on already-normalized clause inventories."""
        started = time.perf_counter()
        run_id = comparison_id or uuid.uuid4()
        scope = workspace_id or source.workspace_id or target.workspace_id
        try:
            self._validate_structures(source, target, workspace_id=scope)
        except ContractComparisonError:
            get_contract_comparison_metrics().record_failure()
            raise
        logger.info(
            "contract_comparison_started",
            comparison_id=str(run_id),
            workspace_id=str(scope) if scope else None,
            document_v1_id=str(source.document_id),
            document_v2_id=str(target.document_id),
            llm_task=llm_task.value,
        )
        context = EvidenceContext(
            workspace_id=scope,
            source_document_id=source.document_id,
            target_document_id=target.document_id,
            source_version_id=source.version_id,
            target_version_id=target.version_id,
        )
        chunk_sources = (
            list(sources) if sources is not None else _source_records(source, target)
        )
        stage_ms: dict[str, int] = {}

        try:
            mapping = self._timed_stage(
                stage_ms,
                "mapping",
                "mapping_failed",
                lambda: self._mapper.map_structures(source, target),
            )
            diff = self._timed_stage(
                stage_ms,
                "diff",
                "diff_failed",
                lambda: self._differ.diff_mapping(mapping),
            )
            exact = self._timed_stage(
                stage_ms,
                "exact",
                "diff_failed",
                lambda: self._exact.extract(diff),
            )
            taxonomy = self._timed_stage(
                stage_ms,
                "taxonomy",
                "risk_analysis_failed",
                lambda: self._taxonomy.classify(diff, exact),
            )
            scores = self._timed_stage(
                stage_ms,
                "scoring",
                "risk_analysis_failed",
                lambda: self._scoring.score(taxonomy, exact),
            )
            bindings = self._timed_stage(
                stage_ms,
                "evidence",
                "citation_verification_failed",
                lambda: self._binder.bind(
                    scores,
                    exact,
                    taxonomy,
                    context=context,
                    sources=chunk_sources,
                ),
            )
            verification = self._timed_stage(
                stage_ms,
                "verification",
                "citation_verification_failed",
                lambda: self._verifier.verify(
                    bindings,
                    context=context,
                    catalog=catalog_from_structures(source, target),
                    chunks=chunk_sources,
                    inventory=inventory_from_structures(source, target),
                    exact=exact,
                ),
            )
        except ContractComparisonError:
            get_contract_comparison_metrics().record_failure()
            raise

        llm_calls = 0
        llm_tokens = 0
        explanations: list[ValidatedLLMResult] = []
        llm_started = time.perf_counter()
        try:
            contexts = self._llm.assemble(
                verification,
                bindings,
                scores,
                exact,
                task=llm_task,
            )
            eligible = [
                item
                for item in contexts
                if _llm_eligible(item.facts.change_type, llm_task, generate)
            ]
            instrumented = _token_counter(generate) if generate is not None else None
            for item in eligible:
                result = self._llm.explain(
                    item,
                    generate=instrumented.fn if instrumented else None,
                )
                explanations.append(result)
                llm_calls += result.llm_calls
            if instrumented is not None:
                llm_tokens = instrumented.tokens
        except Exception:  # noqa: BLE001
            logger.warning(
                "contract_comparison_llm_failed",
                comparison_id=str(run_id),
                code="llm_provider_error",
            )
            explanations.append(_synthetic_llm_failure())
        stage_ms["llm"] = int((time.perf_counter() - llm_started) * 1000)

        duration_ms = int((time.perf_counter() - started) * 1000)
        report = build_comparison_report(
            diff=diff,
            exact=exact,
            scores=scores,
            bindings=bindings,
            verification=verification,
            taxonomy=taxonomy,
            mapping=mapping,
            explanations=explanations,
            workspace_id=scope,
            source_title=source.title,
            target_title=target.title,
            comparison_id=run_id,
            processing_time_ms=duration_ms,
            llm_calls=llm_calls,
            llm_tokens=llm_tokens,
            metadata={
                "source_clause_count": len(source.identity_keys()),
                "target_clause_count": len(target.identity_keys()),
                "mapping_llm_calls": mapping.metadata.get("mapping_llm_calls", 0),
                "diff_llm_calls": diff.metadata.get("diff_llm_calls", 0),
                "exact_diff_llm_calls": exact.metadata.get("exact_diff_llm_calls", 0),
                "retrieval_calls": 0,
                "performance": {
                    "total_ms": duration_ms,
                    "mapping_ms": stage_ms.get("mapping", mapping.metadata.get("mapping_latency_ms", 0)),
                    "diff_ms": stage_ms.get("diff", diff.metadata.get("diff_latency_ms", 0)),
                    "exact_ms": stage_ms.get("exact", exact.metadata.get("exact_diff_latency_ms", 0)),
                    "taxonomy_ms": stage_ms.get("taxonomy", taxonomy.metadata.get("taxonomy_latency_ms", 0)),
                    "scoring_ms": stage_ms.get("scoring", scores.metadata.get("scoring_latency_ms", 0)),
                    "evidence_ms": stage_ms.get("evidence", bindings.metadata.get("binding_latency_ms", 0)),
                    "verification_ms": stage_ms.get(
                        "verification",
                        verification.metadata.get("verification_latency_ms", 0),
                    ),
                    "llm_ms": stage_ms.get("llm", 0),
                },
            },
        )
        report = apply_quality_gate(report, max_llm_calls=self._max_llm_calls)
        get_contract_comparison_metrics().record_success(report)
        logger.info(
            "contract_comparison_completed",
            comparison_id=str(report.comparison_id),
            workspace_id=str(scope) if scope else None,
            document_v1_id=str(source.document_id),
            document_v2_id=str(target.document_id),
            total_clauses=report.summary.total_clauses,
            mapped_clauses=report.statistics.mapped_clauses,
            unchanged=report.summary.unchanged,
            modified=report.summary.modified,
            added=report.summary.added,
            removed=report.summary.removed,
            llm_calls=report.statistics.llm_calls,
            llm_tokens=report.statistics.llm_tokens,
            processing_duration=report.statistics.processing_time_ms,
            citation_verification_rate=report.statistics.citation_verification_rate,
            explanation_incomplete=report.explanation_incomplete,
            quality_status=report.quality_status.value,
            status=report.status.value,
        )
        return report

    async def compare_documents(
        self,
        *,
        workspace_id: uuid.UUID,
        source_document_id: uuid.UUID,
        target_document_id: uuid.UUID,
        source_version_id: uuid.UUID | None = None,
        target_version_id: uuid.UUID | None = None,
        llm_task: LLMTask = LLMTask.NONE,
        generate: GenerateFn | None = None,
        comparison_id: uuid.UUID | None = None,
    ) -> AuditableComparisonReport:
        """Load both versions from the workspace, then run compare_structures."""
        try:
            if self._extractor is None:
                raise ContractComparisonError(
                    "structure_not_available",
                    "DocumentStructureExtractor is required to load documents",
                    status_code=500,
                )
            self._validate_document_pair(
                source_document_id,
                target_document_id,
                source_version_id,
                target_version_id,
            )
            await self._require_ready_version(
                workspace_id=workspace_id,
                document_id=source_document_id,
                version_id=source_version_id,
            )
            await self._require_ready_version(
                workspace_id=workspace_id,
                document_id=target_document_id,
                version_id=target_version_id,
            )
            source = await self._extractor.extract_normalized(
                source_document_id,
                workspace_id=workspace_id,
                version_id=source_version_id,
            )
            target = await self._extractor.extract_normalized(
                target_document_id,
                workspace_id=workspace_id,
                version_id=target_version_id,
            )
        except DocumentStructureError as exc:
            get_contract_comparison_metrics().record_failure()
            raise ContractComparisonError(
                exc.code,
                exc.message,
                status_code=exc.status_code,
            ) from exc
        except ContractComparisonError:
            get_contract_comparison_metrics().record_failure()
            raise
        return self.compare_structures(
            source,
            target,
            workspace_id=workspace_id,
            llm_task=llm_task,
            generate=generate,
            comparison_id=comparison_id,
        )

    def _validate_document_pair(
        self,
        source_document_id: uuid.UUID,
        target_document_id: uuid.UUID,
        source_version_id: uuid.UUID | None,
        target_version_id: uuid.UUID | None,
    ) -> None:
        if (
            source_document_id == target_document_id
            and source_version_id == target_version_id
        ):
            raise ContractComparisonError(
                "invalid_document_pair",
                "Comparison requires two distinct document versions",
                status_code=400,
            )

    def _validate_structures(
        self,
        source: NormalizedDocumentStructure,
        target: NormalizedDocumentStructure,
        *,
        workspace_id: uuid.UUID | None,
    ) -> None:
        if source.document_id == target.document_id and source.version_id == target.version_id:
            raise ContractComparisonError(
                "invalid_document_pair",
                "Comparison requires two distinct document versions",
                status_code=400,
            )
        if (
            workspace_id is not None
            and source.workspace_id is not None
            and source.workspace_id != workspace_id
        ) or (
            workspace_id is not None
            and target.workspace_id is not None
            and target.workspace_id != workspace_id
        ):
            raise ContractComparisonError(
                "not_found",
                "Document not found",
                status_code=404,
            )
        if (
            source.workspace_id is not None
            and target.workspace_id is not None
            and source.workspace_id != target.workspace_id
        ):
            raise ContractComparisonError(
                "not_found",
                "Document not found",
                status_code=404,
            )
        if not source.identity_keys():
            raise ContractComparisonError(
                "clauses_not_available",
                "Source document has no comparable clauses",
                status_code=409,
            )
        if not target.identity_keys():
            raise ContractComparisonError(
                "clauses_not_available",
                "Target document has no comparable clauses",
                status_code=409,
            )

    async def _require_ready_version(
        self,
        *,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        version_id: uuid.UUID | None,
    ) -> None:
        if self._documents is None:
            return
        document = await self._documents.get_document(workspace_id, document_id)
        if document is None:
            raise ContractComparisonError(
                "not_found",
                f"Document {document_id} not found",
                status_code=404,
            )
        target = version_id or document.current_version_id
        if target is None:
            raise ContractComparisonError(
                "no_current_version",
                f"Document {document_id} has no current version",
                status_code=409,
            )
        version = await self._documents.get_version(workspace_id, document_id, target)
        if version is None:
            raise ContractComparisonError(
                "no_current_version",
                f"Version {target} for document {document_id} not found",
                status_code=409,
            )
        if version.status != DocumentVersionStatus.ready:
            raise ContractComparisonError(
                "version_not_ready",
                f"Document {document_id} current version is not ready",
                status_code=409,
            )

    def _timed_stage(self, stage_ms: dict[str, int], name: str, code: str, fn):
        started = time.perf_counter()
        result = self._run_stage(code, fn)
        stage_ms[name] = int((time.perf_counter() - started) * 1000)
        return result

    def _run_stage(self, code: str, fn):
        try:
            return fn()
        except ContractComparisonError:
            raise
        except Exception as exc:
            logger.warning("contract_comparison_stage_failed", code=code)
            raise ContractComparisonError(
                code,
                "Contract comparison pipeline stage failed",
                status_code=500,
            ) from exc


def _llm_eligible(
    change_type: str | None,
    task: LLMTask,
    generate: GenerateFn | None,
) -> bool:
    if generate is None or task is LLMTask.NONE:
        return False
    if change_type == DiffClassification.UNCHANGED.value:
        return False
    if change_type not in {item.value for item in _CONTENT_STATUSES}:
        return False
    return True


def _source_records(
    source: NormalizedDocumentStructure,
    target: NormalizedDocumentStructure,
) -> list[SourceRecord]:
    rows: list[SourceRecord] = []
    seen: set[uuid.UUID] = set()
    for structure in (source, target):
        if structure.version_id is None:
            continue
        for unit in structure.walk():
            for chunk_id in unit.chunk_ids:
                if chunk_id in seen:
                    continue
                seen.add(chunk_id)
                rows.append(
                    SourceRecord(
                        chunk_id=chunk_id,
                        document_id=structure.document_id,
                        document_version_id=structure.version_id,
                        workspace_id=structure.workspace_id,
                        page_number=unit.page_start,
                    )
                )
    return rows


class _TokenCounter:
    def __init__(self, generate: GenerateFn) -> None:
        self.tokens = 0
        self._generate = generate

    def fn(self, system: str, user: str) -> object:
        self.tokens += count_tokens(system) + count_tokens(user)
        raw = self._generate(system, user)
        if isinstance(raw, str):
            self.tokens += count_tokens(raw)
        return raw


def _token_counter(generate: GenerateFn) -> _TokenCounter:
    return _TokenCounter(generate)


def _synthetic_llm_failure() -> ValidatedLLMResult:
    facts = DeterministicFacts(
        finding_id="llm-failed",
        identity_key=None,
        change_type=None,
        risk_category=None,
        risk_score=None,
        risk_level=None,
        rule_id=None,
        old_document_id=None,
        new_document_id=None,
        old_document_version_id=None,
        new_document_version_id=None,
        old_value=None,
        new_value=None,
        verification_status="UNVERIFIED",
        absence_status="NOT_APPLICABLE",
        absence_message=None,
        evidence_state="MISSING",
        reasons=(),
    )
    return ValidatedLLMResult(
        facts=facts,
        status=ValidationStatus.FAILED,
        reasons=(LLMValidationReason.GENERATION_FAILED,),
        llm_calls=0,
    )
