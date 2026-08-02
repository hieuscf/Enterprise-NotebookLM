# =============================================================================
# File: query_orchestrator.py
# Module/Service: Query Router Execution
# Layer: Presentation / DI
# Purpose: FastAPI dependency factory for QueryOrchestrator (Chat Service entry).
# Responsibilities:
#   - Wire QueryRouter + execution branches + observability repository
# Dependencies:
#   - get_db_session, Hybrid Retrieval adapters, QueryCache / RouterRules
# Public Exports:
#   - get_query_orchestrator
# Database/Table: N/A
# Related Modules: app.services.query_router.orchestrator
# Important Notes: RBAC must be enforced by the calling route (workspace member).
# =============================================================================

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.elasticsearch_bm25 import get_elasticsearch_bm25
from app.adapters.neo4j_graph import get_neo4j_graph
from app.adapters.qdrant_store import get_qdrant_store
from app.config.router_rules import get_router_rules
from app.core.config import get_settings
from app.db.session import get_db_session
from app.repositories.query_cache import QueryCacheRepository
from app.repositories.query_logs import QueryObservabilityRepository
from app.repositories.retrieval import RetrievalRepository
from app.repositories.workspace_members import WorkspaceMemberRepository
from app.services.query_router.cache import QueryCacheService
from app.services.query_router.classifier import build_rule_based_classifier
from app.services.query_router.factoid_branch import FactoidBranch
from app.services.query_router.metadata_branch import MetadataBranch
from app.services.query_router.orchestrator import QueryOrchestrator
from app.services.query_router.router import QueryRouter
from app.services.retrieval.bm25_search import Bm25Search
from app.services.retrieval.graph_search import GraphSearch
from app.services.retrieval.hybrid_retrieval_service import HybridRetrievalService
from app.services.retrieval.reranker import Reranker
from app.services.retrieval.vector_search import VectorSearch


def get_query_orchestrator(
    session: AsyncSession = Depends(get_db_session),
) -> QueryOrchestrator:
    """Build the sole Chat-facing query execution orchestrator."""
    settings = get_settings()
    rules = get_router_rules()
    retrieval_repo = RetrievalRepository(session)
    hybrid = HybridRetrievalService(
        settings=settings,
        vector_search=VectorSearch(
            settings=settings,
            qdrant=get_qdrant_store(),
            repo=retrieval_repo,
        ),
        bm25_search=Bm25Search(
            settings=settings,
            elasticsearch=get_elasticsearch_bm25(),
            repo=retrieval_repo,
        ),
        graph_search=GraphSearch(
            settings=settings,
            neo4j=get_neo4j_graph(),
            repo=retrieval_repo,
        ),
        reranker=Reranker(settings),
    )
    cache = QueryCacheService(
        settings=settings,
        rules=rules,
        repo=QueryCacheRepository(session),
        qdrant=get_qdrant_store(),
    )
    router = QueryRouter(
        rules=rules,
        cache=cache,
        classifier=build_rule_based_classifier(settings),
        hybrid=hybrid,
    )
    return QueryOrchestrator(
        router=router,
        metadata_branch=MetadataBranch(
            retrieval_repo=retrieval_repo,
            member_repo=WorkspaceMemberRepository(session),
        ),
        factoid_branch=FactoidBranch(retrieval_repo=retrieval_repo),
        observability=QueryObservabilityRepository(session),
    )
