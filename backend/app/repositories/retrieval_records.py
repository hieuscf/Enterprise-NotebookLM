# =============================================================================
# File: retrieval_records.py
# Module/Service: Chat Service / Citation Verification (FR3, FR5, FR14)
# Layer: Repository
# Purpose: Persist Hybrid Retrieval candidates into ``retrievals`` (pass 1/2).
# Responsibilities:
#   - Bulk-insert RetrievalCandidate rows with retrieval_pass
#   - get_latest_retrieval_pass / list_for_pass (Prompt Construction only)
# Dependencies:
#   - SQLAlchemy AsyncSession, app.models.retrieval.Retrieval
# Public Exports:
#   - RetrievalRecordRepository
# Database/Table: retrievals
# Related Modules: ComplexQueryPipeline, Prompt Construction
# Important Notes:
#   - Never overwrite pass=1 when writing pass=2 — insert only.
#   - Prompt Construction MUST use list_for_latest_pass — never merge passes.
# =============================================================================

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import RetrievalMethod
from app.models.retrieval import Retrieval
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
