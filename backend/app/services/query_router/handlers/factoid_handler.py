# =============================================================================
# File: factoid_handler.py
# Module/Service: Query Router — Simple Factoid Handler (FR11)
# Layer: Service
# Purpose: Lightweight retrieve + confidence + extractive answer (0 LLM).
# Responsibilities:
#   - Call Retriever Top-K; gate on factoid_confidence_threshold
#   - Extract chunk text verbatim; build citation from chunk fields
#   - Downgrade to complex when confidence low / no hits (no second retrieve)
# Dependencies:
#   - Retriever Protocol, Handler/Factoid config, QueryRouterResult
# Public Exports:
#   - FactoidHandler
# Database/Table: N/A (via Retriever)
# Related Modules: orchestrator, factoid_branch (compat facade)
# Important Notes: Never rewrite / summarize / paraphrase / generate.
# =============================================================================

from __future__ import annotations

from uuid import UUID

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.models.enums import RouteType
from app.services.query_router.interfaces.retriever import RetrievedChunk, Retriever
from app.services.query_router.response_models import QueryRouterResult
from app.services.query_router.schemas import CitationRef

logger = get_logger(__name__)

COMPLEX_STATUS = "pending_llm_pipeline"


class FactoidHandler:
    """Simple Factoid executor — extractive answers only."""

    def __init__(
        self,
        *,
        retriever: Retriever,
        settings: Settings | None = None,
        confidence_threshold: float | None = None,
        top_k: int | None = None,
    ) -> None:
        self._retriever = retriever
        cfg = settings or get_settings()
        self._threshold = float(
            confidence_threshold
            if confidence_threshold is not None
            else cfg.query_router_factoid_confidence_threshold
        )
        # Prefer dedicated factoid top_k; fall back to router factoid_top_k.
        self._top_k = max(
            1,
            int(
                top_k
                if top_k is not None
                else getattr(cfg, "query_router_factoid_top_k", 1)
            ),
        )

    async def handle(
        self,
        *,
        workspace_id: UUID,
        query_text: str,
    ) -> QueryRouterResult:
        """Retrieve, score-gate, and extract an answer (or downgrade).

        Args:
            workspace_id: Tenant scope.
            query_text: Original user question.

        Returns:
            ``QueryRouterResult`` with ``factoid`` or ``complex``.
        """
        chunks = await self._retriever.retrieve(
            query_text,
            self._top_k,
            workspace_id=workspace_id,
        )
        if not chunks:
            logger.info(
                "factoid_handler_no_chunks",
                workspace_id=str(workspace_id),
            )
            return self._downgrade("no_retrieval_hits")

        best = max(chunks, key=lambda c: c.score)
        confidence = float(best.score)
        if confidence < self._threshold:
            logger.info(
                "factoid_handler_low_confidence",
                workspace_id=str(workspace_id),
                confidence=confidence,
                threshold=self._threshold,
            )
            return self._downgrade(
                f"confidence_below_threshold:{confidence:.4f}<{self._threshold:.4f}",
                confidence=confidence,
            )

        answer = best.text  # extractive — no rewrite
        citation = CitationRef(
            chunk_id=best.chunk_id,
            document_id=best.document_id,
            page_number=best.page_number,
            verify=True,
        )
        logger.info(
            "factoid_handler_ok",
            workspace_id=str(workspace_id),
            confidence=confidence,
            chunk_id=str(best.chunk_id) if best.chunk_id else None,
        )
        return QueryRouterResult(
            route_type=RouteType.factoid,
            answer=answer,
            citation_refs=[citation],
            confidence=confidence,
            verify=True,
            status=None,
            metadata={
                "top_k": self._top_k,
                "candidates": len(chunks),
                "char_start": best.char_start,
                "char_end": best.char_end,
            },
        )

    def _downgrade(
        self,
        reason: str,
        *,
        confidence: float | None = None,
    ) -> QueryRouterResult:
        return QueryRouterResult(
            route_type=RouteType.complex,
            answer=None,
            citation_refs=[],
            confidence=confidence,
            verify=False,
            status=COMPLEX_STATUS,
            metadata={"fallback_reason": reason},
        )
