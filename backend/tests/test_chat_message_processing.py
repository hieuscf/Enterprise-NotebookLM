# =============================================================================
# File: test_chat_message_processing.py
# Module/Service: Chat Service — Phase 2.4 Part 2
# Layer: Service / Presentation
# Purpose: Unit tests for POST messages — Prompt Construction, tiering, SSE/JSON.
# Responsibilities:
#   - Case1 HIGH: no agent, pass=1, 1 LLM, light model
#   - Case2 LOW rewrite + pass=2: agent_triggered, prompt uses pass2 only, strong model
#   - Case3 Accept application/json
#   - Case4 SSE tokens then citations last
# Dependencies:
#   - pytest, httpx, MessageProcessingService fakes
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: message_service, answer_generator, model_tiering, prompt_builder
# Important Notes: Does not hit live Anthropic / Postgres.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.chat import get_message_processing_service
from app.core.config import Settings
from app.core.rate_limit import InMemoryWorkspaceRateLimiter, get_workspace_rate_limiter
from app.db.session import get_db_session
from app.dependencies.auth import CurrentUser, get_current_user
from app.main import app
from app.models.chat import ChatMessage, ChatSession, MessageGeneration
from app.models.enums import (
    ConfidenceLevel,
    FinishReason,
    MessageRole,
    RoleName,
    RouteType,
)
from app.models.retrieval import Retrieval
from app.repositories.workspace_members import WorkspaceMemberRepository
from app.schemas.chat import ChatMessageResponse, MessageGenerationResponse
from app.services.chat.answer_generator import PromptAnswerGenerator
from app.services.chat.complex_query_pipeline import AnswerGenerationResult
from app.services.chat.message_service import MessageProcessingService, format_sse
from app.services.chat.model_tiering import select_answer_model
from app.services.chat.prompt_builder import (
    PromptRetrievalItem,
    build_prompt,
    retrieval_candidates_to_prompt_items,
)
from app.services.query_router.schemas import CitationRef, QueryExecutionResult
from app.services.retrieval.confidence_engine import ConfidenceResult
from app.services.retrieval.schemas import RetrievalCandidate, RetrievalResult


def _settings(**overrides: Any) -> Settings:
    base = {
        # Pin provider explicitly — Settings() also reads the local dev .env
        # (env_file=(".env", "../.env")); without this, a machine with
        # CHAT_LLM_PROVIDER=openai in .env silently breaks these
        # anthropic-tiering assertions below.
        "chat_llm_provider": "anthropic",
        "anthropic_api_key": "test-key",
        "chat_answer_light_model": "claude-3-5-haiku-latest",
        "chat_answer_strong_model": "claude-sonnet-mock",
        "chat_agent_force_strong_model": True,
        "chat_sse_token_chunk_chars": 5,
    }
    base.update(overrides)
    return Settings(**base)


# ---------------------------------------------------------------------------
# Prompt / tiering unit tests
# ---------------------------------------------------------------------------


def test_build_prompt_only_lists_provided_retrieval_items() -> None:
    items = [
        PromptRetrievalItem(
            citation_id=str(uuid.uuid4()),
            text_snippet="pass2 only",
            rank=1,
        )
    ]
    built = build_prompt("SYS", [{"role": "user", "content": "hi"}], items, "Q?")
    assert "pass2 only" in built.user
    assert "pass1" not in built.user
    assert "citation_ids" in built.user


def test_select_answer_model_agent_force_strong() -> None:
    settings = _settings(chat_agent_force_strong_model=True)
    assert (
        select_answer_model(settings, agent_triggered=False)
        == "claude-3-5-haiku-latest"
    )
    assert (
        select_answer_model(settings, agent_triggered=True) == "claude-sonnet-mock"
    )


def test_select_answer_model_openai_provider() -> None:
    settings = _settings(
        chat_llm_provider="openai",
        openai_api_key="sk-test",
        openai_chat_model="gpt-5",
        openai_chat_strong_model="gpt-5",
        chat_agent_force_strong_model=True,
    )
    assert select_answer_model(settings, agent_triggered=False) == "gpt-5"
    assert select_answer_model(settings, agent_triggered=True) == "gpt-5"


@pytest.mark.asyncio
async def test_answer_generator_maps_citation_ids_and_counts_one_llm() -> None:
    chunk_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    cand = RetrievalCandidate(
        workspace_id=uuid.uuid4(),
        text_snippet="ctx",
        retrieval_method="rerank",
        raw_score=0.9,
        document_id=doc_id,
        chunk_id=chunk_id,
        score=0.9,
        rank=1,
    )
    retrieval = RetrievalResult(items=[cand], latency_ms=1, sources_used=["vector"])

    async def fake_llm(**kwargs: Any) -> Any:
        assert kwargs["model"] == "claude-sonnet-mock"
        return type(
            "R",
            (),
            {
                "data": {
                    "answer": "Final",
                    "citation_ids": [str(chunk_id), str(uuid.uuid4())],
                },
                "model": kwargs["model"],
                "input_tokens": 11,
                "output_tokens": 7,
                "estimated_cost_usd": 0.01,
            },
        )()

    gen = PromptAnswerGenerator(_settings(), llm_call=fake_llm)
    conf = ConfidenceResult(
        confidence_score=0.4,
        confidence_level=ConfidenceLevel.low,
        top_score=0.4,
        score_spread=0.1,
        above_threshold_count=0,
    )
    result = await gen.generate(
        workspace_id=uuid.uuid4(),
        query_text="rewritten?",
        retrieval_result=retrieval,
        confidence=conf,
        agent_triggered=True,
    )
    assert result.answer == "Final"
    assert result.model_used == "claude-sonnet-mock"
    assert len(result.citation_refs) == 1
    assert result.citation_refs[0].chunk_id == chunk_id


# ---------------------------------------------------------------------------
# MessageProcessingService fakes
# ---------------------------------------------------------------------------


class FakeSessions:
    def __init__(self, session: ChatSession) -> None:
        self.session = session
        self.touches: list[dict[str, Any]] = []

    async def get(self, **kwargs: Any) -> ChatSession | None:
        if kwargs.get("session_id") != self.session.id:
            return None
        if kwargs.get("workspace_id") != self.session.workspace_id:
            return None
        if self.session.deleted_at is not None:
            return None
        return self.session

    async def touch_after_message(self, **kwargs: Any) -> bool:
        self.touches.append(kwargs)
        return True


class FakeMessages:
    def __init__(self) -> None:
        self.rows: list[ChatMessage] = []

    async def create(self, *, session_id: uuid.UUID, role: MessageRole, content: str) -> ChatMessage:
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
    def __init__(self) -> None:
        self.latest_calls: list[uuid.UUID] = []
        self.pass2_rows: list[Retrieval] = []
        self.insert_calls: list[dict[str, Any]] = []

    async def list_for_latest_pass(self, message_id: uuid.UUID) -> list[Retrieval]:
        self.latest_calls.append(message_id)
        return list(self.pass2_rows)

    async def get_latest_retrieval_pass(self, message_id: uuid.UUID) -> int | None:
        return 2 if self.pass2_rows else (1 if self.insert_calls else None)

    async def insert_candidates(self, **kwargs: Any) -> int:
        self.insert_calls.append(kwargs)
        candidates = kwargs.get("candidates") or []
        message_id = kwargs["message_id"]
        pass_no = int(kwargs.get("retrieval_pass") or 1)
        method = __import__(
            "app.models.enums", fromlist=["RetrievalMethod"]
        ).RetrievalMethod.bm25
        rows: list[Retrieval] = []
        for index, cand in enumerate(candidates):
            rows.append(
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
        if not self.pass2_rows:
            self.pass2_rows = rows
        return len(rows)


class FakeObservability:
    def __init__(self) -> None:
        self.generations: list[dict[str, Any]] = []

    async def create_message_generation(self, **kwargs: Any) -> MessageGeneration:
        row = MessageGeneration(
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
            finish_reason=kwargs.get("finish_reason"),
            created_at=datetime.now(UTC),
        )
        self.generations.append(kwargs)
        return row


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


@pytest.mark.asyncio
async def test_case1_high_confidence_json_path() -> None:
    ws, user = uuid.uuid4(), uuid.uuid4()
    session = _session(user, ws)
    sessions = FakeSessions(session)
    messages = FakeMessages()
    obs = FakeObservability()
    retrievals = FakeRetrievalRecords()

    class Orch:
        async def handle_query(self, *args: Any, **kwargs: Any) -> QueryExecutionResult:
            assert kwargs["message_id"] is not None
            assert kwargs["assistant_message_id"] is not None
            return QueryExecutionResult(
                route_type=RouteType.complex,
                answer="High conf answer",
                citation_refs=[],
                metadata={
                    "agent_triggered": False,
                    "retrieval_pass_final": 1,
                    "confidence_level": "high",
                    "confidence_score": 0.91,
                },
                verify=True,
                latency_ms=40,
                status="completed",
                llm_calls_count=1,
                model_used="claude-3-5-haiku-latest",
                message_generation_id=uuid.uuid4(),
            )

    svc = MessageProcessingService(
        settings=_settings(),
        session=AsyncMock(),  # type: ignore[arg-type]
        sessions=sessions,  # type: ignore[arg-type]
        messages=messages,  # type: ignore[arg-type]
        citations=FakeCitations(),  # type: ignore[arg-type]
        retrieval_records=retrievals,  # type: ignore[arg-type]
        observability=obs,  # type: ignore[arg-type]
        orchestrator=Orch(),  # type: ignore[arg-type]
    )
    result = await svc.generate_answer(
        workspace_id=ws,
        session_id=session.id,
        user_id=user,
        content="Explain the policy",
    )
    assert result.route_type is RouteType.complex
    assert result.agent_triggered is False
    assert result.retrieval_pass_final == 1
    assert result.llm_calls_count == 1
    assert result.assistant.generation is not None
    assert result.assistant.generation.agent_triggered is False
    assert result.assistant.generation.model_used == "claude-3-5-haiku-latest"
    assert messages.rows[0].role is MessageRole.user
    assert messages.rows[1].content == "High conf answer"
    assert sessions.touches


@pytest.mark.asyncio
async def test_pipeline_failure_never_leaves_empty_assistant_content() -> None:
    """A crashing/timing-out handle_query must not leave a permanent empty
    assistant row — reloading chat history should show an error text, never
    the frontend's "Không có nội dung trả lời." ghost bubble."""
    from app.services.chat.session_service import ChatServiceError

    ws, user = uuid.uuid4(), uuid.uuid4()
    session = _session(user, ws)
    sessions = FakeSessions(session)
    messages = FakeMessages()
    commit_calls = 0

    class FakeSession:
        async def commit(self) -> None:
            nonlocal commit_calls
            commit_calls += 1

    class FailingOrch:
        async def handle_query(self, *args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("pipeline timed out")

    svc = MessageProcessingService(
        settings=_settings(),
        session=FakeSession(),  # type: ignore[arg-type]
        sessions=sessions,  # type: ignore[arg-type]
        messages=messages,  # type: ignore[arg-type]
        citations=FakeCitations(),  # type: ignore[arg-type]
        retrieval_records=FakeRetrievalRecords(),  # type: ignore[arg-type]
        observability=FakeObservability(),  # type: ignore[arg-type]
        orchestrator=FailingOrch(),  # type: ignore[arg-type]
    )

    with pytest.raises(ChatServiceError):
        await svc.generate_answer(
            workspace_id=ws,
            session_id=session.id,
            user_id=user,
            content="Explain the policy",
        )

    assistant_row = messages.rows[1]
    assert assistant_row.role is MessageRole.assistant
    assert assistant_row.content.strip() != ""
    assert commit_calls == 1


@pytest.mark.asyncio
async def test_case2_low_confidence_uses_latest_pass_only() -> None:
    ws, user = uuid.uuid4(), uuid.uuid4()
    session = _session(user, ws)
    messages = FakeMessages()
    retrievals = FakeRetrievalRecords()
    chunk_pass2 = uuid.uuid4()
    retrievals.pass2_rows = [
        Retrieval(
            id=uuid.uuid4(),
            message_id=uuid.uuid4(),
            chunk_id=chunk_pass2,
            entity_id=None,
            retrieval_method=__import__("app.models.enums", fromlist=["RetrievalMethod"]).RetrievalMethod.rerank,
            score=0.8,
            rank=1,
            retrieval_pass=2,
            created_at=datetime.now(UTC),
        )
    ]
    citations = FakeCitations()

    class Orch:
        async def handle_query(self, *args: Any, **kwargs: Any) -> QueryExecutionResult:
            return QueryExecutionResult(
                route_type=RouteType.complex,
                answer="After rewrite",
                citation_refs=[
                    CitationRef(chunk_id=chunk_pass2, document_id=uuid.uuid4(), verify=True)
                ],
                metadata={
                    "agent_triggered": True,
                    "retrieval_pass_final": 2,
                    "confidence_level": "high",
                    "confidence_score": 0.88,
                },
                verify=True,
                latency_ms=90,
                status="completed",
                llm_calls_count=2,
                model_used="claude-sonnet-mock",
                message_generation_id=uuid.uuid4(),
            )

    svc = MessageProcessingService(
        settings=_settings(),
        session=AsyncMock(),  # type: ignore[arg-type]
        sessions=FakeSessions(session),  # type: ignore[arg-type]
        messages=messages,  # type: ignore[arg-type]
        citations=citations,  # type: ignore[arg-type]
        retrieval_records=retrievals,  # type: ignore[arg-type]
        observability=FakeObservability(),  # type: ignore[arg-type]
        orchestrator=Orch(),  # type: ignore[arg-type]
    )
    result = await svc.generate_answer(
        workspace_id=ws,
        session_id=session.id,
        user_id=user,
        content="ambiguous?",
    )
    assert result.agent_triggered is True
    assert result.retrieval_pass_final == 2
    assert result.llm_calls_count == 2
    assert retrievals.latest_calls  # used get_latest / list_for_latest_pass
    assert citations.calls
    rows = citations.calls[0]["latest_pass_rows"]
    assert len(rows) == 1
    assert all(r.retrieval_pass == 2 for r in rows)
    assert rows[0].chunk_id == chunk_pass2


@pytest.mark.asyncio
async def test_case3_and_4_api_json_and_sse(monkeypatch: pytest.MonkeyPatch) -> None:
    ws, user, session_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    class FakeMsgService:
        async def generate_answer(self, **kwargs: Any) -> Any:
            now = datetime.now(UTC)
            assistant = ChatMessageResponse(
                id=uuid.uuid4(),
                session_id=session_id,
                role="assistant",
                content="HelloWorld",
                generation=MessageGenerationResponse(
                    route_type="complex",
                    confidence_level="high",
                    confidence_score=0.9,
                    agent_triggered=False,
                    model_used="claude-3-5-haiku-latest",
                    prompt_tokens=1,
                    completion_tokens=2,
                    total_tokens=3,
                    cost_usd=0.0,
                    latency_ms=10,
                    finish_reason="stop",
                ),
                citations=[],
                created_at=now,
            )
            from app.services.chat.message_service import MessageProcessResult

            return MessageProcessResult(
                user_message_id=uuid.uuid4(),
                assistant=assistant,
                route_type=RouteType.complex,
                llm_calls_count=1,
                retrieval_pass_final=1,
                agent_triggered=False,
            )

        async def stream_answer_events(self, **kwargs: Any):
            # Reuse real chunking via MessageProcessingService.stream after generate
            real = MessageProcessingService(
                settings=_settings(chat_sse_token_chunk_chars=5),
                session=AsyncMock(),
                sessions=AsyncMock(),
                messages=AsyncMock(),
                citations=AsyncMock(),
                retrieval_records=AsyncMock(),
                observability=AsyncMock(),
                orchestrator=AsyncMock(),
            )
            # Monkeypatch generate_answer on this instance
            real.generate_answer = self.generate_answer  # type: ignore[method-assign]
            async for event in real.stream_answer_events(**kwargs):
                yield event

    async def _user() -> CurrentUser:
        return CurrentUser(id=user, email="u@ex.com", full_name="U")

    async def _db():
        yield object()

    async def _role(self: Any, *, user_id: uuid.UUID, workspace_id: uuid.UUID) -> RoleName | None:
        return RoleName.editor

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[get_message_processing_service] = lambda: FakeMsgService()
    app.dependency_overrides[get_workspace_rate_limiter] = (
        lambda: InMemoryWorkspaceRateLimiter()
    )
    monkeypatch.setattr(WorkspaceMemberRepository, "get_role_for_user", _role)

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            json_resp = await client.post(
                f"/workspaces/{ws}/chat/sessions/{session_id}/messages",
                json={"content": "Hi"},
                headers={"Accept": "application/json"},
            )
            assert json_resp.status_code == 200
            body = json_resp.json()
            assert body["role"] == "assistant"
            assert body["content"] == "HelloWorld"
            assert body["generation"]["route_type"] == "complex"

            sse_resp = await client.post(
                f"/workspaces/{ws}/chat/sessions/{session_id}/messages",
                json={"content": "Hi"},
                headers={"Accept": "text/event-stream"},
            )
            assert sse_resp.status_code == 200
            assert "text/event-stream" in sse_resp.headers["content-type"]
            text = sse_resp.text
            assert "event: status" in text
            assert "event: token" in text
            assert "event: citations" in text
            assert "event: done" in text
            # citations appear after tokens; status may precede tokens
            assert text.index("event: status") < text.index("event: token")
            assert text.index("event: token") < text.index("event: citations")
            assert text.index("event: citations") < text.index("event: done")
    finally:
        app.dependency_overrides.clear()


def test_format_sse_shape() -> None:
    from app.services.chat.message_service import ChatStreamEvent

    frame = format_sse(ChatStreamEvent(event="token", data={"text": "ab"}))
    assert frame.startswith("event: token\n")
    assert '"text": "ab"' in frame
    status = format_sse(ChatStreamEvent(event="status", data={"stage": "retrieving"}))
    assert status.startswith("event: status\n")
    assert '"stage": "retrieving"' in status


@pytest.mark.asyncio
async def test_extractive_citations_write_retrievals_when_pass_empty() -> None:
    ws, user = uuid.uuid4(), uuid.uuid4()
    session = _session(user, ws)
    chunk = uuid.uuid4()
    doc = uuid.uuid4()
    retrievals = FakeRetrievalRecords()
    citations = FakeCitations()

    class Orch:
        async def handle_query(self, *args: Any, **kwargs: Any) -> QueryExecutionResult:
            return QueryExecutionResult(
                route_type=RouteType.section_extraction,
                answer="3.3 Hàng tồn kho\nCông ty áp dụng phương pháp kê khai thường xuyên.",
                citation_refs=[
                    CitationRef(
                        chunk_id=chunk,
                        document_id=doc,
                        page_number=None,
                        verify=True,
                        text_snippet="Hàng tồn kho",
                        document_version_id=uuid.uuid4(),
                        workspace_id=ws,
                    )
                ],
                metadata={"llm_calls_count": 0, "answer_type": "extractive"},
                verify=True,
                latency_ms=8,
                status="completed",
                llm_calls_count=0,
            )

    svc = MessageProcessingService(
        settings=_settings(),
        session=AsyncMock(),  # type: ignore[arg-type]
        sessions=FakeSessions(session),  # type: ignore[arg-type]
        messages=FakeMessages(),  # type: ignore[arg-type]
        citations=citations,  # type: ignore[arg-type]
        retrieval_records=retrievals,  # type: ignore[arg-type]
        observability=FakeObservability(),  # type: ignore[arg-type]
        orchestrator=Orch(),  # type: ignore[arg-type]
    )
    result = await svc.generate_answer(
        workspace_id=ws,
        session_id=session.id,
        user_id=user,
        content="3.3 Hàng tồn kho",
    )
    assert result.route_type == RouteType.section_extraction
    assert result.llm_calls_count == 0
    assert retrievals.insert_calls
    assert retrievals.insert_calls[0]["retrieval_pass"] == 1
    assert citations.calls
    latest = citations.calls[0]["latest_pass_rows"]
    assert latest
    assert latest[0].chunk_id == chunk
