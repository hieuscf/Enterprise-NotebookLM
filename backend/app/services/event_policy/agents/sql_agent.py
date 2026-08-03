# =============================================================================
# File: sql_agent.py
# Module/Service: SQL Agent (FR14)
# Layer: Service
# Purpose: Recover structured/metadata queries misclassified as complex (0 LLM).
# Responsibilities:
#   - Reuse MetadataHandler / MetadataRegistry (no dynamic SQL)
#   - Emit AgentEventData with skip_second_retrieval=True on success
# Dependencies:
#   - MetadataHandler, AgentEventData
# Public Exports:
#   - SqlAgent, SqlAgentResult
# Database/Table: via MetadataRepository only; Part 4 writes agent_events
# Important Notes: Parse/whitelist miss → fallback_to_complex (pipeline continues).
# =============================================================================

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.logging import get_logger
from app.models.enums import AgentTriggerReason, AgentType, RouteType
from app.services.event_policy.models import AgentEventData
from app.services.query_router.handlers.metadata_handler import MetadataHandler
from app.services.query_router.response_models import QueryRouterResult

logger = get_logger(__name__)


class SqlAgentResult(BaseModel):
    """SQL/Metadata Agent output — may short-circuit Second Retrieval."""

    model_config = ConfigDict(frozen=True)

    sql_result: dict[str, Any] | None = None
    answer: str | None = None
    skip_second_retrieval: bool = True
    fallback_to_complex: bool = False
    event: AgentEventData


class SqlAgent:
    """Metadata recovery agent — wraps existing MetadataHandler (no SQL rebuild)."""

    def __init__(self, metadata_handler: MetadataHandler) -> None:
        self._handler = metadata_handler

    async def run(
        self,
        *,
        workspace_id: UUID,
        query_text: str,
        trigger_reason: AgentTriggerReason = AgentTriggerReason.structured_misclassified,
        confidence_score: float | None = None,
    ) -> SqlAgentResult:
        """Execute whitelist metadata query; fallback to complex on miss/error."""
        started = time.perf_counter()
        input_payload: dict[str, Any] = {
            "query_text": (query_text or "")[:200],
            "workspace_id": str(workspace_id),
        }

        try:
            result: QueryRouterResult = await self._handler.handle(
                workspace_id=workspace_id,
                query_text=query_text,
            )
        except Exception as exc:  # noqa: BLE001
            latency_ms = _elapsed_ms(started)
            logger.warning("sql_agent_failed", error=str(exc))
            event = _event(
                trigger_reason=trigger_reason,
                latency_ms=latency_ms,
                input_payload=input_payload,
                output_payload={"sql_result": None, "fallback": True},
                confidence_score=confidence_score,
                success=False,
                error=type(exc).__name__,
                skip_second_retrieval=False,
            )
            _log_agent(event)
            return SqlAgentResult(
                sql_result=None,
                answer=None,
                skip_second_retrieval=False,
                fallback_to_complex=True,
                event=event,
            )

        latency_ms = _elapsed_ms(started)
        if result.route_type is not RouteType.metadata or not result.answer:
            event = _event(
                trigger_reason=trigger_reason,
                latency_ms=latency_ms,
                input_payload=input_payload,
                output_payload={
                    "sql_result": None,
                    "fallback_reason": (result.metadata or {}).get("fallback_reason"),
                },
                confidence_score=confidence_score,
                success=False,
                error="metadata_whitelist_miss",
                skip_second_retrieval=False,
            )
            _log_agent(event)
            return SqlAgentResult(
                sql_result=None,
                answer=None,
                skip_second_retrieval=False,
                fallback_to_complex=True,
                event=event,
            )

        sql_result = {
            "answer": result.answer,
            "route_type": result.route_type.value,
            "metadata": result.metadata or {},
            "confidence": result.confidence,
        }
        event = _event(
            trigger_reason=trigger_reason,
            latency_ms=latency_ms,
            input_payload=input_payload,
            output_payload={"sql_result": sql_result},
            confidence_score=confidence_score,
            success=True,
            error=None,
            skip_second_retrieval=True,
        )
        _log_agent(event)
        return SqlAgentResult(
            sql_result=sql_result,
            answer=result.answer,
            skip_second_retrieval=True,
            fallback_to_complex=False,
            event=event,
        )


def _event(
    *,
    trigger_reason: AgentTriggerReason,
    latency_ms: int,
    input_payload: dict[str, Any],
    output_payload: dict[str, Any],
    confidence_score: float | None,
    success: bool,
    error: str | None,
    skip_second_retrieval: bool,
) -> AgentEventData:
    return AgentEventData(
        agent_type=AgentType.sql,
        trigger_reason=trigger_reason,
        model_used=None,
        cost_usd=Decimal("0"),
        latency_ms=latency_ms,
        input_payload=input_payload,
        output_payload=output_payload,
        confidence_score=confidence_score,
        triggered_second_retrieval=False,
        skip_second_retrieval=skip_second_retrieval,
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
