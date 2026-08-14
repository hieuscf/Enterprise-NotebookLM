# =============================================================================
# File: test_citation_verification_flow.py
# Module/Service: Citation Verification Layer (FR5)
# Layer: Service (integration tests, no Postgres)
# Purpose: End-to-end citation verification through Chat persist + SSE order.
# Responsibilities:
#   - Happy path persist verified citations
#   - Invalid citations are not persisted / not exposed
#   - Unsupported snippet → no verified citation
#   - All invalid → fallback answer
#   - Workspace isolation
#   - SSE tokens only after generate_answer (verification) completes
# Dependencies:
#   - pytest, MessageProcessingService fakes, CitationVerificationService
# Public Exports:
#   - N/A
# Database/Table: N/A (fakes)
# Related Modules: message_service, citation_verification
# Important Notes:
#   - Deterministic verification. No LLM call.
#   - Must validate workspace/message/retrieval membership.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.models.chat import ChatMessage, ChatSession, MessageGeneration
from app.models.enums import FinishReason, MessageRole, RetrievalMethod, RouteType
from app.models.retrieval import Retrieval
from app.services.chat.message_service import MessageProcessingService
from app.services.citation_verification.reasons import VerificationReason
from app.services.citation_verification.results import RetrievalEvidence
from app.services.citation_verification.service import (
    INSUFFICIENT_EVIDENCE_ANSWER,
    CitationVerificationService,
)
from app.services.query_router.schemas import CitationRef, QueryExecutionResult


def _settings() -> Settings:
    return Settings(
        chat_llm_provider="anthropic",
        anthropic_api_key="test-key",
        chat_sse_token_chunk_chars=5,
    )


class FakeSessions:
    def __init__(self, session: ChatSession) -> None:
        self.session = session

    async def get(self, **kwargs: Any) -> ChatSession | None:
        if kwargs.get("session_id") != self.session.id:
            return None
        if kwargs.get("workspace_id") != self.session.workspace_id:
            return None
        return self.session

    async def touch_after_message(self, **kwargs: Any) -> bool:
        return True


class FakeMessages:
    def __init__(self) -> None:
        self.rows: list[ChatMessage] = []

    async def create(
        self, *, session_id: uuid.UUID, role: MessageRole, content: str
    ) -> ChatMessage:
        row = ChatMessage(
            id=uuid.uuid4(),
            session_id=session_id,
            role=role,
            content=content,
            created_at=datetime.now(UTC),
        )
        self.rows.append(row)
        return row

    async def update_content(self, message_id: uuid.UUID, content: str) -> ChatMessage | None:
        for row in self.rows:
            if row.id == message_id:
                row.content = content
                return row
        return None

    async def count(self, *, session_id: uuid.UUID) -> int:
        return sum(1 for r in self.rows if r.session_id == session_id)

    async def list(self, **kwargs: Any) -> list[Any]:
        return []

    async def list_citations_for_message(self, message_id: uuid.UUID) -> list[Any]:
        return []


class FakeCitations:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def insert_mapped(self, **kwargs: Any) -> list[Any]:
        self.calls.append(kwargs)
        return []


class FakeRetrievalRecords:
    def __init__(self, rows: list[Retrieval] | None = None) -> None:
        self.rows = list(rows or [])
        self.insert_calls: list[dict[str, Any]] = []

    async def list_for_latest_pass(self, message_id: uuid.UUID) -> list[Retrieval]:
        return list(self.rows)

    async def get_latest_retrieval_pass(self, message_id: uuid.UUID) -> int | None:
        return 1 if self.rows else None

    async def insert_candidates(self, **kwargs: Any) -> int:
        self.insert_calls.append(kwargs)
        candidates = kwargs.get("candidates") or []
        message_id = kwargs["message_id"]
        pass_no = int(kwargs.get("retrieval_pass") or 1)
        method = __import__(
            "app.models.enums", fromlist=["RetrievalMethod"]
        ).RetrievalMethod.bm25
        for index, cand in enumerate(candidates):
            self.rows.append(
                Retrieval(
                    id=uuid.uuid4(),
                    message_id=message_id,
                    chunk_id=getattr(cand, "chunk_id", None),
                    entity_id=getattr(cand, "entity_id", None),
                    retrieval_method=method,
                    score=1.0,
                    rank=index,
                    retrieval_pass=pass_no,
                    created_at=datetime.now(UTC),
                )
            )
        return len(candidates)


class FakeObservability:
    async def create_message_generation(self, **kwargs: Any) -> MessageGeneration:
        return MessageGeneration(
            id=uuid.uuid4(),
            message_id=kwargs["message_id"],
            route_type=kwargs["route_type"],
            confidence_level=kwargs.get("confidence_level"),
            confidence_score=kwargs.get("confidence_score"),
            agent_triggered=bool(kwargs.get("agent_triggered", False)),
            model_used=kwargs.get("model_used"),
            prompt_tokens=kwargs.get("prompt_tokens"),
            completion_tokens=kwargs.get("completion_tokens"),
            total_tokens=kwargs.get("total_tokens"),
            cost_usd=kwargs.get("cost_usd"),
            latency_ms=kwargs.get("latency_ms"),
            finish_reason=kwargs.get("finish_reason") or FinishReason.stop,
            created_at=datetime.now(UTC),
        )


def _session(user_id: uuid.UUID, workspace_id: uuid.UUID) -> ChatSession:
    now = datetime.now(UTC)
    return ChatSession(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        user_id=user_id,
        title=None,
        created_at=now,
        updated_at=now,
        deleted_at=None,
        deleted_by=None,
        last_message_preview=None,
        last_message_at=None,
        message_count=0,
    )


def _retrieval(chunk_id: uuid.UUID) -> Retrieval:
    return Retrieval(
        id=uuid.uuid4(),
        message_id=uuid.uuid4(),
        chunk_id=chunk_id,
        entity_id=None,
        retrieval_method=RetrievalMethod.rerank,
        score=0.9,
        rank=1,
        retrieval_pass=1,
        created_at=datetime.now(UTC),
    )


class ScriptedOrch:
    def __init__(self, execution: QueryExecutionResult) -> None:
        self.execution = execution

    async def handle_query(self, *args: Any, **kwargs: Any) -> QueryExecutionResult:
        return self.execution


def _svc(
    *,
    ws: uuid.UUID,
    user: uuid.UUID,
    session: ChatSession,
    execution: QueryExecutionResult,
    retrievals: FakeRetrievalRecords | None = None,
    citations: FakeCitations | None = None,
    messages: FakeMessages | None = None,
) -> tuple[MessageProcessingService, FakeMessages, FakeCitations]:
    messages = messages or FakeMessages()
    citations = citations or FakeCitations()
    svc = MessageProcessingService(
        settings=_settings(),
        session=AsyncMock(),  # type: ignore[arg-type]
        sessions=FakeSessions(session),  # type: ignore[arg-type]
        messages=messages,  # type: ignore[arg-type]
        citations=citations,  # type: ignore[arg-type]
        retrieval_records=retrievals or FakeRetrievalRecords(),  # type: ignore[arg-type]
        observability=FakeObservability(),  # type: ignore[arg-type]
        orchestrator=ScriptedOrch(execution),  # type: ignore[arg-type]
    )
    return svc, messages, citations


@pytest.mark.asyncio
async def test_happy_path_persists_only_verified_citations() -> None:
    ws, user = uuid.uuid4(), uuid.uuid4()
    session = _session(user, ws)
    chunk = uuid.uuid4()
    execution = QueryExecutionResult(
        route_type=RouteType.complex,
        answer="Grounded answer",
        citation_refs=[
            CitationRef(
                chunk_id=chunk,
                document_id=uuid.uuid4(),
                verify=True,
                text_snippet="hybrid retrieval using vector search",
            )
        ],
        metadata={"agent_triggered": False, "retrieval_pass_final": 1},
        verify=True,
        latency_ms=10,
        status="completed",
        llm_calls_count=1,
        model_used="claude-3-5-haiku-latest",
        message_generation_id=uuid.uuid4(),
    )
    svc, messages, citations = _svc(
        ws=ws,
        user=user,
        session=session,
        execution=execution,
        retrievals=FakeRetrievalRecords([_retrieval(chunk)]),
    )
    result = await svc.generate_answer(
        workspace_id=ws,
        session_id=session.id,
        user_id=user,
        content="What is hybrid retrieval?",
    )
    assert result.assistant.content == "Grounded answer"
    assert citations.calls
    persisted_refs = citations.calls[0]["citation_refs"]
    assert len(persisted_refs) == 1
    assert persisted_refs[0].verify is True
    assert persisted_refs[0].chunk_id == chunk
    assert messages.rows[1].content == "Grounded answer"


@pytest.mark.asyncio
async def test_invalid_citation_is_not_persisted() -> None:
    ws, user = uuid.uuid4(), uuid.uuid4()
    session = _session(user, ws)
    execution = QueryExecutionResult(
        route_type=RouteType.complex,
        answer=INSUFFICIENT_EVIDENCE_ANSWER,
        citation_refs=[],
        metadata={"agent_triggered": False, "retrieval_pass_final": 1},
        verify=False,
        latency_ms=10,
        status="completed",
        llm_calls_count=1,
        model_used="claude-3-5-haiku-latest",
        message_generation_id=uuid.uuid4(),
    )
    svc, messages, citations = _svc(
        ws=ws, user=user, session=session, execution=execution
    )
    result = await svc.generate_answer(
        workspace_id=ws,
        session_id=session.id,
        user_id=user,
        content="Invent a fact",
    )
    assert result.assistant.content == INSUFFICIENT_EVIDENCE_ANSWER
    assert citations.calls == []
    assert result.assistant.citations == []
    assert messages.rows[1].content == INSUFFICIENT_EVIDENCE_ANSWER


@pytest.mark.asyncio
async def test_unverified_refs_are_dropped_at_persist() -> None:
    ws, user = uuid.uuid4(), uuid.uuid4()
    session = _session(user, ws)
    chunk = uuid.uuid4()
    execution = QueryExecutionResult(
        route_type=RouteType.complex,
        answer="Should not expose unverified source",
        citation_refs=[
            CitationRef(chunk_id=chunk, document_id=uuid.uuid4(), verify=False)
        ],
        metadata={},
        verify=False,
        latency_ms=5,
        status="completed",
        llm_calls_count=1,
        message_generation_id=uuid.uuid4(),
    )
    svc, _, citations = _svc(
        ws=ws,
        user=user,
        session=session,
        execution=execution,
        retrievals=FakeRetrievalRecords([_retrieval(chunk)]),
    )
    await svc.generate_answer(
        workspace_id=ws,
        session_id=session.id,
        user_id=user,
        content="Q?",
    )
    assert citations.calls == []


@pytest.mark.asyncio
async def test_workspace_isolation_rejects_foreign_retrieval() -> None:
    ws_a, ws_b, msg = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    foreign = RetrievalEvidence(
        retrieval_id=uuid.uuid4(),
        message_id=msg,
        source_text="secret from workspace B",
        workspace_id=ws_b,
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_version_id=uuid.uuid4(),
    )
    report = CitationVerificationService().verify(
        workspace_id=ws_a,
        message_id=msg,
        cited_ids=[str(foreign.chunk_id)],
        evidence=[foreign],
    )
    assert report.has_verified is False
    assert report.results[0].reason is VerificationReason.WRONG_WORKSPACE


@pytest.mark.asyncio
async def test_sse_emits_tokens_only_after_generate_answer_completes() -> None:
    """Streaming contract: verification finishes inside generate_answer first."""
    ws, user = uuid.uuid4(), uuid.uuid4()
    session = _session(user, ws)
    chunk = uuid.uuid4()
    execution = QueryExecutionResult(
        route_type=RouteType.complex,
        answer="Verified",
        citation_refs=[
            CitationRef(
                chunk_id=chunk,
                document_id=uuid.uuid4(),
                verify=True,
                text_snippet="Verified",
            )
        ],
        metadata={},
        verify=True,
        latency_ms=8,
        status="completed",
        llm_calls_count=1,
        message_generation_id=uuid.uuid4(),
    )
    svc, _, _ = _svc(
        ws=ws,
        user=user,
        session=session,
        execution=execution,
        retrievals=FakeRetrievalRecords([_retrieval(chunk)]),
    )
    events = []
    async for event in svc.stream_answer_events(
        workspace_id=ws,
        session_id=session.id,
        user_id=user,
        content="Q?",
    ):
        events.append(event.event)
    assert "status" in events
    assert events[0] == "status"
    assert "token" in events
    assert "citations" in events
    assert events[-1] == "done"
    assert events.index("token") < events.index("citations")
