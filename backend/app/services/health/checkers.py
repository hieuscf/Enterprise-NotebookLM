# =============================================================================
# File: checkers.py
# Module/Service: Observability Module — System Health (FR13)
# Layer: Adapter
# Purpose: Lightweight dependency probes for GET /admin/health.
# Responsibilities:
#   - Probe Postgres / Redis / Celery / MinIO / Qdrant / Neo4j / ES
#   - Config-only checks for LLM + embedding (no generation / embed calls)
#   - Return sanitized messages (never secrets, URLs with credentials)
# Dependencies:
#   - Settings, AsyncSession, redis, celery_app, existing adapters
# Public Exports:
#   - ProbeResult, run_all_probes
# Database/Table: N/A (SELECT 1 only for Postgres)
# Related Modules: app.services.health.service
# Important Notes: No RAG, OCR, embedding batch, or LLM generation.
# =============================================================================

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.schemas.admin import HealthCategoryLiteral, HealthStatusLiteral

PROBE_TIMEOUT_S = 3.0


@dataclass(frozen=True, slots=True)
class ProbeResult:
    id: str
    name: str
    category: HealthCategoryLiteral
    status: HealthStatusLiteral
    provider: str | None
    message: str | None
    checked_at: datetime
    response_time_ms: int | None
    critical: bool


def _now() -> datetime:
    return datetime.now(UTC)


def _ms_since(start: float) -> int:
    return max(0, int((time.perf_counter() - start) * 1000))


async def _with_timeout(coro: Awaitable[ProbeResult]) -> ProbeResult:
    return await asyncio.wait_for(coro, timeout=PROBE_TIMEOUT_S)


async def check_postgresql(session: AsyncSession) -> ProbeResult:
    start = time.perf_counter()
    checked = _now()
    try:
        await session.execute(text("SELECT 1"))
        return ProbeResult(
            id="postgresql",
            name="PostgreSQL",
            category="core",
            status="healthy",
            provider="postgresql",
            message="Database connection operational",
            checked_at=checked,
            response_time_ms=_ms_since(start),
            critical=True,
        )
    except Exception:
        return ProbeResult(
            id="postgresql",
            name="PostgreSQL",
            category="core",
            status="unhealthy",
            provider="postgresql",
            message="Database connection unavailable",
            checked_at=checked,
            response_time_ms=_ms_since(start),
            critical=True,
        )


async def check_redis(settings: Settings) -> ProbeResult:
    start = time.perf_counter()
    checked = _now()

    def _ping() -> None:
        client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2)
        try:
            if not client.ping():
                raise RuntimeError("ping failed")
        finally:
            client.close()

    try:
        await asyncio.to_thread(_ping)
        return ProbeResult(
            id="redis",
            name="Redis",
            category="core",
            status="healthy",
            provider="redis",
            message="Cache / message broker available",
            checked_at=checked,
            response_time_ms=_ms_since(start),
            critical=True,
        )
    except Exception:
        return ProbeResult(
            id="redis",
            name="Redis",
            category="core",
            status="unhealthy",
            provider="redis",
            message="Cache / message broker unavailable",
            checked_at=checked,
            response_time_ms=_ms_since(start),
            critical=True,
        )


async def check_celery_worker() -> ProbeResult:
    start = time.perf_counter()
    checked = _now()

    def _inspect() -> dict | None:
        from app.workers.celery_app import celery_app

        inspector = celery_app.control.inspect(timeout=2.0)
        if inspector is None:
            return None
        return inspector.ping()

    try:
        replies = await asyncio.to_thread(_inspect)
        if not replies:
            return ProbeResult(
                id="celery_worker",
                name="Celery Worker",
                category="core",
                status="unhealthy",
                provider="celery",
                message="No background workers responding",
                checked_at=checked,
                response_time_ms=_ms_since(start),
                critical=True,
            )
        return ProbeResult(
            id="celery_worker",
            name="Celery Worker",
            category="core",
            status="healthy",
            provider="celery",
            message="Background workers responding",
            checked_at=checked,
            response_time_ms=_ms_since(start),
            critical=True,
        )
    except Exception:
        return ProbeResult(
            id="celery_worker",
            name="Celery Worker",
            category="core",
            status="unknown",
            provider="celery",
            message="Worker health check timed out or failed",
            checked_at=checked,
            response_time_ms=_ms_since(start),
            critical=True,
        )


async def check_object_storage(settings: Settings) -> ProbeResult:
    start = time.perf_counter()
    checked = _now()

    def _bucket() -> None:
        from app.adapters.minio_storage import MinioStorageAdapter

        adapter = MinioStorageAdapter(settings)
        # bucket_exists is a lightweight probe; ensure_bucket may create — avoid create.
        if not adapter._client.bucket_exists(adapter._bucket):  # noqa: SLF001
            raise RuntimeError("bucket missing")

    try:
        await asyncio.to_thread(_bucket)
        return ProbeResult(
            id="object_storage",
            name="Object Storage",
            category="core",
            status="healthy",
            provider="minio",
            message="Document storage available",
            checked_at=checked,
            response_time_ms=_ms_since(start),
            critical=True,
        )
    except Exception:
        return ProbeResult(
            id="object_storage",
            name="Object Storage",
            category="core",
            status="unhealthy",
            provider="minio",
            message="Document storage unavailable",
            checked_at=checked,
            response_time_ms=_ms_since(start),
            critical=True,
        )


async def check_vector_store(settings: Settings) -> ProbeResult:
    start = time.perf_counter()
    checked = _now()
    provider = (settings.vector_store or "qdrant").strip().lower() or "qdrant"

    def _probe() -> None:
        if provider == "qdrant":
            from qdrant_client import QdrantClient

            client = QdrantClient(url=settings.qdrant_url, prefer_grpc=False, timeout=2)
            client.get_collections()
            return
        raise RuntimeError(f"unsupported vector store: {provider}")

    try:
        await asyncio.to_thread(_probe)
        return ProbeResult(
            id="vector_store",
            name="Vector Store",
            category="ai_retrieval",
            status="healthy",
            provider=provider,
            message="Vector store responding",
            checked_at=checked,
            response_time_ms=_ms_since(start),
            critical=False,
        )
    except Exception:
        return ProbeResult(
            id="vector_store",
            name="Vector Store",
            category="ai_retrieval",
            status="unhealthy",
            provider=provider,
            message="Vector store unavailable",
            checked_at=checked,
            response_time_ms=_ms_since(start),
            critical=False,
        )


async def check_knowledge_graph(settings: Settings) -> ProbeResult:
    start = time.perf_counter()
    checked = _now()

    def _probe() -> None:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        try:
            with driver.session() as session:
                session.run("RETURN 1 AS ok").single()
        finally:
            driver.close()

    try:
        await asyncio.to_thread(_probe)
        return ProbeResult(
            id="knowledge_graph",
            name="Knowledge Graph",
            category="ai_retrieval",
            status="healthy",
            provider="neo4j",
            message="Knowledge graph responding",
            checked_at=checked,
            response_time_ms=_ms_since(start),
            critical=False,
        )
    except Exception:
        return ProbeResult(
            id="knowledge_graph",
            name="Knowledge Graph",
            category="ai_retrieval",
            status="unhealthy",
            provider="neo4j",
            message="Knowledge graph unavailable",
            checked_at=checked,
            response_time_ms=_ms_since(start),
            critical=False,
        )


async def check_fulltext_search(settings: Settings) -> ProbeResult:
    start = time.perf_counter()
    checked = _now()

    def _probe() -> None:
        from elasticsearch import Elasticsearch

        client = Elasticsearch(settings.elasticsearch_url, request_timeout=2)
        if not client.ping():
            raise RuntimeError("ping failed")

    try:
        await asyncio.to_thread(_probe)
        return ProbeResult(
            id="fulltext_search",
            name="Full-text Search",
            category="ai_retrieval",
            status="healthy",
            provider="elasticsearch",
            message="Full-text search responding",
            checked_at=checked,
            response_time_ms=_ms_since(start),
            critical=False,
        )
    except Exception:
        return ProbeResult(
            id="fulltext_search",
            name="Full-text Search",
            category="ai_retrieval",
            status="unhealthy",
            provider="elasticsearch",
            message="Full-text search unavailable",
            checked_at=checked,
            response_time_ms=_ms_since(start),
            critical=False,
        )


async def check_embedding_service(settings: Settings) -> ProbeResult:
    """Config-only probe — never runs an embedding request (avoids cost)."""
    start = time.perf_counter()
    checked = _now()
    provider = (settings.embedding_provider or "local").strip().lower() or "local"

    if provider == "local":
        return ProbeResult(
            id="embedding_service",
            name="Embedding Service",
            category="ai_retrieval",
            status="healthy",
            provider="local",
            message="Local embedding provider configured",
            checked_at=checked,
            response_time_ms=_ms_since(start),
            critical=False,
        )

    key = (settings.embedding_api_key or "").strip()
    if key:
        return ProbeResult(
            id="embedding_service",
            name="Embedding Service",
            category="ai_retrieval",
            status="healthy",
            provider=provider,
            message="Embedding credentials configured (connectivity not probed)",
            checked_at=checked,
            response_time_ms=_ms_since(start),
            critical=False,
        )
    return ProbeResult(
        id="embedding_service",
        name="Embedding Service",
        category="ai_retrieval",
        status="degraded",
        provider=provider,
        message="Embedding API key not configured",
        checked_at=checked,
        response_time_ms=_ms_since(start),
        critical=False,
    )


async def check_llm_provider(settings: Settings) -> ProbeResult:
    """Config-only probe — never calls the LLM provider (avoids generation cost)."""
    start = time.perf_counter()
    checked = _now()
    provider = (settings.chat_llm_provider or "anthropic").strip().lower() or "anthropic"

    if provider == "anthropic":
        key = (settings.anthropic_api_key or "").strip()
    elif provider == "openai":
        key = (settings.openai_api_key or "").strip()
    else:
        return ProbeResult(
            id="llm_provider",
            name="LLM Provider",
            category="ai_retrieval",
            status="degraded",
            provider=provider,
            message="Chat LLM provider is not fully wired",
            checked_at=checked,
            response_time_ms=_ms_since(start),
            critical=True,
        )

    if key:
        return ProbeResult(
            id="llm_provider",
            name="LLM Provider",
            category="ai_retrieval",
            status="healthy",
            provider=provider,
            message="LLM credentials configured (connectivity not probed)",
            checked_at=checked,
            response_time_ms=_ms_since(start),
            critical=True,
        )
    return ProbeResult(
        id="llm_provider",
        name="LLM Provider",
        category="ai_retrieval",
        status="unhealthy",
        provider=provider,
        message="LLM API key not configured",
        checked_at=checked,
        response_time_ms=_ms_since(start),
        critical=True,
    )


async def _safe_probe(
    factory: Callable[[], Awaitable[ProbeResult]],
    *,
    fallback_id: str,
    fallback_name: str,
    category: HealthCategoryLiteral,
    critical: bool,
    provider: str | None,
) -> ProbeResult:
    try:
        return await _with_timeout(factory())
    except TimeoutError:
        return ProbeResult(
            id=fallback_id,
            name=fallback_name,
            category=category,
            status="unknown",
            provider=provider,
            message="Health check timed out",
            checked_at=_now(),
            response_time_ms=int(PROBE_TIMEOUT_S * 1000),
            critical=critical,
        )
    except Exception:
        return ProbeResult(
            id=fallback_id,
            name=fallback_name,
            category=category,
            status="unknown",
            provider=provider,
            message="Health check failed",
            checked_at=_now(),
            response_time_ms=None,
            critical=critical,
        )


async def run_all_probes(
    *,
    session: AsyncSession,
    settings: Settings,
) -> list[ProbeResult]:
    """Run all dependency probes concurrently; never raise."""
    tasks = [
        _safe_probe(
            lambda: check_postgresql(session),
            fallback_id="postgresql",
            fallback_name="PostgreSQL",
            category="core",
            critical=True,
            provider="postgresql",
        ),
        _safe_probe(
            lambda: check_redis(settings),
            fallback_id="redis",
            fallback_name="Redis",
            category="core",
            critical=True,
            provider="redis",
        ),
        _safe_probe(
            check_celery_worker,
            fallback_id="celery_worker",
            fallback_name="Celery Worker",
            category="core",
            critical=True,
            provider="celery",
        ),
        _safe_probe(
            lambda: check_object_storage(settings),
            fallback_id="object_storage",
            fallback_name="Object Storage",
            category="core",
            critical=True,
            provider="minio",
        ),
        _safe_probe(
            lambda: check_llm_provider(settings),
            fallback_id="llm_provider",
            fallback_name="LLM Provider",
            category="ai_retrieval",
            critical=True,
            provider=None,
        ),
        _safe_probe(
            lambda: check_embedding_service(settings),
            fallback_id="embedding_service",
            fallback_name="Embedding Service",
            category="ai_retrieval",
            critical=False,
            provider=None,
        ),
        _safe_probe(
            lambda: check_vector_store(settings),
            fallback_id="vector_store",
            fallback_name="Vector Store",
            category="ai_retrieval",
            critical=False,
            provider=None,
        ),
        _safe_probe(
            lambda: check_knowledge_graph(settings),
            fallback_id="knowledge_graph",
            fallback_name="Knowledge Graph",
            category="ai_retrieval",
            critical=False,
            provider="neo4j",
        ),
        _safe_probe(
            lambda: check_fulltext_search(settings),
            fallback_id="fulltext_search",
            fallback_name="Full-text Search",
            category="ai_retrieval",
            critical=False,
            provider="elasticsearch",
        ),
    ]
    return list(await asyncio.gather(*tasks))
