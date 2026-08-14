/**
 * =============================================================================
 * File: chat.ts
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: TypeScript types for Chat sessions/messages, matching OpenAPI 1:1.
 * Responsibilities:
 *   - Mirror backend ChatSession / ChatMessage / MessageGeneration schemas
 * Dependencies:
 *   - docs/Enterprise_notebooklm_openapi.yaml §Chat
 * Public Exports:
 *   - ChatSession, ChatMessage, MessageGeneration, ChatPipelineStage
 *   - MessageRole, RouteType, ConfidenceLevel, FinishReason
 * Database/Table: N/A
 * Related Modules: lib/chat.api.ts, features/chat/*, types/citations
 * Important Notes:
 *   - ChatSession intentionally has no last_message_preview/message_count —
 *     backend does not expose those fields yet (see session_service.py TODO).
 *   - Citation type is reused as-is from types/citations.ts (FR5); not
 *     redefined here.
 * =============================================================================
 */

import type { Citation } from "./citations";

export type MessageRole = "user" | "assistant";

/** Client-side lifecycle for live streaming (history rows omit this → completed). */
export type ChatMessageStatus = "pending" | "streaming" | "completed" | "failed";

/** Live-only pipeline hint while waiting for the first token (SSE `status`). */
export type ChatPipelineStage = "retrieving" | "generating" | "verifying";

export type RouteType = "cache_hit" | "metadata" | "factoid" | "complex";

export type ConfidenceLevel = "high" | "low";

export type FinishReason = "stop" | "length" | "content_filter" | "tool_calls";

export type ChatSession = {
  id: string;
  workspace_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
};

export type MessageGeneration = {
  route_type: RouteType;
  confidence_level: ConfidenceLevel | null;
  confidence_score: number | null;
  agent_triggered: boolean;
  model_used: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  cost_usd: number | null;
  latency_ms: number | null;
  finish_reason: FinishReason | null;
};

export type ChatMessage = {
  id: string;
  session_id: string;
  role: MessageRole;
  content: string;
  generation: MessageGeneration | null;
  citations: Citation[];
  created_at: string;
  /** Live-only; omitted on GET history (treat as completed). */
  status?: ChatMessageStatus;
  /** Live-only SSE stage while content is still empty. */
  pipeline_stage?: ChatPipelineStage;
};
