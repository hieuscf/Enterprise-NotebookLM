# =============================================================================
# File: test_query_routing_logging.py
# Module/Service: Query Router — Unified Routing Logging (FR11 / Task 4)
# Layer: Service
# Purpose: Unit tests for log_query_routing + orchestrator exactly-one query_logs.
# Responsibilities:
#   - Assert route field rules (cache/metadata/factoid/complex)
#   - Monotonic latency; best-effort failure; exactly one record
# Dependencies:
#   - pytest, AsyncMock, app.services.query_router.logging_*
# Public Exports:
#   - N/A
# Database/Table: N/A (fakes)
# Related Modules: QueryOrchestrator, QueryRoutingLogger
# Important Notes: Does not write message_generations (Chat Service).
# =============================================================================

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.models.enums import RouteType
from app.services.query_router.logging_models import QueryRoutingLogContext
from app.services.query_router.logging_service import QueryRoutingLogger, log_query_routing
from app.services.query_router.orchestrator import COMPLEX_STATUS, QueryOrchestrator
from app.services.query_router.response_models import QueryRouterResult
from app.services.query_router.schemas import CacheEntryView, CitationRef, RouteDecision



class RecordingQueryLogRepo:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.fail: Exception | None = None

    async def create_log(self, **kwargs: Any) -> SimpleNamespace:
        if self.fail is not None:
            raise self.fail
        row_id = uuid.uuid4()
        self.rows.append({"id": row_id, **kwargs})
        return SimpleNamespace(id=row_id)


def _ctx(
    *,
    route_type: RouteType,
    latency_ms: int = 12,
    llm_calls_count: int = 0,
    cache_id: uuid.UUID | None = None,
    model_used: str | None = None,
    message_id: uuid.UUID | None = None,
) -> QueryRoutingLogContext:
    return QueryRoutingLogContext(
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        query_text="example query",
        route_type=route_type,
        latency_ms=latency_ms,
        llm_calls_count=llm_calls_count,
        cache_id=cache_id,
        message_id=message_id,
        model_used=model_used,
    )


# ---------------------------------------------------------------------------
# Logging service — field rules per route
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_hit_log_fields() -> None:
    repo = RecordingQueryLogRepo()
    cache_id = uuid.uuid4()
    result = await log_query_routing(
        _ctx(route_type=RouteType.cache_hit, cache_id=cache_id, llm_calls_count=0),
        repository=repo,  # type: ignore[arg-type]
    )
    assert result.persisted is True
    assert len(repo.rows) == 1
    row = repo.rows[0]
    assert row["route_type"] == RouteType.cache_hit
    assert row["llm_calls_count"] == 0
    assert row["cache_id"] == cache_id
    assert row["model_used"] is None


@pytest.mark.asyncio
async def test_metadata_log_fields() -> None:
    repo = RecordingQueryLogRepo()
    result = await log_query_routing(
        _ctx(route_type=RouteType.metadata),
        repository=repo,  # type: ignore[arg-type]
    )
    assert result.persisted is True
    assert len(repo.rows) == 1
    row = repo.rows[0]
    assert row["route_type"] == RouteType.metadata
    assert row["llm_calls_count"] == 0
    assert row["cache_id"] is None
    assert row["model_used"] is None


@pytest.mark.asyncio
async def test_factoid_log_fields() -> None:
    repo = RecordingQueryLogRepo()
    result = await log_query_routing(
        _ctx(route_type=RouteType.factoid),
        repository=repo,  # type: ignore[arg-type]
    )
    assert result.persisted is True
    assert len(repo.rows) == 1
    row = repo.rows[0]
    assert row["route_type"] == RouteType.factoid
    assert row["llm_calls_count"] == 0
    assert row["cache_id"] is None


@pytest.mark.asyncio
async def test_complex_log_fields() -> None:
    repo = RecordingQueryLogRepo()
    result = await log_query_routing(
        _ctx(
            route_type=RouteType.complex,
            llm_calls_count=2,
            model_used="claude-sonnet-4",
        ),
        repository=repo,  # type: ignore[arg-type]
    )
    assert result.persisted is True
    assert len(repo.rows) == 1
    row = repo.rows[0]
    assert row["route_type"] == RouteType.complex
    assert row["llm_calls_count"] == 2
    assert row["model_used"] == "claude-sonnet-4"


@pytest.mark.asyncio
async def test_exactly_one_record_per_call() -> None:
    repo = RecordingQueryLogRepo()
    logger = QueryRoutingLogger(repo)  # type: ignore[arg-type]
    await logger.log_query_routing(_ctx(route_type=RouteType.metadata))
    await logger.log_query_routing(_ctx(route_type=RouteType.factoid))
    assert len(repo.rows) == 2
    # Single call never duplicates
    repo.rows.clear()
    await logger.log_query_routing(_ctx(route_type=RouteType.complex, llm_calls_count=1))
    assert len(repo.rows) == 1


@pytest.mark.asyncio
async def test_repository_failure_is_best_effort() -> None:
    repo = RecordingQueryLogRepo()
    repo.fail = RuntimeError("db down")
    with patch(
        "app.services.query_router.logging_service.logger.exception"
    ) as exc_log:
        result = await log_query_routing(
            _ctx(route_type=RouteType.metadata),
            repository=repo,  # type: ignore[arg-type]
        )
    assert result.persisted is False
    assert result.query_log_id is None
    assert result.error is not None
    assert len(repo.rows) == 0
    exc_log.assert_called_once()


# ---------------------------------------------------------------------------
# Orchestrator integration — latency + failure + route metadata return
# ---------------------------------------------------------------------------


def _decision(
    route: RouteType,
    *,
    cache_entry: CacheEntryView | None = None,
) -> RouteDecision:
    return RouteDecision(
        route_type=route,
        reason="test",
        latency_ms=1,
        query_hash="abc",
        cache_entry=cache_entry,
    )


def _build_orch(
    *,
    route: RouteType,
    repo: RecordingQueryLogRepo | None = None,
    cache_entry: CacheEntryView | None = None,
    meta_result: QueryRouterResult | None = None,
    fact_result: QueryRouterResult | None = None,
) -> tuple[QueryOrchestrator, RecordingQueryLogRepo]:
    repo = repo or RecordingQueryLogRepo()
    router = AsyncMock()
    router.route = AsyncMock(return_value=_decision(route, cache_entry=cache_entry))

    meta = AsyncMock()
    fact = AsyncMock()
    if meta_result is not None:
        meta.execute = AsyncMock(return_value=meta_result)
    if fact_result is not None:
        fact.execute = AsyncMock(return_value=fact_result)

    orch = QueryOrchestrator(
        router=router,
        metadata_branch=meta,
        factoid_branch=fact,
        query_log_repository=repo,  # type: ignore[arg-type]
    )
    return orch, repo


@pytest.mark.asyncio
async def test_orchestrator_latency_uses_monotonic_timer() -> None:
    # perf_counter sequence: start → end (42ms delta)
    times = iter([100.0, 100.042])
    orch, repo = _build_orch(route=RouteType.complex)
    with patch(
        "app.services.query_router.orchestrator.time.perf_counter",
        side_effect=lambda: next(times),
    ):
        result = await orch.handle_query(uuid.uuid4(), uuid.uuid4(), "compare X and Y")

    assert result.latency_ms == 42
    assert result.latency_ms > 0
    assert len(repo.rows) == 1
    assert repo.rows[0]["latency_ms"] == 42


@pytest.mark.asyncio
async def test_orchestrator_survives_log_failure() -> None:
    repo = RecordingQueryLogRepo()
    repo.fail = RuntimeError("insert failed")
    orch, _ = _build_orch(route=RouteType.complex, repo=repo)

    with patch(
        "app.services.query_router.logging_service.logger.exception"
    ) as exc_log:
        result = await orch.handle_query(
            uuid.uuid4(),
            uuid.uuid4(),
            "So sánh A và B",
            message_id=uuid.uuid4(),
        )

    assert result.route_type == RouteType.complex
    assert result.status == COMPLEX_STATUS
    assert result.query_log_id is None
    assert result.message_generation_id is None
    assert result.llm_calls_count == 0
    assert result.model_used is None
    exc_log.assert_called_once()


@pytest.mark.asyncio
async def test_orchestrator_cache_hit_exactly_one_log() -> None:
    from datetime import UTC, datetime, timedelta

    cache_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    entry = CacheEntryView(
        id=cache_id,
        workspace_id=workspace_id,
        query_hash="h",
        query_text="cached?",
        answer="yes",
        citation_refs=[],
        similarity_threshold=0.9,
        hit_count=1,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        match_type="exact",
    )
    orch, repo = _build_orch(route=RouteType.cache_hit, cache_entry=entry)
    result = await orch.handle_query(workspace_id, uuid.uuid4(), "cached?")

    assert result.route_type == RouteType.cache_hit
    assert result.cache_id == cache_id
    assert result.llm_calls_count == 0
    assert result.model_used is None
    assert result.message_generation_id is None
    assert len(repo.rows) == 1
    assert repo.rows[0]["route_type"] == RouteType.cache_hit
    assert repo.rows[0]["cache_id"] == cache_id
    assert repo.rows[0]["llm_calls_count"] == 0
    assert repo.rows[0]["model_used"] is None


@pytest.mark.asyncio
async def test_orchestrator_metadata_exactly_one_log() -> None:
    meta_result = QueryRouterResult(
        route_type=RouteType.metadata,
        answer="3 documents",
        citation_refs=[],
        metadata={"count": 3},
        verify=True,
    )
    orch, repo = _build_orch(route=RouteType.metadata, meta_result=meta_result)
    result = await orch.handle_query(uuid.uuid4(), uuid.uuid4(), "How many docs?")

    assert result.route_type == RouteType.metadata
    assert result.llm_calls_count == 0
    assert result.model_used is None
    assert result.cache_id is None
    assert len(repo.rows) == 1
    assert repo.rows[0]["cache_id"] is None
    assert repo.rows[0]["llm_calls_count"] == 0
    assert repo.rows[0]["model_used"] is None


@pytest.mark.asyncio
async def test_orchestrator_factoid_exactly_one_log() -> None:
    chunk_id = uuid.uuid4()
    fact_result = QueryRouterResult(
        route_type=RouteType.factoid,
        answer="RAG is retrieval-augmented generation.",
        citation_refs=[
            CitationRef(chunk_id=chunk_id, document_id=uuid.uuid4(), page_number=1)
        ],
        metadata={},
        verify=True,
    )
    orch, repo = _build_orch(route=RouteType.factoid, fact_result=fact_result)
    result = await orch.handle_query(uuid.uuid4(), uuid.uuid4(), "What is RAG?")

    assert result.route_type == RouteType.factoid
    assert result.llm_calls_count == 0
    assert result.cache_id is None
    assert len(repo.rows) == 1
    assert repo.rows[0]["route_type"] == RouteType.factoid
    assert repo.rows[0]["cache_id"] is None
    assert repo.rows[0]["llm_calls_count"] == 0


@pytest.mark.asyncio
async def test_orchestrator_complex_with_llm_overrides() -> None:
    orch, repo = _build_orch(route=RouteType.complex)
    result = await orch.handle_query(
        uuid.uuid4(),
        uuid.uuid4(),
        "Compare strategies",
        llm_calls_count=2,
        model_used="gpt-5",
    )
    assert result.route_type == RouteType.complex
    assert result.llm_calls_count == 2
    assert result.model_used == "gpt-5"
    assert len(repo.rows) == 1
    assert repo.rows[0]["llm_calls_count"] == 2
    assert repo.rows[0]["model_used"] == "gpt-5"
    assert result.message_generation_id is None
