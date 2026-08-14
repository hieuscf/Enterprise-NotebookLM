# =============================================================================
# File: message_service.py
# Module/Service: Chat Service
# Layer: Service
# Purpose: POST message processing — user insert → Query Router → persist answer.
# Responsibilities:
#   - generate_answer(): single business entry for JSON + SSE handlers
#   - 0-LLM routes: assistant + message_generations; complex: FR14 pipeline + LLM
#   - Session touch / last_message summary; persist verified citations only
# Dependencies:
#   - QueryOrchestrator, ChatSessionRepository, ChatMessageRepository,
#     CitationRepository, RetrievalRecordRepository, QueryObservabilityRepository
# Public Exports:
#   - MessageProcessingService, MessageProcessResult, ChatStreamEvent
# Database/Table: chat_messages, message_generations, citations, chat_sessions
# Related Modules: app.api.chat, Citation Verification Layer
# Important Notes:
#   - Does not alter Query Router / Confidence / Agent logic.
#   - SSE: status (retrieving/generating) immediately, then tokens after
#     verification; citations last. Never stream an unverified final answer.
#   - Commit before yielding tokens so live UI / remount refetch sees content.
#   - Deterministic verification. No LLM call.
#   - Must validate workspace/message/retrieval membership.
# =============================================================================

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.enums import ConfidenceLevel, FinishReason, MessageRole, RouteType
from app.repositories.chat_messages import ChatMessageRepository
from app.repositories.chat_sessions import ChatSessionRepository
from app.repositories.citations import CitationRepository
from app.repositories.query_logs import QueryObservabilityRepository
from app.repositories.retrieval_records import RetrievalRecordRepository
from app.schemas.chat import (
    ChatMessageResponse,
    MessageGenerationResponse,
)
from app.services.chat.session_service import ChatServiceError
from app.services.query_router.orchestrator import QueryOrchestrator
from app.services.query_router.schemas import CitationRef, QueryExecutionResult

logger = get_logger(__name__)

# Never leave the pre-created assistant row with empty content — an unhandled
# pipeline failure must not turn into a permanent "no content" ghost bubble
# on every future reload of the chat history.
PIPELINE_FAILURE_TEXT = (
    "Xin lỗi, đã xảy ra lỗi khi tạo câu trả lời. Vui lòng thử lại."
)


@dataclass(slots=True)
class MessageProcessResult:
    """Full outcome of generate_answer (JSON response body source)."""

    user_message_id: UUID
    assistant: ChatMessageResponse
    route_type: RouteType
    llm_calls_count: int
    retrieval_pass_final: int | None = None
    agent_triggered: bool = False


@dataclass(slots=True)
class ChatStreamEvent:
    """One SSE payload unit."""

    event: Literal["status", "token", "citations", "generation", "done", "error"]
    data: dict[str, Any] = field(default_factory=dict)


class MessageProcessingService:
    """Orchestrate Conversation Memory + Query Router for POST .../messages."""

    def __init__(
        self,
        *,
        settings: Settings,
        session: AsyncSession,
        sessions: ChatSessionRepository,
        messages: ChatMessageRepository,
        citations: CitationRepository,
        retrieval_records: RetrievalRecordRepository,
        observability: QueryObservabilityRepository,
        orchestrator: QueryOrchestrator,
    ) -> None:
        self._settings = settings
        self._session = session
        self._sessions = sessions
        self._messages = messages
        self._citations = citations
        self._retrieval_records = retrieval_records
        self._observability = observability
        self._orchestrator = orchestrator

    async def generate_answer(
        self,
        *,
        workspace_id: UUID,
        session_id: UUID,
        user_id: UUID,
        content: str,
    ) -> MessageProcessResult:
        """Core business flow shared by JSON and SSE handlers."""
        question = (content or "").strip()
        if not question:
            raise ChatServiceError(
                "validation_error",
                "Message content must not be empty",
                status_code=422,
            )

        session = await self._sessions.get(
            session_id=session_id,
            workspace_id=workspace_id,
            include_deleted=False,
        )
        if session is None or session.user_id != user_id:
            raise ChatServiceError(
                "not_found",
                "Chat session not found in this workspace",
                status_code=404,
            )

        # 1) INSERT user message first — pipeline keys off this message_id.
        user_msg = await self._messages.create(
            session_id=session_id,
            role=MessageRole.user,
            content=question,
        )

        # 2) Pre-create assistant row so message_generations FK can attach (complex).
        assistant_msg = await self._messages.create(
            session_id=session_id,
            role=MessageRole.assistant,
            content="",
        )

        history = await self._load_history(session_id=session_id, exclude_ids={assistant_msg.id})

        # 3) Query Router (+ FR14 complex / Prompt Construction when wired).
        try:
            execution = await self._orchestrator.handle_query(
                workspace_id,
                user_id,
                question,
                message_id=user_msg.id,
                session_id=session_id,
                assistant_message_id=assistant_msg.id,
                chat_history=history,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "chat_handle_query_failed",
                session_id=str(session_id),
                error=type(exc).__name__,
                detail=str(exc),
            )
            await self._fail_assistant_message(assistant_msg.id)
            raise ChatServiceError(
                "pipeline_error",
                "Failed to process chat message",
                status_code=500,
            ) from exc

        answer_text = (execution.answer or "").strip() or (
            "I could not produce an answer from the available documents."
        )
        await self._messages.update_content(assistant_msg.id, answer_text)

        citation_rows = await self._persist_citations(
            user_message_id=user_msg.id,
            assistant_message_id=assistant_msg.id,
            citation_refs=execution.citation_refs,
        )
        # Re-load with chunk/location joins — Citation ORM rows alone lack locator.
        enriched_citations = await self._messages.list_citations_for_message(
            assistant_msg.id
        )
        if not enriched_citations and citation_rows:
            # Fallback when joins miss (should be rare): keep document_id from refs.
            from app.repositories.chat_messages import CitationWithDocument

            enriched_citations = [
                CitationWithDocument(
                    citation=c,
                    document_id=_doc_id_from_ref(execution.citation_refs, idx),
                    chunk_id=(
                        execution.citation_refs[idx].chunk_id
                        if 0 <= idx < len(execution.citation_refs)
                        else None
                    ),
                    page_number=(
                        execution.citation_refs[idx].page_number
                        if 0 <= idx < len(execution.citation_refs)
                        else None
                    ),
                )
                for idx, c in enumerate(citation_rows)
            ]

        generation = await self._ensure_generation(
            assistant_message_id=assistant_msg.id,
            execution=execution,
        )

        count = await self._messages.count(session_id=session_id)
        await self._sessions.touch_after_message(
            session_id=session_id,
            preview=answer_text,
            message_at=datetime.now(UTC),
            message_count=count,
        )

        from app.adapters.minio_storage import get_minio_storage
        from app.services.chat.session_service import _citation_response
        from app.services.documents import DocumentIngestionService

        locator_map = {}
        try:
            docs = DocumentIngestionService(self._session, get_minio_storage())
            locator_map = await docs.resolve_locators_for_citations(
                workspace_id,
                enriched_citations,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("citation_locator_enrich_failed", error=str(exc))

        assistant_resp = ChatMessageResponse(
            id=assistant_msg.id,
            session_id=session_id,
            role="assistant",
            content=answer_text,
            generation=_generation_response(generation, execution),
            citations=[
                _citation_response(row, locator=locator_map.get(row.citation.id))
                for row in enriched_citations
            ],
            created_at=assistant_msg.created_at,
        )

        agent_triggered = bool((execution.metadata or {}).get("agent_triggered"))
        retrieval_pass = (execution.metadata or {}).get("retrieval_pass_final")
        return MessageProcessResult(
            user_message_id=user_msg.id,
            assistant=assistant_resp,
            route_type=execution.route_type,
            llm_calls_count=int(execution.llm_calls_count),
            retrieval_pass_final=int(retrieval_pass) if retrieval_pass is not None else None,
            agent_triggered=agent_triggered,
        )

    async def stream_answer_events(
        self,
        *,
        workspace_id: UUID,
        session_id: UUID,
        user_id: UUID,
        content: str,
    ) -> AsyncIterator[ChatStreamEvent]:
        """SSE adapter — status first, then tokens after verification."""
        # Flush progress before the (slow) retrieve + LLM + verify path so
        # the client is not stuck on a blank bubble until the first token.
        yield ChatStreamEvent(event="status", data={"stage": "retrieving"})
        yield ChatStreamEvent(event="status", data={"stage": "generating"})
        try:
            result = await self.generate_answer(
                workspace_id=workspace_id,
                session_id=session_id,
                user_id=user_id,
                content=content,
            )
            # Persist before tokens so a client remount/refetch cannot load
            # the empty placeholder row.
            await self._session.commit()
        except ChatServiceError as exc:
            yield ChatStreamEvent(
                event="error",
                data={"code": exc.code, "message": exc.message, "status_code": exc.status_code},
            )
            return

        chunk = max(1, int(self._settings.chat_sse_token_chunk_chars))
        text = result.assistant.content
        for i in range(0, len(text), chunk):
            yield ChatStreamEvent(event="token", data={"text": text[i : i + chunk]})

        yield ChatStreamEvent(
            event="citations",
            data={
                "citations": [
                    c.model_dump(mode="json") for c in result.assistant.citations
                ]
            },
        )
        yield ChatStreamEvent(
            event="generation",
            data={
                "generation": (
                    result.assistant.generation.model_dump(mode="json")
                    if result.assistant.generation
                    else None
                ),
                "message": result.assistant.model_dump(mode="json"),
            },
        )
        yield ChatStreamEvent(event="done", data={})

    async def _fail_assistant_message(self, assistant_message_id: UUID) -> None:
        """Best-effort: replace the empty placeholder with a visible error text
        and commit immediately so it survives the request's rollback-on-error
        (``get_db_session`` rolls back the whole transaction when the caller
        re-raises). Never let this secondary failure mask the original error.
        """
        try:
            await self._messages.update_content(assistant_message_id, PIPELINE_FAILURE_TEXT)
            await self._session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("chat_fail_assistant_message_failed", error=str(exc))

    async def _load_history(
        self,
        *,
        session_id: UUID,
        exclude_ids: set[UUID],
    ) -> list[dict[str, str]]:
        rows = await self._messages.list(session_id=session_id, page=1, page_size=50)
        out: list[dict[str, str]] = []
        for row in rows:
            if row.message.id in exclude_ids:
                continue
            if not row.message.content:
                continue
            role = (
                row.message.role.value
                if hasattr(row.message.role, "value")
                else str(row.message.role)
            )
            out.append({"role": role, "content": row.message.content})
        return out

    async def _persist_citations(
        self,
        *,
        user_message_id: UUID,
        assistant_message_id: UUID,
        citation_refs: list[CitationRef],
    ) -> list[Any]:
        if not citation_refs:
            return []
        # Latest pass only — never merge pass1 + pass2.
        latest_rows = await self._retrieval_records.list_for_latest_pass(user_message_id)
        snippet_by_chunk: dict[UUID, str] = {}
        for ref in citation_refs:
            if ref.verify and ref.chunk_id is not None and (ref.text_snippet or "").strip():
                snippet_by_chunk[ref.chunk_id] = (ref.text_snippet or "").strip()
        verified_refs = [ref for ref in citation_refs if ref.verify]
        if not verified_refs:
            return []
        return await self._citations.insert_mapped(
            message_id=assistant_message_id,
            citation_refs=verified_refs,
            latest_pass_rows=latest_rows,
            snippet_by_chunk_id=snippet_by_chunk,
        )

    async def _ensure_generation(
        self,
        *,
        assistant_message_id: UUID,
        execution: QueryExecutionResult,
    ) -> Any | None:
        """Write message_generations for 0-LLM routes; complex already wrote one."""
        if execution.message_generation_id is not None:
            # Complex / SQL path already persisted metrics.
            return _SyntheticGeneration(execution)

        route = execution.route_type
        if route is RouteType.complex and execution.status not in {
            None,
            "completed",
            "sql_agent_direct",
        }:
            # pending_llm without generator — still record a stub generation.
            pass

        conf_level = (execution.metadata or {}).get("confidence_level")
        conf_score = (execution.metadata or {}).get("confidence_score")
        agent_triggered = bool((execution.metadata or {}).get("agent_triggered", False))

        # 0-LLM convention: confidence NULL, tokens/cost 0/NULL.
        is_zero_llm = route in {
            RouteType.cache_hit,
            RouteType.metadata,
            RouteType.factoid,
        }
        conf_enum: ConfidenceLevel | None = None
        if not is_zero_llm and conf_level in {"high", "low"}:
            conf_enum = ConfidenceLevel(conf_level)
        elif not is_zero_llm and isinstance(conf_level, ConfidenceLevel):
            conf_enum = conf_level

        try:
            row = await self._observability.create_message_generation(
                message_id=assistant_message_id,
                route_type=route,
                model_used=None if is_zero_llm else execution.model_used,
                prompt_tokens=0 if is_zero_llm else None,
                completion_tokens=0 if is_zero_llm else None,
                total_tokens=0 if is_zero_llm else None,
                cost_usd=Decimal("0") if is_zero_llm else None,
                latency_ms=int(execution.latency_ms),
                confidence_level=None if is_zero_llm else conf_enum,
                confidence_score=None if is_zero_llm else conf_score,
                agent_triggered=False if is_zero_llm else agent_triggered,
                temperature=None,
                top_p=None,
                finish_reason=FinishReason.stop if execution.answer else None,
            )
            return row
        except Exception as exc:  # noqa: BLE001
            logger.warning("chat_persist_generation_failed", error=str(exc))
            return _SyntheticGeneration(execution)


@dataclass(slots=True)
class _SyntheticGeneration:
    """Fallback view when generation was written inside ComplexQueryPipeline."""

    execution: QueryExecutionResult

    @property
    def route_type(self) -> RouteType:
        return self.execution.route_type

    @property
    def confidence_level(self) -> Any:
        raw = (self.execution.metadata or {}).get("confidence_level")
        return raw

    @property
    def confidence_score(self) -> float | None:
        raw = (self.execution.metadata or {}).get("confidence_score")
        return float(raw) if raw is not None else None

    @property
    def agent_triggered(self) -> bool:
        return bool((self.execution.metadata or {}).get("agent_triggered", False))

    @property
    def model_used(self) -> str | None:
        return self.execution.model_used

    @property
    def prompt_tokens(self) -> int | None:
        return None

    @property
    def completion_tokens(self) -> int | None:
        return None

    @property
    def total_tokens(self) -> int | None:
        return None

    @property
    def cost_usd(self) -> Decimal | None:
        return None

    @property
    def latency_ms(self) -> int | None:
        return int(self.execution.latency_ms)

    @property
    def finish_reason(self) -> FinishReason | None:
        return FinishReason.stop if self.execution.answer else None


def _generation_response(
    generation: Any | None,
    execution: QueryExecutionResult,
) -> MessageGenerationResponse | None:
    if generation is None:
        return MessageGenerationResponse(
            route_type=execution.route_type.value,  # type: ignore[arg-type]
            confidence_level=None,
            confidence_score=None,
            agent_triggered=False,
            model_used=execution.model_used,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            cost_usd=0.0,
            latency_ms=execution.latency_ms,
            finish_reason=None,
        )

    route = generation.route_type
    route_val = route.value if hasattr(route, "value") else str(route)
    conf = getattr(generation, "confidence_level", None)
    conf_val = conf.value if conf is not None and hasattr(conf, "value") else conf
    if isinstance(conf_val, str) and conf_val not in {"high", "low"}:
        conf_val = None
    finish = getattr(generation, "finish_reason", None)
    finish_val = finish.value if finish is not None and hasattr(finish, "value") else finish
    cost = getattr(generation, "cost_usd", None)
    return MessageGenerationResponse(
        route_type=route_val,  # type: ignore[arg-type]
        confidence_level=conf_val,  # type: ignore[arg-type]
        confidence_score=getattr(generation, "confidence_score", None),
        agent_triggered=bool(getattr(generation, "agent_triggered", False)),
        model_used=getattr(generation, "model_used", None),
        prompt_tokens=getattr(generation, "prompt_tokens", None),
        completion_tokens=getattr(generation, "completion_tokens", None),
        total_tokens=getattr(generation, "total_tokens", None),
        cost_usd=float(cost) if cost is not None else None,
        latency_ms=getattr(generation, "latency_ms", None),
        finish_reason=finish_val,  # type: ignore[arg-type]
    )


def _doc_id_from_ref(refs: list[CitationRef], index: int) -> UUID | None:
    if 0 <= index < len(refs):
        return refs[index].document_id
    return None


def format_sse(event: ChatStreamEvent) -> str:
    """Encode one SSE frame."""
    payload = json.dumps({"type": event.event, **event.data}, default=str)
    return f"event: {event.event}\ndata: {payload}\n\n"
