# =============================================================================
# File: query_orchestrator.py
# Module/Service: Query Router Execution
# Layer: Presentation / DI
# Purpose: FastAPI dependency factory for QueryOrchestrator (Chat Service entry).
# Responsibilities:
#   - Wire QueryRouter + execution branches + FR14 ComplexQueryPipeline
# Dependencies:
#   - get_db_session, Hybrid Retrieval adapters, QueryCache / RouterRules, agents
# Public Exports:
#   - get_query_orchestrator
# Database/Table: N/A
# Related Modules: app.services.query_router.orchestrator, ComplexQueryPipeline
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
from app.repositories.agent_events import AgentEventRepository
from app.repositories.metadata_query import PostgresMetadataRepository
from app.repositories.query_logs import QueryObservabilityRepository
from app.repositories.retrieval import RetrievalRepository
from app.repositories.retrieval_records import RetrievalRecordRepository
from app.repositories.workspace_members import WorkspaceMemberRepository
from app.services.chat.answer_generator import PromptAnswerGenerator
from app.services.chat.complex_query_pipeline import ComplexQueryPipeline
from app.services.chat.context_assembly import RetrievalRepositoryContextPort
from app.services.event_policy.agents.graph_agent import GraphAgent
from app.services.event_policy.agents.rewrite_agent import RewriteAgent
from app.services.event_policy.agents.sql_agent import SqlAgent
from app.services.query_router.classifier import build_rule_based_classifier
from app.services.query_router.factoid_branch import FactoidBranch
from app.services.query_router.handlers.metadata_handler import MetadataHandler
from app.services.query_router.lightweight_retriever import LightweightVectorRetriever
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
    """Build the sole Chat-facing query execution orchestrator (with FR14)."""
    settings = get_settings()
    rules = get_router_rules()
    retrieval_repo = RetrievalRepository(session)
    vector_search = VectorSearch(
        settings=settings,
        qdrant=get_qdrant_store(),
        repo=retrieval_repo,
    )
    hybrid = HybridRetrievalService(
        settings=settings,
        vector_search=vector_search,
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
    router = QueryRouter(
        rules=rules,
        classifier=build_rule_based_classifier(settings),
        hybrid=hybrid,
    )
    observability = QueryObservabilityRepository(session)
    metadata_handler = MetadataHandler(
        repository=PostgresMetadataRepository(session),
    )
    complex_pipeline = ComplexQueryPipeline(
        settings=settings,
        hybrid=hybrid,
        agent_events=AgentEventRepository(session),
        retrieval_records=RetrievalRecordRepository(session),
        observability=observability,
        rewrite_agent=RewriteAgent(settings),
        graph_agent=GraphAgent(settings, get_neo4j_graph()),
        sql_agent=SqlAgent(metadata_handler),
        answer_generator=PromptAnswerGenerator(
            settings,
            context_port=RetrievalRepositoryContextPort(retrieval_repo),
        ),
        retrieval_top_k=max(1, int(settings.retrieval_per_source_top_k)),
    )
    return QueryOrchestrator(
        router=router,
        metadata_branch=MetadataBranch(
            retrieval_repo=retrieval_repo,
            member_repo=WorkspaceMemberRepository(session),
        ),
        factoid_branch=FactoidBranch(
            retrieval_repo=retrieval_repo,
            retriever=LightweightVectorRetriever(vector_search),
            settings=settings,
        ),
        query_log_repository=observability,
        complex_pipeline=complex_pipeline,
    )
