# =============================================================================
# File: router.py
# Module/Service: Query Router (FR11)
# Layer: Service
# Purpose: Classify chat queries into cache_hit / metadata / section_extraction /
#          factoid / complex.
# Responsibilities:
#   - Exact then semantic query_cache lookup (0 LLM) before classification
#   - Rule-based classifier for metadata / section_extraction / factoid / complex
#   - Never generate answers — QueryOrchestrator executes the chosen branch
# Dependencies:
#   - QueryClassifier, QueryCacheService, RouterRules, HybridRetrievalService
# Public Exports:
#   - QueryRouter
# Database/Table: query_cache (via QueryCacheService)
# Related Modules: Chat Service, QueryOrchestrator, Hybrid Retrieval
# Important Notes:
#   - Classifier never returns cache_hit — that is a cache lookup state.
#   - Hybrid retrieval is owned by ComplexQueryPipeline / FactoidHandler,
#     not by this router.
#   - Cache lookup failures must not block classification.
# =============================================================================

from __future__ import annotations

import time
from uuid import UUID

from app.config.router_rules import RouterRules
from app.core.logging import get_logger
from app.models.enums import RouteType
from app.services.query_router.cache import QueryCacheService, build_normalized_query
from app.services.query_router.classifier import QueryClassifier
from app.services.query_router.schemas import RouteDecision
from app.services.retrieval.hybrid_retrieval_service import HybridRetrievalService

logger = get_logger(__name__)


class QueryRouter:
    """FR11 Query Router — cache first, then metadata / section / factoid / complex."""

    def __init__(
        self,
        *,
        rules: RouterRules,
        classifier: QueryClassifier,
        hybrid: HybridRetrievalService,
        cache: QueryCacheService | None = None,
    ) -> None:
        self._rules = rules
        self._classifier = classifier
        self._hybrid = hybrid
        self._cache = cache

    async def route(
        self,
        workspace_id: UUID,
        user_id: UUID,
        query_text: str,
    ) -> RouteDecision:
        """Classify ``query_text`` for Chat — no answer generation, 0 LLM.

        Args:
            workspace_id: Tenant scope (RBAC enforced by callers).
            user_id: Authenticated user (logging / cache isolation).
            query_text: Raw user question.

        Returns:
            ``RouteDecision`` with ``cache_hit``, ``metadata``, ``section_extraction``,
            ``factoid``, or ``complex``. Cache hits include ``cache_entry``.
        """
        started = time.perf_counter()
        nq = build_normalized_query(query_text)
        extras: dict[str, object] = {"query_text": nq.original.strip() or nq.normalized}

        cache_decision = await self._lookup_cache(
            workspace_id=workspace_id,
            query_hash=nq.query_hash,
            normalized_text=nq.normalized,
        )
        if cache_decision is not None:
            latency = int((time.perf_counter() - started) * 1000)
            cache_decision.latency_ms = latency
            cache_decision.query_hash = nq.query_hash
            cache_decision.extras = extras
            self._log_decision(workspace_id, user_id, cache_decision)
            return cache_decision

        route_type, reason = self._classify_with_reason(query_text, workspace_id)
        latency = int((time.perf_counter() - started) * 1000)
        decision = RouteDecision(
            route_type=route_type,
            reason=reason,
            latency_ms=latency,
            query_hash=nq.query_hash,
            extras=extras,
        )
        self._log_decision(workspace_id, user_id, decision)
        return decision

    async def _lookup_cache(
        self,
        *,
        workspace_id: UUID,
        query_hash: str,
        normalized_text: str,
    ) -> RouteDecision | None:
        if self._cache is None:
            return None
        try:
            exact = await self._cache.check_exact(
                workspace_id=workspace_id,
                query_hash=query_hash,
            )
        except Exception as exc:  # noqa: BLE001 — cache must not block routing
            logger.warning(
                "query_cache_exact_lookup_failed",
                workspace_id=str(workspace_id),
                error=type(exc).__name__,
            )
            return None
        if exact is not None:
            return RouteDecision(
                route_type=RouteType.cache_hit,
                reason="exact_cache",
                latency_ms=0,
                query_hash=query_hash,
                cache_entry=exact,
                similarity=exact.similarity,
            )
        try:
            semantic, _vector, similarity = await self._cache.check_semantic(
                workspace_id=workspace_id,
                normalized_text=normalized_text,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "query_cache_semantic_lookup_failed",
                workspace_id=str(workspace_id),
                error=type(exc).__name__,
            )
            return None
        if semantic is None:
            return None
        return RouteDecision(
            route_type=RouteType.cache_hit,
            reason="semantic_cache",
            latency_ms=0,
            query_hash=query_hash,
            cache_entry=semantic,
            similarity=similarity if similarity is not None else semantic.similarity,
        )

    def _classify_with_reason(
        self,
        query_text: str,
        workspace_id: UUID,
    ) -> tuple[RouteType, str]:
        detailed = getattr(self._classifier, "classify_detailed", None)
        if callable(detailed):
            result = detailed(query_text, workspace_id)
            route = result.route_type
            if route is RouteType.cache_hit:
                route = RouteType.complex
            reason = str(getattr(result, "reason", "") or f"classified_{route.value}")
            return route, reason
        route = self._classifier.classify(query_text, workspace_id)
        if route is RouteType.cache_hit:
            route = RouteType.complex
        return route, f"classified_{route.value}"

    def _log_decision(
        self,
        workspace_id: UUID,
        user_id: UUID,
        decision: RouteDecision,
    ) -> None:
        logger.info(
            "query_router_decision",
            workspace_id=str(workspace_id),
            user_id=str(user_id),
            query_hash=decision.query_hash,
            route_type=decision.route_type.value,
            latency=decision.latency_ms,
            reason=decision.reason,
        )
