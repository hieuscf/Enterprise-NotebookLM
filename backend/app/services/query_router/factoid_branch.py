# =============================================================================
# File: factoid_branch.py
# Module/Service: Query Router Execution / Factoid Branch
# Layer: Service
# Purpose: Extractive factoid answers from Router retrieval_result (0 LLM).
# Responsibilities:
#   - Use top-1 text_snippet as answer (no paraphrase / no re-retrieve)
#   - Build citation_refs with verify=true; hydrate page_number when needed
# Dependencies:
#   - RetrievalRepository (page_number only), RouteDecision.retrieval_result
# Public Exports:
#   - FactoidBranch, FactoidBranchResult
# Database/Table: document_chunks (optional page_number hydration)
# Related Modules: app.services.query_router.orchestrator, Hybrid Retrieval (Part 1)
# Important Notes: Never call HybridRetrievalService; never call LLM.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.core.logging import get_logger
from app.models.enums import RouteType
from app.repositories.retrieval import RetrievalRepository
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


class FactoidBranch:
    """Factoid executor — extractive top-1 snippet only."""

    def __init__(self, *, retrieval_repo: RetrievalRepository | None = None) -> None:
        self._repo = retrieval_repo

    async def execute(
        self,
        *,
        workspace_id: UUID,
        decision: RouteDecision,
    ) -> FactoidBranchResult:
        """Build extractive answer from ``decision.retrieval_result``.

        Args:
            workspace_id: Tenant scope for optional page_number hydration.
            decision: Router decision with precomputed ``retrieval_result``.

        Returns:
            Factoid result with ``verify=True`` and one citation when possible.
            Falls back to complex placeholder if retrieval payload is missing.
        """
        retrieval = decision.retrieval_result
        if retrieval is None or not retrieval.items:
            logger.info(
                "factoid_branch_missing_retrieval",
                workspace_id=str(workspace_id),
            )
            return FactoidBranchResult(
                route_type=RouteType.complex,
                answer=None,
                citation_refs=[],
                metadata={},
                verify=False,
                status="pending_llm_pipeline",
                extras={"fallback_reason": "missing_retrieval_result"},
            )

        top = retrieval.items[0]
        answer = top.text_snippet
        page_number: int | None = None
        document_id = top.document_id
        chunk_id = top.chunk_id

        if chunk_id is not None and self._repo is not None:
            hydrated = await self._repo.hydrate_chunks(workspace_id, [chunk_id])
            row = hydrated.get(chunk_id)
            if row is not None:
                page_number = row.page_number
                if document_id is None:
                    document_id = row.document_id

        citation = CitationRef(
            chunk_id=chunk_id,
            document_id=document_id,
            page_number=page_number,
            verify=True,
        )
        return FactoidBranchResult(
            route_type=RouteType.factoid,
            answer=answer,
            citation_refs=[citation],
            metadata={},
            verify=True,
        )
