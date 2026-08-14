# =============================================================================
# File: extractive.py
# Module/Service: Citation Verification Layer (FR5)
# Layer: Service
# Purpose: Provenance helpers for 0-LLM extractive routes (section_extraction).
# Responsibilities:
#   - Map CitationRef → RetrievalCandidate so retrievals can be audited
#   - Never invent chunk ids; page_number may be null
# Dependencies:
#   - RetrievalCandidate, CitationRef
# Public Exports:
#   - provenance_candidates_from_refs
# Database/Table: retrievals (via RetrievalRecordRepository.insert_candidates)
# Related Modules: CitationVerificationService.verify_extractive_citations
# Important Notes: 0 LLM. Missing page_number is not a missing source.
# =============================================================================

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from app.services.citation_verification.results import RetrievalEvidence
from app.services.query_router.schemas import CitationRef
from app.services.retrieval.schemas import RetrievalCandidate


def provenance_candidates_from_refs(
    *,
    workspace_id: UUID,
    refs: Sequence[CitationRef],
) -> list[RetrievalCandidate]:
    """Build retrieval-audit candidates from extractive citation refs."""
    out: list[RetrievalCandidate] = []
    seen: set[UUID] = set()
    rank = 0
    for ref in refs:
        if ref.chunk_id is None or ref.chunk_id in seen:
            continue
        seen.add(ref.chunk_id)
        snippet = (ref.text_snippet or "").strip()
        out.append(
            RetrievalCandidate(
                workspace_id=ref.workspace_id or workspace_id,
                text_snippet=snippet,
                retrieval_method="bm25",
                raw_score=1.0,
                score=1.0,
                rank=rank,
                document_id=ref.document_id,
                chunk_id=ref.chunk_id,
                page_number=ref.page_number,
                document_version_id=ref.document_version_id,
            )
        )
        rank += 1
    return out


def merge_extractive_evidence(
    *,
    retrieved: Sequence[RetrievalEvidence],
    persisted: Sequence[RetrievalEvidence],
) -> list[RetrievalEvidence]:
    """Overlay DB integrity/workspace onto extractive in-memory provenance.

    Unlike the LLM merger, a non-empty snippet must not mark a missing chunk
    as valid. ``source_integrity_ok`` comes from the document_chunks join.
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
                    db_row.page_number
                    if db_row.page_number is not None
                    else mem.page_number
                ),
                retrieval_pass=db_row.retrieval_pass,
                source_integrity_ok=db_row.source_integrity_ok,
            )
        )
    for db_row in persisted:
        key = str(db_row.chunk_id) if db_row.chunk_id is not None else str(db_row.retrieval_id)
        if key in seen:
            continue
        seen.add(key)
        out.append(db_row)
    return out
