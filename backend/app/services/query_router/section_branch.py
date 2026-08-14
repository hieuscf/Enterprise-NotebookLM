# =============================================================================
# File: section_branch.py
# Module/Service: Query Router Execution / Section Extraction Branch
# Layer: Service
# Purpose: Compat facade over SectionExtractionHandler (0 LLM).
# Responsibilities:
#   - Execute structure-aware section listing; preserve branch result shape
# Dependencies:
#   - SectionExtractionHandler, RetrievalRepository
# Public Exports:
#   - SectionExtractionBranch, SectionExtractionBranchResult
# Database/Table: document_chunks
# Related Modules: orchestrator, handlers.section_extraction_handler
# Important Notes: Never call LLM; never paraphrase source chunks.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.models.enums import RouteType
from app.repositories.retrieval import RetrievalRepository
from app.services.query_router.handlers.section_extraction_handler import (
    SectionExtractionHandler,
)
from app.services.query_router.schemas import CitationRef, RouteDecision
from app.services.query_router.section_patterns import SectionIntentMatch


@dataclass(slots=True)
class SectionExtractionBranchResult:
    """Section extraction execution result (may signal complex fallback)."""

    route_type: RouteType
    answer: str | None
    citation_refs: list[CitationRef]
    metadata: dict[str, Any]
    verify: bool
    status: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)
    confidence: float | None = None


class SectionExtractionBranch:
    """Section extraction executor — structured headings + children, 0 LLM."""

    def __init__(
        self,
        *,
        retrieval_repo: RetrievalRepository,
        handler: SectionExtractionHandler | None = None,
    ) -> None:
        self._handler = handler or SectionExtractionHandler(
            retrieval_repo=retrieval_repo
        )

    async def execute(
        self,
        *,
        workspace_id: UUID,
        query_text: str,
        decision: RouteDecision | None = None,
        intent: SectionIntentMatch | None = None,
    ) -> SectionExtractionBranchResult:
        """Run section extraction; complex route_type means caller should RAG."""
        del decision
        result = await self._handler.handle(
            workspace_id=workspace_id,
            query_text=query_text,
            intent=intent,
        )
        return SectionExtractionBranchResult(
            route_type=result.route_type,
            answer=result.answer,
            citation_refs=list(result.citation_refs),
            metadata=dict(result.metadata),
            verify=result.verify,
            status=result.status,
            confidence=result.confidence,
            extras={},
        )
