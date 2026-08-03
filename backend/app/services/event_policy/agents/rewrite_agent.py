# =============================================================================
# File: rewrite_agent.py
# Module/Service: Rewrite Agent (FR14)
# Layer: Service
# Purpose: Haiku-tier rewrite of ambiguous queries without changing intent.
# Responsibilities:
#   - Call Anthropic structured JSON with rewrite-only system prompt
#   - Return rewritten_query + AgentEventData (cost/latency/payloads)
# Dependencies:
#   - anthropic_client.extract_structured_json, Settings, AgentEventData
# Public Exports:
#   - RewriteAgent, RewriteAgentResult
# Database/Table: N/A (Part 4 persists AgentEventData → agent_events)
# Related Modules: event_policy_engine, HybridRetrievalService (Second Retrieval)
# Important Notes: Model from Settings (tiering). On LLM failure → original_query.
# =============================================================================

from __future__ import annotations

import time
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from app.adapters.anthropic_client import extract_structured_json
from app.core.config import Settings
from app.core.logging import get_logger
from app.models.enums import AgentTriggerReason, AgentType
from app.services.event_policy.models import AgentEventData, ChatTurn
from pydantic import BaseModel, ConfigDict

logger = get_logger(__name__)

_REWRITE_SYSTEM = (
    "You rewrite user questions for document retrieval.\n"
    "Rules:\n"
    "- Preserve the original intent exactly.\n"
    "- Do NOT answer the question.\n"
    "- Do NOT add facts, assumptions, or new entities.\n"
    "- Do NOT change language unless required for clarity.\n"
    "- Resolve underspecified pronouns using chat history when present.\n"
    "- Output JSON only: {\"rewritten_query\": \"...\"}."
)


class RewriteAgentResult(BaseModel):
    """Rewrite Agent output for orchestrator / Second Retrieval."""

    model_config = ConfigDict(frozen=True)

    rewritten_query: str
    event: AgentEventData


class RewriteAgent:
    """Light-model rewrite agent (Dependency-injected Settings + optional LLM hook)."""

    def __init__(
        self,
        settings: Settings,
        *,
        llm_call: Any | None = None,
    ) -> None:
        self._settings = settings
        # Injectable for unit tests — defaults to anthropic extract_structured_json.
        self._llm_call = llm_call or extract_structured_json

    def run(
        self,
        *,
        original_query: str,
        trigger_reason: AgentTriggerReason = AgentTriggerReason.ambiguous_query,
        chat_history: Sequence[ChatTurn | dict[str, str]] | None = None,
        confidence_score: float | None = None,
    ) -> RewriteAgentResult:
        """Rewrite ``original_query``; never raises to the pipeline.

        Args:
            original_query: User question.
            trigger_reason: From Event Policy (usually ``ambiguous_query``).
            chat_history: Optional prior turns from the same session (caller-supplied).
            confidence_score: Score at agent trigger time (audit).

        Returns:
            ``RewriteAgentResult`` — on failure ``rewritten_query`` equals original.
        """
        started = time.perf_counter()
        original = (original_query or "").strip()
        history = _normalize_history(chat_history)
        input_payload: dict[str, Any] = {
            "original_query": original,
            "history_turns": len(history),
        }

        api_key = (self._settings.anthropic_api_key or "").strip()
        model = (self._settings.rewrite_agent_model or "").strip()
        if not api_key or not model or not original:
            latency_ms = _elapsed_ms(started)
            event = _event(
                trigger_reason=trigger_reason,
                model_used=None,
                cost_usd=Decimal("0"),
                latency_ms=latency_ms,
                input_payload=input_payload,
                output_payload={"rewritten_query": original},
                confidence_score=confidence_score,
                success=bool(original),
                error=None if original else "empty_query",
            )
            _log_agent(event)
            return RewriteAgentResult(rewritten_query=original, event=event)

        user_prompt = _build_user_prompt(original, history)
        try:
            result = self._llm_call(
                system=_REWRITE_SYSTEM,
                user=user_prompt,
                model=model,
                api_key=api_key,
                api_base=self._settings.anthropic_api_base,
                max_tokens=int(self._settings.rewrite_agent_max_tokens),
                timeout_seconds=float(self._settings.rewrite_agent_timeout_seconds),
            )
            rewritten = str((result.data or {}).get("rewritten_query") or "").strip()
            if not rewritten:
                rewritten = original
            latency_ms = _elapsed_ms(started)
            event = _event(
                trigger_reason=trigger_reason,
                model_used=str(result.model or model),
                cost_usd=Decimal(str(result.estimated_cost_usd or 0)),
                latency_ms=latency_ms,
                input_payload=input_payload,
                output_payload={"rewritten_query": rewritten},
                confidence_score=confidence_score,
                success=True,
                error=None,
            )
            _log_agent(event)
            return RewriteAgentResult(rewritten_query=rewritten, event=event)
        except Exception as exc:  # noqa: BLE001 — never crash pipeline
            latency_ms = _elapsed_ms(started)
            logger.warning("rewrite_agent_failed", error=str(exc))
            event = _event(
                trigger_reason=trigger_reason,
                model_used=model,
                cost_usd=Decimal("0"),
                latency_ms=latency_ms,
                input_payload=input_payload,
                output_payload={"rewritten_query": original},
                confidence_score=confidence_score,
                success=False,
                error=type(exc).__name__,
            )
            _log_agent(event)
            return RewriteAgentResult(rewritten_query=original, event=event)


def _normalize_history(
    chat_history: Sequence[ChatTurn | dict[str, str]] | None,
) -> list[ChatTurn]:
    if not chat_history:
        return []
    turns: list[ChatTurn] = []
    for item in chat_history:
        turn = item if isinstance(item, ChatTurn) else ChatTurn.model_validate(item)
        content = (turn.content or "").strip()
        if content:
            turns.append(ChatTurn(role=turn.role, content=content))
    # Cap history to keep rewrite prompt small (no full conversation dump in logs).
    return turns[-6:]


def _build_user_prompt(original: str, history: list[ChatTurn]) -> str:
    if not history:
        return f"Original query:\n{original}\n"
    lines = ["Recent chat history (oldest → newest):"]
    for turn in history:
        lines.append(f"- {turn.role}: {turn.content[:400]}")
    lines.append("")
    lines.append(f"Original query:\n{original}")
    return "\n".join(lines)


def _event(
    *,
    trigger_reason: AgentTriggerReason,
    model_used: str | None,
    cost_usd: Decimal,
    latency_ms: int,
    input_payload: dict[str, Any],
    output_payload: dict[str, Any],
    confidence_score: float | None,
    success: bool,
    error: str | None,
) -> AgentEventData:
    return AgentEventData(
        agent_type=AgentType.rewrite,
        trigger_reason=trigger_reason,
        model_used=model_used,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        input_payload=input_payload,
        output_payload=output_payload,
        confidence_score=confidence_score,
        triggered_second_retrieval=True,
        skip_second_retrieval=False,
        success=success,
        error=error,
    )


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))


def _log_agent(event: AgentEventData) -> None:
    logger.info(
        "agent_run",
        agent_type=event.agent_type.value,
        trigger_reason=event.trigger_reason.value,
        latency_ms=event.latency_ms,
        cost_usd=str(event.cost_usd),
        success=event.success,
    )
