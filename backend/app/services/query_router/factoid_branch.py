# =============================================================================
# File: factoid_branch.py
# Module/Service: Query Router Execution / Factoid Branch
# Layer: Service
# Purpose: Compat facade over FactoidHandler (extractive, 0 LLM).
# Responsibilities:
#   - Prefer FactoidHandler + Retriever; fall back to decision.retrieval_result
# Dependencies:
#   - FactoidHandler, Retriever, RetrievalRepository (optional hydration)
# Public Exports:
#   - FactoidBranch, FactoidBranchResult
# Database/Table: document_chunks (optional page_number hydration)
# Related Modules: orchestrator, handlers.factoid_handler
# Important Notes: Never call LLM; never paraphrase.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.models.enums import RouteType
from app.repositories.retrieval import RetrievalRepository
from app.services.query_router.handlers.factoid_handler import FactoidHandler
from app.services.query_router.interfaces.retriever import RetrievedChunk, Retriever
from app.services.query_router.schemas import CitationRef, RouteDecision

logger = get_logger(__name__)


@dataclass(slots=True)
class FactoidBranchResult:
    """Extractive factoid execution result."""

    route_type: RouteType
    answer: str | None
    citation_refs: list[CitationRef]
    metadata: dict[str, Any]
    verify: bool
    status: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)
    confidence: float | None = None


class _DecisionRetriever:
    """Adapter: reuse router-attached retrieval_result as Retriever hits."""

    def __init__(self, decision: RouteDecision) -> None:
        self._decision = decision

    async def retrieve(
        self,
        query: str,
        top_k: int,
        *,
        workspace_id: UUID,
    ) -> list[RetrievedChunk]:
        del query, workspace_id
        retrieval = self._decision.retrieval_result
        if retrieval is None or not retrieval.items:
            return []
        out: list[RetrievedChunk] = []
        for item in retrieval.items[: max(1, top_k)]:
            score = float(item.score if item.score is not None else item.raw_score or 0.0)
            out.append(
                RetrievedChunk(
                    chunk_id=item.chunk_id,
                    document_id=item.document_id,
                    text=item.text_snippet or "",
                    score=score,
                    page_number=getattr(item, "page_number", None),
                )
            )
        return out


class FactoidBranch:
    """Factoid executor — extractive Top-K via ``FactoidHandler``."""

    def __init__(
        self,
        *,
        retrieval_repo: RetrievalRepository | None = None,
        retriever: Retriever | None = None,
        handler: FactoidHandler | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._repo = retrieval_repo
        self._retriever = retriever
        self._handler = handler
        self._settings = settings or get_settings()

    async def execute(
        self,
        *,
        workspace_id: UUID,
        decision: RouteDecision,
        query_text: str | None = None,
    ) -> FactoidBranchResult:
        """Build extractive answer via handler (Retriever or decision payload).

        Args:
            workspace_id: Tenant scope.
            decision: Router decision (may carry retrieval_result).
            query_text: Original query — required when using injected Retriever.
        """
        retriever = self._retriever
        if retriever is None:
            retriever = _DecisionRetriever(decision)

        handler = self._handler or FactoidHandler(
            retriever=retriever,
            settings=self._settings,
        )

        # When using decision-backed retriever, query text is unused.
        text = query_text or decision.extras.get("query_text") or ""
        result = await handler.handle(workspace_id=workspace_id, query_text=str(text))

        citations = list(result.citation_refs)
        # Optional page_number hydration when missing.
        if (
            result.route_type == RouteType.factoid
            and citations
            and self._repo is not None
            and citations[0].chunk_id is not None
            and citations[0].page_number is None
        ):
            hydrated = await self._repo.hydrate_chunks(
                workspace_id, [citations[0].chunk_id]
            )
            row = hydrated.get(citations[0].chunk_id)
            if row is not None:
                citations[0] = CitationRef(
                    chunk_id=citations[0].chunk_id,
                    document_id=citations[0].document_id or row.document_id,
                    page_number=row.page_number,
                    verify=citations[0].verify,
                )

        return FactoidBranchResult(
            route_type=result.route_type,
            answer=result.answer,
            citation_refs=citations,
            metadata=dict(result.metadata),
            verify=result.verify,
            status=result.status,
            confidence=result.confidence,
            extras={},
        )
