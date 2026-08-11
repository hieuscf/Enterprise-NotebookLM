# =============================================================================
# File: router.py
# Module/Service: Query Router (FR11)
# Layer: Service
# Purpose: Always route chat queries directly to complex (no cache check).
# Responsibilities:
#   - Normalize/hash the query for logging correlation only
#   - Always emit route_type=complex for Chat → ComplexQueryPipeline
# Dependencies:
#   - QueryClassifier, HybridRetrievalService, RouterRules (retained for DI/compat)
# Public Exports:
#   - QueryRouter
# Database/Table: N/A (query_cache is no longer consulted from chat routing)
# Related Modules: Chat Service, Hybrid Retrieval, QueryOrchestrator
# Important Notes:
#   - Mandatory product rule: every chat query goes straight into complex.
#   - Cache (query_cache) is intentionally NOT checked here anymore — it never
#     short-circuited the answer once complex became mandatory, so checking
#     it only added latency with no benefit. See cache.py / cache_writer.py
#     for the (currently unused-by-chat) cache subsystem.
#   - Classifier / hybrid are retained for DI/compat but are not used for
#     chat routing.
# =============================================================================

from __future__ import annotations

import time
from uuid import UUID

from app.config.router_rules import RouterRules
from app.core.logging import get_logger
from app.models.enums import RouteType
from app.services.query_router.cache import build_normalized_query
from app.services.query_router.classifier import QueryClassifier
from app.services.query_router.schemas import RouteDecision
from app.services.retrieval.hybrid_retrieval_service import HybridRetrievalService

logger = get_logger(__name__)


class QueryRouter:
    """Query Router — always routes chat queries directly to complex."""

    def __init__(
        self,
        *,
        rules: RouterRules,
        classifier: QueryClassifier,
        hybrid: HybridRetrievalService,
    ) -> None:
        self._rules = rules
        self._classifier = classifier
        self._hybrid = hybrid

    async def route(
        self,
        workspace_id: UUID,
        user_id: UUID,
        query_text: str,
    ) -> RouteDecision:
        """Always route straight to ``complex`` — no cache check.

        Args:
            workspace_id: Tenant scope (RBAC enforced by callers).
            user_id: Authenticated user (for logging / future query_logs).
            query_text: Raw user question.

        Returns:
            ``RouteDecision`` with ``route_type=complex``. No answer
            generation, 0 LLM calls, no cache lookup.
        """
        started = time.perf_counter()
        nq = build_normalized_query(query_text)

        decision = RouteDecision(
            route_type=RouteType.complex,
            reason="direct_complex",
            latency_ms=0,
            query_hash=nq.query_hash,
            extras={"query_text": nq.original.strip() or nq.normalized},
        )
        latency = int((time.perf_counter() - started) * 1000)
        decision.latency_ms = latency
        logger.info(
            "query_router_decision",
            workspace_id=str(workspace_id),
            user_id=str(user_id),
            query_hash=decision.query_hash,
            route_type=decision.route_type.value,
            latency=latency,
            reason=decision.reason,
        )
        return decision
