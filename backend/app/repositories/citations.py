# =============================================================================
# File: citations.py
# Module/Service: Chat Service / Citation Verification (FR5)
# Layer: Repository
# Purpose: Persist verified citations for an assistant message (FR5).
# Responsibilities:
#   - insert_mapped() from verified CitationRef + latest-pass retrieval rows
# Dependencies:
#   - SQLAlchemy AsyncSession, Citation, Retrieval
# Public Exports:
#   - CitationRepository
# Database/Table: citations, retrievals
# Related Modules: MessageProcessingService, Citation Verification Layer
# Important Notes:
#   - Deterministic verification. No LLM call.
#   - Must validate workspace/message/retrieval membership.
#   - Only persist refs with verify=True that map to this message's latest pass.
#   - Never invent placeholder snippets or mark unverified citations as verified.
# =============================================================================

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import DocumentChunk
from app.models.retrieval import Citation, Retrieval
from app.services.query_router.schemas import CitationRef


class CitationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert_mapped(
        self,
        *,
        message_id: uuid.UUID,
        citation_refs: Sequence[CitationRef],
        latest_pass_rows: Sequence[Retrieval],
        snippet_by_chunk_id: Mapping[uuid.UUID, str] | None = None,
    ) -> list[Citation]:
        """Insert citations for verified refs that match latest-pass retrievals.

        Unverified refs are skipped. Empty snippets are skipped (never persist a
        placeholder as if it were evidence).
        """
        by_chunk: dict[uuid.UUID, Retrieval] = {
            row.chunk_id: row
            for row in latest_pass_rows
            if row.chunk_id is not None
        }
        snippets = dict(snippet_by_chunk_id or {})
        # Hydrate missing snippets from document_chunks — only for retrieval
        # members of this message (by_chunk). Never query chunks outside that set.
        missing = [
            ref.chunk_id
            for ref in citation_refs
            if ref.verify
            and ref.chunk_id is not None
            and ref.chunk_id in by_chunk
            and not (snippets.get(ref.chunk_id) or "").strip()
            and not (ref.text_snippet or "").strip()
        ]
        if missing:
            rows = (
                await self._session.execute(
                    select(DocumentChunk.id, DocumentChunk.content).where(
                        DocumentChunk.id.in_(missing)
                    )
                )
            ).all()
            for chunk_id, content in rows:
                if chunk_id not in snippets or not (snippets.get(chunk_id) or "").strip():
                    snippets[chunk_id] = (content or "").strip()

        created: list[Citation] = []
        order_index = 0
        seen: set[uuid.UUID] = set()
        for ref in citation_refs:
            if not ref.verify:
                continue
            if ref.chunk_id is None or ref.chunk_id in seen:
                continue
            retrieval = by_chunk.get(ref.chunk_id)
            if retrieval is None:
                continue
            text = (
                (ref.text_snippet or "").strip()
                or (snippets.get(ref.chunk_id) or "").strip()
            )
            if not text:
                continue
            row = Citation(
                id=uuid.uuid4(),
                message_id=message_id,
                retrieval_id=retrieval.id,
                text_snippet=text[:4000],
                verified=True,
                order_index=order_index,
            )
            self._session.add(row)
            created.append(row)
            seen.add(ref.chunk_id)
            order_index += 1
        if created:
            await self._session.flush()
        return created
