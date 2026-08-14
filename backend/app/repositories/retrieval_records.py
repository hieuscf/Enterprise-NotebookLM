# =============================================================================
# File: retrieval_records.py
# Module/Service: Chat Service / Citation Verification (FR3, FR5, FR14)
# Layer: Repository
# Purpose: Persist Hybrid Retrieval candidates into ``retrievals`` (pass 1/2).
# Responsibilities:
#   - Bulk-insert RetrievalCandidate rows with retrieval_pass
#   - list_integrity_for_cited_chunks: workspace/version/document joins WITHOUT
#     loading DocumentChunk.content (source text comes from retrieved context)
# Dependencies:
#   - SQLAlchemy AsyncSession, app.models.retrieval.Retrieval
# Public Exports:
#   - RetrievalRecordRepository
# Database/Table: retrievals, document_chunks, document_versions, documents
# Related Modules: ComplexQueryPipeline, Prompt Construction, Citation Verification
# Important Notes:
#   - Never overwrite pass=1 when writing pass=2 — insert only.
#   - Prompt Construction MUST use list_for_latest_pass — never merge passes.
#   - Integrity lookup is scoped to message_id + cited chunk_ids; never SELECT
#     retrievals by id alone; never load full chunk text just to verify.
#   - Deterministic verification. No LLM call.
#   - Must validate workspace/message/retrieval membership.
# =============================================================================

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.documents import Document, DocumentVersion
from app.models.enums import RetrievalMethod
from app.models.knowledge import DocumentChunk
from app.models.retrieval import Retrieval
from app.services.citation_verification.results import RetrievalEvidence
from app.services.retrieval.schemas import RetrievalCandidate

_METHOD_MAP: dict[str, RetrievalMethod] = {m.value: m for m in RetrievalMethod}


class RetrievalRecordRepository:
    """Write + latest-pass read for ``retrievals`` audit rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert_candidates(
        self,
        *,
        message_id: uuid.UUID,
        candidates: Sequence[RetrievalCandidate],
        retrieval_pass: int,
    ) -> int:
        """Insert candidates for one retrieval pass. Returns rows inserted."""
        pass_no = max(1, int(retrieval_pass))
        count = 0
        for cand in candidates:
            method = _METHOD_MAP.get(
                (cand.retrieval_method or "vector").strip().lower(),
                RetrievalMethod.vector,
            )
            score = float(cand.score if cand.score is not None else cand.raw_score or 0.0)
            rank = int(cand.rank if cand.rank is not None else 0)
            self._session.add(
                Retrieval(
                    id=uuid.uuid4(),
                    message_id=message_id,
                    chunk_id=cand.chunk_id,
                    entity_id=cand.entity_id,
                    retrieval_method=method,
                    score=score,
                    rank=rank,
                    retrieval_pass=pass_no,
                )
            )
            count += 1
        if count:
            await self._session.flush()
        return count

    async def get_latest_retrieval_pass(self, message_id: uuid.UUID) -> int | None:
        """Return ``MAX(retrieval_pass)`` for the message, or None if no rows."""
        result = await self._session.execute(
            select(func.max(Retrieval.retrieval_pass)).where(
                Retrieval.message_id == message_id
            )
        )
        value = result.scalar_one_or_none()
        return int(value) if value is not None else None

    async def list_for_pass(
        self,
        *,
        message_id: uuid.UUID,
        retrieval_pass: int,
    ) -> list[Retrieval]:
        """Rows for exactly one pass, ordered by rank ASC (no merge across passes)."""
        rows = (
            await self._session.execute(
                select(Retrieval)
                .where(
                    Retrieval.message_id == message_id,
                    Retrieval.retrieval_pass == int(retrieval_pass),
                )
                .order_by(Retrieval.rank.asc())
            )
        ).scalars().all()
        return list(rows)

    async def list_for_latest_pass(self, message_id: uuid.UUID) -> list[Retrieval]:
        """Load only the newest retrieval_pass for Prompt Construction / citations."""
        latest = await self.get_latest_retrieval_pass(message_id)
        if latest is None:
            return []
        return await self.list_for_pass(message_id=message_id, retrieval_pass=latest)

    async def list_integrity_for_cited_chunks(
        self,
        *,
        message_id: uuid.UUID,
        chunk_ids: Sequence[uuid.UUID],
    ) -> list[RetrievalEvidence]:
        """Join cited retrievals to document/workspace — no chunk body.

        Source text for Level 4 must come from retrieved context (in-memory),
        not a full ``document_chunks.content`` reload of the entire pass.
        """
        ids = [cid for cid in chunk_ids if cid is not None]
        if not ids:
            return []
        latest_pass = (
            select(func.max(Retrieval.retrieval_pass))
            .where(Retrieval.message_id == message_id)
            .scalar_subquery()
        )
        stmt = (
            select(
                Retrieval,
                DocumentChunk.document_version_id,
                DocumentChunk.page_number,
                DocumentVersion.id.label("version_pk"),
                Document.id.label("document_pk"),
                Document.workspace_id,
            )
            .outerjoin(DocumentChunk, Retrieval.chunk_id == DocumentChunk.id)
            .outerjoin(
                DocumentVersion,
                DocumentChunk.document_version_id == DocumentVersion.id,
            )
            .outerjoin(Document, DocumentVersion.document_id == Document.id)
            .where(
                Retrieval.message_id == message_id,
                Retrieval.retrieval_pass == latest_pass,
                Retrieval.chunk_id.in_(ids),
            )
            .order_by(Retrieval.rank.asc())
        )
        rows = (await self._session.execute(stmt)).all()
        evidence: list[RetrievalEvidence] = []
        for (
            retrieval,
            chunk_version_id,
            page_number,
            version_pk,
            document_pk,
            workspace_id,
        ) in rows:
            chunk_id = retrieval.chunk_id
            integrity_ok = (
                chunk_id is not None
                and version_pk is not None
                and document_pk is not None
                and workspace_id is not None
            )
            evidence.append(
                RetrievalEvidence(
                    retrieval_id=retrieval.id,
                    message_id=retrieval.message_id,
                    source_text="",  # filled from retrieved context by the merger
                    workspace_id=workspace_id,
                    chunk_id=chunk_id,
                    entity_id=retrieval.entity_id,
                    document_id=document_pk,
                    document_version_id=chunk_version_id or version_pk,
                    page_number=page_number,
                    retrieval_pass=int(retrieval.retrieval_pass),
                    source_integrity_ok=integrity_ok,
                )
            )
        return evidence
