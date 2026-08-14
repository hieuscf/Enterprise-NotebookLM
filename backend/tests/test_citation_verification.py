# =============================================================================
# File: test_citation_verification.py
# Module/Service: Citation Verification Layer (FR5)
# Layer: Service (tests)
# Purpose: Unit tests for deterministic 4-level citation verification.
# Responsibilities:
#   - Valid / unknown / wrong message / wrong workspace / missing retrieval
#   - Missing source, exact + sub-span snippet, whitespace normalize, empty
#   - Partial validity, duplicates, metrics
# Dependencies:
#   - pytest, citation_verification
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: ComplexQueryPipeline, MessageProcessingService
# Important Notes:
#   - Deterministic verification. No LLM call.
#   - Must validate workspace/message/retrieval membership.
# =============================================================================

from __future__ import annotations

import uuid

from app.services.citation_verification.metrics import (
    get_citation_verification_metrics,
    reset_citation_verification_metrics_for_tests,
)
from app.services.citation_verification.reasons import VerificationReason
from app.services.citation_verification.results import RetrievalEvidence
from app.services.citation_verification.extractive import provenance_candidates_from_refs
from app.services.citation_verification.service import (
    CitationVerificationService,
    evidence_from_candidates,
)
from app.services.citation_verification.text import normalize_evidence_text, snippet_in_source
from app.services.query_router.schemas import CitationRef

SOURCE = (
    "Enterprise NotebookLM provides hybrid retrieval using vector search, "
    "BM25 and knowledge graph retrieval for enterprise documents."
)


def _evidence(
    *,
    workspace_id: uuid.UUID,
    message_id: uuid.UUID,
    chunk_id: uuid.UUID | None = None,
    retrieval_id: uuid.UUID | None = None,
    source_text: str = SOURCE,
    document_id: uuid.UUID | None = None,
    document_version_id: uuid.UUID | None = None,
    page_number: int | None = 3,
    source_integrity_ok: bool = True,
) -> RetrievalEvidence:
    cid = chunk_id or uuid.uuid4()
    return RetrievalEvidence(
        retrieval_id=retrieval_id or uuid.uuid4(),
        message_id=message_id,
        source_text=source_text,
        workspace_id=workspace_id,
        chunk_id=cid,
        document_id=document_id or uuid.uuid4(),
        document_version_id=document_version_id or uuid.uuid4(),
        page_number=page_number,
        source_integrity_ok=source_integrity_ok,
    )


def _verify(
    *,
    workspace_id: uuid.UUID,
    message_id: uuid.UUID,
    cited_ids: list[str],
    evidence: list[RetrievalEvidence],
    snippets: dict[str, str] | None = None,
):
    return CitationVerificationService().verify(
        workspace_id=workspace_id,
        message_id=message_id,
        cited_ids=cited_ids,
        evidence=evidence,
        snippet_by_citation_id=snippets,
    )


def test_normalize_collapses_whitespace_and_case() -> None:
    assert normalize_evidence_text("Enterprise   RAG\nSystem") == normalize_evidence_text(
        "Enterprise RAG System"
    )
    assert snippet_in_source(
        snippet="hybrid retrieval using vector search, BM25 and knowledge graph retrieval",
        source=SOURCE,
    )


def test_valid_citation() -> None:
    ws, msg = uuid.uuid4(), uuid.uuid4()
    row = _evidence(workspace_id=ws, message_id=msg)
    report = _verify(
        workspace_id=ws,
        message_id=msg,
        cited_ids=[str(row.chunk_id)],
        evidence=[row],
    )
    assert report.has_verified
    assert report.verified_results[0].reason is VerificationReason.VALID
    assert report.verified_results[0].verified is True


def test_unknown_citation() -> None:
    ws, msg = uuid.uuid4(), uuid.uuid4()
    row = _evidence(workspace_id=ws, message_id=msg)
    report = _verify(
        workspace_id=ws,
        message_id=msg,
        cited_ids=["not-a-real-id"],
        evidence=[row],
    )
    assert report.results[0].verified is False
    assert report.results[0].reason is VerificationReason.CITATION_NOT_FOUND


def test_wrong_message() -> None:
    ws, msg, other = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    row = _evidence(workspace_id=ws, message_id=other)
    report = _verify(
        workspace_id=ws,
        message_id=msg,
        cited_ids=[str(row.chunk_id)],
        evidence=[row],
    )
    assert report.results[0].verified is False
    assert report.results[0].reason is VerificationReason.WRONG_MESSAGE


def test_wrong_workspace() -> None:
    ws_a, ws_b, msg = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    row = _evidence(workspace_id=ws_b, message_id=msg)
    report = _verify(
        workspace_id=ws_a,
        message_id=msg,
        cited_ids=[str(row.chunk_id)],
        evidence=[row],
    )
    assert report.results[0].verified is False
    assert report.results[0].reason is VerificationReason.WRONG_WORKSPACE


def test_missing_retrieval() -> None:
    ws, msg = uuid.uuid4(), uuid.uuid4()
    row = _evidence(workspace_id=ws, message_id=msg)
    missing = uuid.uuid4()
    report = _verify(
        workspace_id=ws,
        message_id=msg,
        cited_ids=[str(missing)],
        evidence=[row],
    )
    assert report.results[0].verified is False
    assert report.results[0].reason is VerificationReason.RETRIEVAL_NOT_FOUND


def test_missing_source() -> None:
    ws, msg = uuid.uuid4(), uuid.uuid4()
    row = _evidence(
        workspace_id=ws,
        message_id=msg,
        source_text="",
        source_integrity_ok=False,
    )
    report = _verify(
        workspace_id=ws,
        message_id=msg,
        cited_ids=[str(row.chunk_id)],
        evidence=[row],
    )
    assert report.results[0].verified is False
    assert report.results[0].reason is VerificationReason.SOURCE_NOT_FOUND


def test_exact_snippet() -> None:
    ws, msg = uuid.uuid4(), uuid.uuid4()
    row = _evidence(workspace_id=ws, message_id=msg)
    report = _verify(
        workspace_id=ws,
        message_id=msg,
        cited_ids=[str(row.chunk_id)],
        evidence=[row],
        snippets={str(row.chunk_id): SOURCE},
    )
    assert report.results[0].verified is True


def test_subspan_snippet() -> None:
    ws, msg = uuid.uuid4(), uuid.uuid4()
    row = _evidence(workspace_id=ws, message_id=msg)
    snippet = "hybrid retrieval using vector search, BM25 and knowledge graph retrieval"
    report = _verify(
        workspace_id=ws,
        message_id=msg,
        cited_ids=[str(row.chunk_id)],
        evidence=[row],
        snippets={str(row.chunk_id): snippet},
    )
    assert report.results[0].verified is True
    assert report.results[0].text_snippet == snippet


def test_whitespace_normalization() -> None:
    ws, msg = uuid.uuid4(), uuid.uuid4()
    row = _evidence(workspace_id=ws, message_id=msg, source_text="Enterprise   RAG\nSystem")
    report = _verify(
        workspace_id=ws,
        message_id=msg,
        cited_ids=[str(row.chunk_id)],
        evidence=[row],
        snippets={str(row.chunk_id): "Enterprise RAG System"},
    )
    assert report.results[0].verified is True


def test_unsupported_snippet() -> None:
    ws, msg = uuid.uuid4(), uuid.uuid4()
    row = _evidence(workspace_id=ws, message_id=msg)
    report = _verify(
        workspace_id=ws,
        message_id=msg,
        cited_ids=[str(row.chunk_id)],
        evidence=[row],
        snippets={str(row.chunk_id): "Enterprise NotebookLM reduces cost by 80%"},
    )
    assert report.results[0].verified is False
    assert report.results[0].reason is VerificationReason.SNIPPET_NOT_IN_SOURCE


def test_empty_snippet() -> None:
    ws, msg = uuid.uuid4(), uuid.uuid4()
    row = _evidence(workspace_id=ws, message_id=msg)
    report = _verify(
        workspace_id=ws,
        message_id=msg,
        cited_ids=[str(row.chunk_id)],
        evidence=[row],
        snippets={str(row.chunk_id): ""},
    )
    assert report.results[0].verified is False
    assert report.results[0].reason is VerificationReason.EMPTY_SNIPPET


def test_duplicate_citation_keeps_first() -> None:
    ws, msg = uuid.uuid4(), uuid.uuid4()
    row = _evidence(workspace_id=ws, message_id=msg)
    cid = str(row.chunk_id)
    report = _verify(
        workspace_id=ws,
        message_id=msg,
        cited_ids=[cid, cid],
        evidence=[row],
    )
    assert report.valid_count == 1
    assert report.results[1].reason is VerificationReason.DUPLICATE
    assert report.results[1].verified is False


def test_partial_validity() -> None:
    ws, msg = uuid.uuid4(), uuid.uuid4()
    a = _evidence(workspace_id=ws, message_id=msg)
    c = _evidence(workspace_id=ws, message_id=msg)
    b_id = str(uuid.uuid4())
    report = _verify(
        workspace_id=ws,
        message_id=msg,
        cited_ids=[str(a.chunk_id), b_id, str(c.chunk_id)],
        evidence=[a, c],
    )
    assert [r.verified for r in report.results] == [True, False, True]
    assert report.results[1].reason is VerificationReason.RETRIEVAL_NOT_FOUND
    refs = CitationVerificationService().to_citation_refs(report)
    assert {str(r.chunk_id) for r in refs} == {str(a.chunk_id), str(c.chunk_id)}
    assert all(r.verify for r in refs)


def test_match_by_retrieval_id() -> None:
    ws, msg = uuid.uuid4(), uuid.uuid4()
    retrieval_id = uuid.uuid4()
    row = _evidence(workspace_id=ws, message_id=msg, retrieval_id=retrieval_id)
    report = _verify(
        workspace_id=ws,
        message_id=msg,
        cited_ids=[str(retrieval_id)],
        evidence=[row],
    )
    assert report.results[0].verified is True


def test_out_of_retrieval_context_rejected_even_if_id_looks_real() -> None:
    """Citation to a chunk that exists elsewhere must not verify for this message."""
    ws, msg = uuid.uuid4(), uuid.uuid4()
    in_context = _evidence(workspace_id=ws, message_id=msg)
    other_chunk = uuid.uuid4()
    report = _verify(
        workspace_id=ws,
        message_id=msg,
        cited_ids=[str(other_chunk)],
        evidence=[in_context],
    )
    assert report.has_verified is False
    assert report.results[0].reason is VerificationReason.RETRIEVAL_NOT_FOUND


def test_metrics_record_valid_and_invalid() -> None:
    reset_citation_verification_metrics_for_tests()
    ws, msg = uuid.uuid4(), uuid.uuid4()
    row = _evidence(workspace_id=ws, message_id=msg)
    _verify(
        workspace_id=ws,
        message_id=msg,
        cited_ids=[str(row.chunk_id), "missing"],
        evidence=[row],
    )
    snap = get_citation_verification_metrics().snapshot()
    assert snap["citation_verification_total"] == 2
    assert snap["citation_verification_valid"] == 1
    assert snap["citation_verification_invalid"] == 1


def test_extractive_null_page_is_valid() -> None:
    ws, msg = uuid.uuid4(), uuid.uuid4()
    chunk = uuid.uuid4()
    doc = uuid.uuid4()
    ref = CitationRef(
        chunk_id=chunk,
        document_id=doc,
        page_number=None,
        verify=True,
        text_snippet="Hàng tồn kho",
        workspace_id=ws,
    )
    evidence = evidence_from_candidates(
        workspace_id=ws,
        message_id=msg,
        candidates=provenance_candidates_from_refs(workspace_id=ws, refs=[ref]),
        use_candidate_workspace=True,
    )
    report = CitationVerificationService().verify_extractive_citations(
        workspace_id=ws,
        message_id=msg,
        refs=[ref],
        evidence=evidence,
    )
    assert report.has_verified
    assert report.results[0].verified is True
    assert report.results[0].page_number is None
    assert report.results[0].chunk_id == chunk


def test_extractive_wrong_workspace_is_invalid() -> None:
    ws_a, ws_b, msg = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    chunk = uuid.uuid4()
    ref = CitationRef(
        chunk_id=chunk,
        document_id=uuid.uuid4(),
        page_number=4,
        verify=True,
        text_snippet="secret",
        workspace_id=ws_b,
    )
    evidence = evidence_from_candidates(
        workspace_id=ws_a,
        message_id=msg,
        candidates=provenance_candidates_from_refs(workspace_id=ws_a, refs=[ref]),
        use_candidate_workspace=True,
    )
    report = CitationVerificationService().verify_extractive_citations(
        workspace_id=ws_a,
        message_id=msg,
        refs=[ref],
        evidence=evidence,
    )
    assert report.results[0].verified is False
    assert report.results[0].reason is VerificationReason.WRONG_WORKSPACE


def test_extractive_duplicate_content_keeps_both_chunk_ids() -> None:
    ws, msg = uuid.uuid4(), uuid.uuid4()
    text = "Chi phí xây dựng công trình dở dang được ghi nhận theo giá gốc."
    a = uuid.uuid4()
    b = uuid.uuid4()
    refs = [
        CitationRef(
            chunk_id=a,
            document_id=uuid.uuid4(),
            page_number=9,
            verify=True,
            text_snippet=text,
            workspace_id=ws,
        ),
        CitationRef(
            chunk_id=b,
            document_id=uuid.uuid4(),
            page_number=9,
            verify=True,
            text_snippet=text,
            workspace_id=ws,
        ),
    ]
    evidence = evidence_from_candidates(
        workspace_id=ws,
        message_id=msg,
        candidates=provenance_candidates_from_refs(workspace_id=ws, refs=refs),
        use_candidate_workspace=True,
    )
    report = CitationVerificationService().verify_extractive_citations(
        workspace_id=ws,
        message_id=msg,
        refs=refs,
        evidence=evidence,
    )
    assert report.valid_count == 2
    assert {row.chunk_id for row in report.verified_results} == {a, b}
    persistable = CitationVerificationService().to_citation_refs(report)
    assert {ref.chunk_id for ref in persistable} == {a, b}
