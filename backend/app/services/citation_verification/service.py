# =============================================================================
# File: service.py
# Module/Service: Citation Verification Layer (FR5)
# Layer: Service
# Purpose: Deterministic 4-level citation verification (no LLM).
# Responsibilities:
#   - verify() / verify_llm_citations(): 4-level LLM citation_id check
#   - verify_extractive_citations(): chunk_id + workspace, page optional
# Dependencies:
#   - citation_verification.text, reasons, results, metrics
# Public Exports:
#   - CitationVerificationService, INSUFFICIENT_EVIDENCE_ANSWER,
#     evidence_from_candidates
# Database/Table: N/A (evidence loaded by repository / in-memory retrieval)
# Related Modules: ComplexQueryPipeline, MessageProcessingService, QueryOrchestrator
# Important Notes:
#   - Deterministic verification. No LLM call.
#   - Must validate workspace/message/retrieval membership.
#   - Extractive route does not require snippet ⊆ source or page_number.
# =============================================================================

from __future__ import annotations

import hashlib
import time
from collections.abc import Mapping, Sequence
from uuid import UUID, uuid4

from app.core.logging import get_logger
from app.services.citation_verification.metrics import get_citation_verification_metrics
from app.services.citation_verification.reasons import VerificationReason
from app.services.citation_verification.results import (
    CitationVerificationReport,
    CitationVerificationResult,
    RetrievalEvidence,
)
from app.services.citation_verification.text import normalize_evidence_text, snippet_in_source
from app.services.query_router.schemas import CitationRef
from app.services.retrieval.schemas import RetrievalCandidate

logger = get_logger(__name__)

INSUFFICIENT_EVIDENCE_ANSWER = (
    "Không đủ căn cứ trong tài liệu để trả lời câu hỏi này."
)

_UUID_LEN = 36


def evidence_from_candidates(
    *,
    workspace_id: UUID,
    message_id: UUID,
    candidates: Sequence[RetrievalCandidate],
    use_candidate_workspace: bool = False,
) -> list[RetrievalEvidence]:
    """Build evidence rows from the in-memory retrieved context of this query.

    ``message_id`` is the current query's user message. Hybrid retrieval is
    already scoped to ``workspace_id``; candidate.workspace_id is not used as
    a substitute (LLM path). Extractive provenance sets
    ``use_candidate_workspace=True`` so a foreign chunk fails WRONG_WORKSPACE.
    """
    out: list[RetrievalEvidence] = []
    seen_chunks: set[UUID] = set()
    for cand in candidates:
        chunk_id = cand.chunk_id
        if chunk_id is None or chunk_id in seen_chunks:
            continue
        seen_chunks.add(chunk_id)
        evidence_ws = (
            cand.workspace_id
            if use_candidate_workspace and cand.workspace_id is not None
            else workspace_id
        )
        out.append(
            RetrievalEvidence(
                retrieval_id=uuid4(),
                message_id=message_id,
                source_text=str(cand.text_snippet or ""),
                workspace_id=evidence_ws,
                chunk_id=chunk_id,
                entity_id=cand.entity_id,
                document_id=cand.document_id,
                document_version_id=cand.document_version_id,
                page_number=cand.page_number,
                retrieval_pass=1,
            )
        )
    return out


def merge_retrieved_and_persisted_evidence(
    *,
    retrieved: Sequence[RetrievalEvidence],
    persisted: Sequence[RetrievalEvidence],
) -> list[RetrievalEvidence]:
    """Prefer retrieved-context source text; overlay persisted integrity fields.

    Persisted-only rows (in ``retrievals`` but not in the in-memory result,
    e.g. context-assembly expansions flushed to DB) are kept — they are still
    retrieval-context members of this message.
    """
    persisted_by_chunk: dict[str, RetrievalEvidence] = {
        str(row.chunk_id): row for row in persisted if row.chunk_id is not None
    }
    out: list[RetrievalEvidence] = []
    seen: set[str] = set()
    for mem in retrieved:
        key = str(mem.chunk_id) if mem.chunk_id is not None else str(mem.retrieval_id)
        seen.add(key)
        db_row = persisted_by_chunk.get(str(mem.chunk_id)) if mem.chunk_id else None
        if db_row is None:
            out.append(mem)
            continue
        out.append(
            RetrievalEvidence(
                retrieval_id=db_row.retrieval_id,
                message_id=db_row.message_id,
                source_text=mem.source_text if mem.source_text.strip() else db_row.source_text,
                workspace_id=(
                    db_row.workspace_id
                    if db_row.workspace_id is not None
                    else mem.workspace_id
                ),
                chunk_id=mem.chunk_id or db_row.chunk_id,
                entity_id=mem.entity_id or db_row.entity_id,
                document_id=db_row.document_id or mem.document_id,
                document_version_id=db_row.document_version_id or mem.document_version_id,
                page_number=(
                    db_row.page_number if db_row.page_number is not None else mem.page_number
                ),
                retrieval_pass=db_row.retrieval_pass,
                source_integrity_ok=(
                    True
                    if (mem.source_text or "").strip()
                    else db_row.source_integrity_ok
                ),
            )
        )
    for db_row in persisted:
        key = str(db_row.chunk_id) if db_row.chunk_id is not None else str(db_row.retrieval_id)
        if key in seen:
            continue
        seen.add(key)
        out.append(db_row)
    return out


class CitationVerificationService:
    """Independent Citation Verification Layer — deterministic, no LLM."""

    def verify(
        self,
        *,
        workspace_id: UUID,
        message_id: UUID,
        cited_ids: Sequence[str],
        evidence: Sequence[RetrievalEvidence],
        snippet_by_citation_id: Mapping[str, str] | None = None,
    ) -> CitationVerificationReport:
        """Verify each cited id against this message's retrieved evidence only."""
        started = time.perf_counter()
        snippets = dict(snippet_by_citation_id or {})
        by_retrieval, by_chunk = _index_evidence(evidence)

        results: list[CitationVerificationResult] = []
        seen_keys: set[str] = set()

        for raw in cited_ids:
            citation_id = str(raw or "").strip()
            result = self._verify_one(
                citation_id=citation_id,
                workspace_id=workspace_id,
                message_id=message_id,
                by_retrieval=by_retrieval,
                by_chunk=by_chunk,
                snippet_override=snippets.get(citation_id),
                seen_keys=seen_keys,
            )
            results.append(result)
            self._log_one(
                workspace_id=workspace_id,
                message_id=message_id,
                result=result,
            )

        latency_ms = max(0, int((time.perf_counter() - started) * 1000))
        report = CitationVerificationReport(results=results, latency_ms=latency_ms)
        self._record_metrics(report)
        logger.info(
            "citation_verification_completed",
            workspace_id=str(workspace_id),
            message_id=str(message_id),
            citation_count=report.total_count,
            valid_count=report.valid_count,
            invalid_count=report.invalid_count,
            verification_latency_ms=latency_ms,
            verification_rate=(
                report.valid_count / report.total_count if report.total_count else None
            ),
        )
        return report

    def verify_llm_citations(
        self,
        *,
        workspace_id: UUID,
        message_id: UUID,
        cited_ids: Sequence[str],
        evidence: Sequence[RetrievalEvidence],
        snippet_by_citation_id: Mapping[str, str] | None = None,
    ) -> CitationVerificationReport:
        """LLM citation_ids against retrieved evidence (4-level check)."""
        return self.verify(
            workspace_id=workspace_id,
            message_id=message_id,
            cited_ids=cited_ids,
            evidence=evidence,
            snippet_by_citation_id=snippet_by_citation_id,
        )

    def verify_extractive_citations(
        self,
        *,
        workspace_id: UUID,
        message_id: UUID,
        refs: Sequence[CitationRef],
        evidence: Sequence[RetrievalEvidence],
    ) -> CitationVerificationReport:
        """0-LLM provenance check: chunk exists, workspace matches, page optional.

        Duplicate chunk ids collapse to one valid citation (provenance merge),
        they are not rejected. Empty source text is allowed when integrity is ok
        — extractive snippets may be heading titles rather than body spans.
        """
        started = time.perf_counter()
        _by_retrieval, by_chunk = _index_evidence(evidence)
        results: list[CitationVerificationResult] = []
        seen_keys: set[str] = set()

        for ref in refs:
            citation_id = str(ref.chunk_id) if ref.chunk_id is not None else ""
            result = self._verify_extractive_one(
                citation_id=citation_id,
                workspace_id=workspace_id,
                message_id=message_id,
                by_chunk=by_chunk,
                snippet_override=ref.text_snippet,
                seen_keys=seen_keys,
            )
            results.append(result)
            self._log_one(
                workspace_id=workspace_id,
                message_id=message_id,
                result=result,
            )

        latency_ms = max(0, int((time.perf_counter() - started) * 1000))
        report = CitationVerificationReport(results=results, latency_ms=latency_ms)
        self._record_metrics(report)
        logger.info(
            "citation_verification_extractive_completed",
            workspace_id=str(workspace_id),
            message_id=str(message_id),
            citation_count=report.total_count,
            valid_count=report.valid_count,
            invalid_count=report.invalid_count,
            verification_latency_ms=latency_ms,
        )
        return report

    def _verify_extractive_one(
        self,
        *,
        citation_id: str,
        workspace_id: UUID,
        message_id: UUID,
        by_chunk: dict[str, RetrievalEvidence],
        snippet_override: str | None,
        seen_keys: set[str],
    ) -> CitationVerificationResult:
        if not citation_id:
            return CitationVerificationResult(
                citation_id=citation_id,
                verified=False,
                reason=VerificationReason.CITATION_NOT_FOUND,
            )
        evidence = by_chunk.get(citation_id)
        if evidence is None:
            return CitationVerificationResult(
                citation_id=citation_id,
                verified=False,
                reason=VerificationReason.RETRIEVAL_NOT_FOUND,
            )
        if evidence.message_id != message_id:
            return _rejected(citation_id, evidence, VerificationReason.WRONG_MESSAGE)
        if evidence.chunk_id is None:
            return _rejected(
                citation_id, evidence, VerificationReason.INVALID_RETRIEVAL_REFERENCE
            )
        if not evidence.source_integrity_ok:
            return _rejected(citation_id, evidence, VerificationReason.SOURCE_NOT_FOUND)
        if evidence.workspace_id is None:
            return _rejected(citation_id, evidence, VerificationReason.SOURCE_NOT_FOUND)
        if evidence.workspace_id != workspace_id:
            return _rejected(citation_id, evidence, VerificationReason.WRONG_WORKSPACE)

        dedupe_key = str(evidence.chunk_id)
        if dedupe_key in seen_keys:
            return CitationVerificationResult(
                citation_id=citation_id,
                verified=True,
                reason=VerificationReason.VALID,
                retrieval_id=evidence.retrieval_id,
                document_id=evidence.document_id,
                chunk_id=evidence.chunk_id,
                page_number=evidence.page_number,
                text_snippet=(snippet_override or evidence.source_text or "").strip()
                or None,
                document_version_id=evidence.document_version_id,
            )
        seen_keys.add(dedupe_key)

        snippet = (snippet_override or evidence.source_text or "").strip()
        return CitationVerificationResult(
            citation_id=citation_id,
            verified=True,
            reason=VerificationReason.VALID,
            retrieval_id=evidence.retrieval_id,
            document_id=evidence.document_id,
            chunk_id=evidence.chunk_id,
            page_number=evidence.page_number,
            text_snippet=snippet or None,
            document_version_id=evidence.document_version_id,
        )

    def to_citation_refs(
        self,
        report: CitationVerificationReport,
    ) -> list[CitationRef]:
        """Map verified results to persistable CitationRef (verify=True only)."""
        refs: list[CitationRef] = []
        for row in report.verified_results:
            refs.append(
                CitationRef(
                    chunk_id=row.chunk_id,
                    document_id=row.document_id,
                    page_number=row.page_number,
                    verify=True,
                    text_snippet=row.text_snippet,
                    document_version_id=row.document_version_id,
                )
            )
        return refs

    def _verify_one(
        self,
        *,
        citation_id: str,
        workspace_id: UUID,
        message_id: UUID,
        by_retrieval: dict[str, RetrievalEvidence],
        by_chunk: dict[str, RetrievalEvidence],
        snippet_override: str | None,
        seen_keys: set[str],
    ) -> CitationVerificationResult:
        # Level 1 — citation id validity
        if not citation_id:
            return CitationVerificationResult(
                citation_id=citation_id,
                verified=False,
                reason=VerificationReason.CITATION_NOT_FOUND,
            )

        evidence = by_retrieval.get(citation_id) or by_chunk.get(citation_id)
        if evidence is None:
            reason = (
                VerificationReason.RETRIEVAL_NOT_FOUND
                if _looks_like_uuid(citation_id)
                else VerificationReason.CITATION_NOT_FOUND
            )
            return CitationVerificationResult(
                citation_id=citation_id,
                verified=False,
                reason=reason,
            )

        dedupe_key = str(evidence.chunk_id or evidence.retrieval_id)
        if dedupe_key in seen_keys:
            return CitationVerificationResult(
                citation_id=citation_id,
                verified=False,
                reason=VerificationReason.DUPLICATE,
                retrieval_id=evidence.retrieval_id,
                document_id=evidence.document_id,
                chunk_id=evidence.chunk_id,
                page_number=evidence.page_number,
                document_version_id=evidence.document_version_id,
            )
        seen_keys.add(dedupe_key)

        # Level 2 + 3 — message membership, workspace, source chain
        if evidence.message_id != message_id:
            return _rejected(
                citation_id,
                evidence,
                VerificationReason.WRONG_MESSAGE,
            )
        if evidence.chunk_id is None:
            return _rejected(
                citation_id,
                evidence,
                VerificationReason.INVALID_RETRIEVAL_REFERENCE,
            )
        if not evidence.source_integrity_ok:
            return _rejected(
                citation_id,
                evidence,
                VerificationReason.SOURCE_NOT_FOUND,
            )
        source_text = evidence.source_text or ""
        if not source_text.strip():
            return _rejected(
                citation_id,
                evidence,
                VerificationReason.SOURCE_NOT_FOUND,
            )
        if evidence.workspace_id is None:
            # Document join missed — cannot prove tenant isolation.
            return _rejected(
                citation_id,
                evidence,
                VerificationReason.SOURCE_NOT_FOUND,
            )
        if evidence.workspace_id != workspace_id:
            return _rejected(
                citation_id,
                evidence,
                VerificationReason.WRONG_WORKSPACE,
            )

        snippet = snippet_override if snippet_override is not None else source_text
        if not normalize_evidence_text(snippet or ""):
            return _rejected(
                citation_id,
                evidence,
                VerificationReason.EMPTY_SNIPPET,
                text_snippet=snippet or "",
            )

        # Level 4 — snippet must be grounded in retrieved source text
        if not snippet_in_source(snippet=snippet, source=evidence.source_text):
            return _rejected(
                citation_id,
                evidence,
                VerificationReason.SNIPPET_NOT_IN_SOURCE,
                text_snippet=snippet,
            )

        return CitationVerificationResult(
            citation_id=citation_id,
            verified=True,
            reason=VerificationReason.VALID,
            retrieval_id=evidence.retrieval_id,
            document_id=evidence.document_id,
            chunk_id=evidence.chunk_id,
            page_number=evidence.page_number,
            text_snippet=(snippet or "").strip(),
            document_version_id=evidence.document_version_id,
        )

    def _log_one(
        self,
        *,
        workspace_id: UUID,
        message_id: UUID,
        result: CitationVerificationResult,
    ) -> None:
        logger.info(
            "citation_verification_item",
            workspace_id=str(workspace_id),
            message_id=str(message_id),
            citation_id=result.citation_id,
            retrieval_id=str(result.retrieval_id) if result.retrieval_id else None,
            chunk_id=str(result.chunk_id) if result.chunk_id else None,
            verification_status="valid" if result.verified else "invalid",
            verification_reason=result.reason.value,
            snippet_hash=_snippet_hash(result.text_snippet),
        )

    def _record_metrics(self, report: CitationVerificationReport) -> None:
        reasons: dict[str, int] = {}
        for row in report.rejected_results:
            reasons[row.reason.value] = reasons.get(row.reason.value, 0) + 1
        get_citation_verification_metrics().record_batch(
            total=report.total_count,
            valid=report.valid_count,
            invalid=report.invalid_count,
            latency_ms=report.latency_ms,
            reasons=reasons,
        )


def _index_evidence(
    evidence: Sequence[RetrievalEvidence],
) -> tuple[dict[str, RetrievalEvidence], dict[str, RetrievalEvidence]]:
    by_retrieval: dict[str, RetrievalEvidence] = {}
    by_chunk: dict[str, RetrievalEvidence] = {}
    for row in evidence:
        by_retrieval[str(row.retrieval_id)] = row
        if row.chunk_id is not None:
            by_chunk.setdefault(str(row.chunk_id), row)
    return by_retrieval, by_chunk


def _rejected(
    citation_id: str,
    evidence: RetrievalEvidence,
    reason: VerificationReason,
    *,
    text_snippet: str | None = None,
) -> CitationVerificationResult:
    return CitationVerificationResult(
        citation_id=citation_id,
        verified=False,
        reason=reason,
        retrieval_id=evidence.retrieval_id,
        document_id=evidence.document_id,
        chunk_id=evidence.chunk_id,
        page_number=evidence.page_number,
        text_snippet=text_snippet,
        document_version_id=evidence.document_version_id,
    )


def _looks_like_uuid(value: str) -> bool:
    if len(value) != _UUID_LEN:
        return False
    try:
        UUID(value)
        return True
    except ValueError:
        return False


def _snippet_hash(text: str | None) -> str | None:
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
