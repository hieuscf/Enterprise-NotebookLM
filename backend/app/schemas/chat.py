# =============================================================================
# File: chat.py
# Module/Service: Chat Service
# Layer: Schema
# Purpose: Pydantic request/response models for Chat Conversation Memory + FR14.
# Responsibilities:
#   - Match OpenAPI ChatSession / ChatMessage / MessageGeneration / Citation
#   - AgentEventResponse for FR14 agent-events (no payloads)
# Dependencies:
#   - pydantic
# Public Exports:
#   - ChatSessionCreateRequest, ChatSessionResponse
#   - ChatMessageResponse, MessageGenerationResponse, CitationResponse
#   - AgentEventResponse
# Database/Table: chat_sessions, chat_messages, message_generations, citations
# Related Modules: Enterprise_notebooklm_openapi.yaml §Chat
# Important Notes:
#   - OpenAPI ChatSession has no last_message_preview/message_count — do not add.
#   - User messages: generation=null, citations=[].
# =============================================================================

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentEventResponse(BaseModel):
    """Public AgentEvent DTO — excludes sensitive JSON payloads."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_type: Literal["rewrite", "graph", "sql"]
    trigger_reason: Literal[
        "ambiguous_query",
        "multi_hop_reasoning",
        "structured_misclassified",
    ]
    confidence_score: float | None = None
    triggered_second_retrieval: bool
    model_used: str | None = None
    cost_usd: float = Field(ge=0)
    latency_ms: int = Field(ge=0)
    created_at: datetime


class ChatSessionCreateRequest(BaseModel):
    """POST /chat/sessions body — title optional (NULL until Part 2)."""

    title: str | None = Field(default=None, max_length=512)


class ChatSessionResponse(BaseModel):
    """OpenAPI ChatSession summary/detail (no nested messages)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str | None = None
    created_at: datetime
    updated_at: datetime


class MessageGenerationResponse(BaseModel):
    """OpenAPI MessageGeneration nested under assistant ChatMessage."""

    model_config = ConfigDict(from_attributes=True)

    route_type: Literal["cache_hit", "metadata", "factoid", "complex"]
    confidence_level: Literal["high", "low"] | None = None
    confidence_score: float | None = None
    agent_triggered: bool = False
    model_used: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    latency_ms: int | None = None
    finish_reason: Literal["stop", "length", "content_filter", "tool_calls"] | None = None


class CitationResponse(BaseModel):
    """OpenAPI Citation — document_id resolved via retrieval joins."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    message_id: uuid.UUID
    retrieval_id: uuid.UUID
    document_id: uuid.UUID | None = None
    text_snippet: str
    verified: bool
    order_index: int


class ChatMessageResponse(BaseModel):
    """OpenAPI ChatMessage with nested generation + citations."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str
    generation: MessageGenerationResponse | None = None
    citations: list[CitationResponse] = Field(default_factory=list)
    created_at: datetime
