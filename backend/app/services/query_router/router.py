# =============================================================================
# File: router.py
# Module/Service: Query Router (FR11)
# Layer: Service
# Purpose: Orchestrate cache check then QueryClassifier (0 LLM).
# Responsibilities:
#   - Exact → semantic cache; then classify metadata / factoid / complex
#   - Retrieve once for factoid/complex so branches can execute extractively
# Dependencies:
#   - QueryCacheService, QueryClassifier, HybridRetrievalService, RouterRules
# Public Exports:
#   - QueryRouter
# Database/Table: query_cache (via cache service)
# Related Modules: Chat Service, Hybrid Retrieval
# Important Notes:
#   - Classifier never decides cache_hit.
#   - Retrieval called at most once after classification (factoid/complex).
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
from app.services.retrieval.schemas import RetrievalResult

logger = get_logger(__name__)


class QueryRouter:
    """Query Router — cache check + injected QueryClassifier."""

    def __init__(
        self,
        *,
        rules: RouterRules,
        cache: QueryCacheService,
        classifier: QueryClassifier,
        hybrid: HybridRetrievalService,
    ) -> None:
        self._rules = rules
        self._cache = cache
        self._classifier = classifier
        self._hybrid = hybrid

    async def route(
        self,
        workspace_id: UUID,
        user_id: UUID,
        query_text: str,
    ) -> RouteDecision:
        """Classify ``query_text`` into cache_hit / metadata / factoid / complex.

        Args:
            workspace_id: Tenant scope (RBAC enforced by callers).
            user_id: Authenticated user (for logging / future query_logs).
            query_text: Raw user question.

        Returns:
            ``RouteDecision`` — no answer generation, 0 LLM calls.
        """
        started = time.perf_counter()
        nq = build_normalized_query(query_text)
        query_vector: list[float] | None = None
        similarity: float | None = None
        factoid_score: float | None = None
        retrieval: RetrievalResult | None = None

        # --- 1–2: normalize + hash (done) ---
        # --- 3: Exact Cache Check ---
        exact = await self._cache.check_exact(
            workspace_id=workspace_id,
            query_hash=nq.query_hash,
        )
        if exact is not None:
            return self._finish(
                started=started,
                workspace_id=workspace_id,
                user_id=user_id,
                decision=RouteDecision(
                    route_type=RouteType.cache_hit,
                    reason="exact_cache_hit",
                    latency_ms=0,
                    query_hash=nq.query_hash,
                    cache_entry=exact,
                    similarity=1.0,
                ),
                cache_hit=True,
                similarity=1.0,
                factoid_score=None,
            )

        # --- 4: Semantic Cache Check ---
        semantic, query_vector, similarity = await self._cache.check_semantic(
            workspace_id=workspace_id,
            normalized_text=nq.normalized,
            query_vector=None,
        )
        if semantic is not None:
            return self._finish(
                started=started,
                workspace_id=workspace_id,
                user_id=user_id,
                decision=RouteDecision(
                    route_type=RouteType.cache_hit,
                    reason="semantic_cache_hit",
                    latency_ms=0,
                    query_hash=nq.query_hash,
                    cache_entry=semantic,
                    similarity=similarity,
                ),
                cache_hit=True,
                similarity=similarity,
                factoid_score=None,
            )

        # --- 5: Intent classification (never cache_hit) ---
        route_type, reason = self._classify(query_text, workspace_id)
        if route_type == RouteType.cache_hit:
            # Defensive: classifiers must not emit cache_hit; treat as complex.
            logger.warning("classifier_returned_cache_hit_fallback_complex")
            route_type = RouteType.complex
            reason = "classifier_forbidden_cache_hit_fallback_complex"

        if route_type == RouteType.metadata:
            return self._finish(
                started=started,
                workspace_id=workspace_id,
                user_id=user_id,
                decision=RouteDecision(
                    route_type=RouteType.metadata,
                    reason=reason,
                    latency_ms=0,
                    query_hash=nq.query_hash,
                    metadata_payload={"reason": reason},
                    similarity=similarity,
                ),
                cache_hit=False,
                similarity=similarity,
                factoid_score=None,
            )

        # --- 6: Retrieve once for factoid / complex execution ---
        retrieval = await self._hybrid.retrieve(
            workspace_id,
            nq.original.strip() or nq.normalized,
            top_k=self._rules.factoid_top_k,
        )
        if retrieval.items:
            top = retrieval.items[0]
            factoid_score = float(top.score if top.score is not None else top.raw_score)

        if route_type == RouteType.factoid:
            return self._finish(
                started=started,
                workspace_id=workspace_id,
                user_id=user_id,
                decision=RouteDecision(
                    route_type=RouteType.factoid,
                    reason=reason,
                    latency_ms=0,
                    query_hash=nq.query_hash,
                    retrieval_result=retrieval,
                    similarity=similarity,
                    factoid_score=factoid_score,
                ),
                cache_hit=False,
                similarity=similarity,
                factoid_score=factoid_score,
            )

        return self._finish(
            started=started,
            workspace_id=workspace_id,
            user_id=user_id,
            decision=RouteDecision(
                route_type=RouteType.complex,
                reason=reason or "default_complex",
                latency_ms=0,
                query_hash=nq.query_hash,
                retrieval_result=retrieval,
                similarity=similarity,
                factoid_score=factoid_score,
                extras={"query_vector_cached": bool(query_vector)},
            ),
            cache_hit=False,
            similarity=similarity,
            factoid_score=factoid_score,
        )

    def _classify(self, query_text: str, workspace_id: UUID) -> tuple[RouteType, str]:
        """Run classifier; prefer detailed result when available."""
        detailed = getattr(self._classifier, "classify_detailed", None)
        if callable(detailed):
            result = detailed(query_text, workspace_id)
            return result.route_type, result.reason
        route = self._classifier.classify(query_text, workspace_id)
        return route, f"classified={route.value}"

    def _finish(
        self,
        *,
        started: float,
        workspace_id: UUID,
        user_id: UUID,
        decision: RouteDecision,
        cache_hit: bool,
        similarity: float | None,
        factoid_score: float | None,
    ) -> RouteDecision:
        latency = int((time.perf_counter() - started) * 1000)
        decision.latency_ms = latency
        logger.info(
            "query_router_decision",
            workspace_id=str(workspace_id),
            user_id=str(user_id),
            query_hash=decision.query_hash,
            route_type=decision.route_type.value,
            cache_hit=cache_hit,
            similarity=similarity,
            factoid_score=factoid_score,
            latency=latency,
            reason=decision.reason,
        )
        return decision
