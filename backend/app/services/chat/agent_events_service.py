# =============================================================================
# File: agent_events_service.py
# Module/Service: Chat Service (FR14)
# Layer: Service
# Purpose: List agent_events for a chat message within a workspace (RBAC upstream).
# Responsibilities:
#   - Delegate to AgentEventRepository; map to API response models
# Dependencies:
#   - AgentEventRepository, AgentEventResponse
# Public Exports:
#   - AgentEventsService, AgentEventsServiceError
# Database/Table: agent_events
# Related Modules: app.api.chat
# Important Notes: Missing message → not_found; no events → empty list (HTTP 200).
# =============================================================================

from __future__ import annotations

import uuid

from app.repositories.agent_events import AgentEventRepository
from app.schemas.chat import AgentEventResponse


class AgentEventsServiceError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


class AgentEventsService:
    """Application service for GET .../agent-events."""

    def __init__(self, repo: AgentEventRepository) -> None:
        self._repo = repo

    async def list_for_message(
        self,
        *,
        workspace_id: uuid.UUID,
        message_id: uuid.UUID,
    ) -> list[AgentEventResponse]:
        rows = await self._repo.list_by_message(
            workspace_id=workspace_id,
            message_id=message_id,
        )
        if rows is None:
            raise AgentEventsServiceError(
                status_code=404,
                code="not_found",
                message="Chat message not found in this workspace",
            )
        return [
            AgentEventResponse(
                id=r.id,
                agent_type=r.agent_type.value,
                trigger_reason=r.trigger_reason.value,
                confidence_score=r.confidence_score,
                triggered_second_retrieval=r.triggered_second_retrieval,
                model_used=r.model_used,
                cost_usd=float(r.cost_usd),
                latency_ms=r.latency_ms,
                created_at=r.created_at,
            )
            for r in rows
        ]
