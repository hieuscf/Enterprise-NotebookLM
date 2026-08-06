# =============================================================================
# File: citations.py
# Module/Service: Chat Service / Citation Verification (FR5)
# Layer: Repository
# Purpose: Persist verified citations for an assistant message (Part 2 mapping).
# Responsibilities:
#   - insert_mapped() from CitationRef + latest-pass retrieval rows
# Dependencies:
#   - SQLAlchemy AsyncSession, Citation, Retrieval
# Public Exports:
#   - CitationRepository
# Database/Table: citations, retrievals
# Related Modules: MessageProcessingService
# Important Notes: Part 2 maps LLM citation_ids → retrievals of latest pass only.
# =============================================================================

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

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
        """Insert citations for refs that match chunk_id in latest-pass retrievals."""
        by_chunk: dict[uuid.UUID, Retrieval] = {
            row.chunk_id: row
            for row in latest_pass_rows
            if row.chunk_id is not None
        }
        snippets = snippet_by_chunk_id or {}
        created: list[Citation] = []
        order_index = 0
        seen: set[uuid.UUID] = set()
        for ref in citation_refs:
            if ref.chunk_id is None or ref.chunk_id in seen:
                continue
            retrieval = by_chunk.get(ref.chunk_id)
            if retrieval is None:
                continue
            text = (snippets.get(ref.chunk_id) or "").strip() or f"Cited chunk {ref.chunk_id}"
            row = Citation(
                id=uuid.uuid4(),
                message_id=message_id,
                retrieval_id=retrieval.id,
                text_snippet=text[:4000],
                verified=bool(ref.verify),
                order_index=order_index,
            )
            self._session.add(row)
            created.append(row)
            seen.add(ref.chunk_id)
            order_index += 1
        if created:
            await self._session.flush()
        return created
