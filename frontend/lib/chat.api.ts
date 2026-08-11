/**
 * =============================================================================
 * File: chat.api.ts
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Typed calls to /workspaces/{id}/chat/* incl. manual SSE parsing.
 * Responsibilities:
 *   - listChatSessions / createChatSession
 *   - listChatMessages
 *   - sendChatMessageStream — POST .../messages, parse the SSE frame format
 *     emitted by backend format_sse() (event: {type}\ndata: {json}\n\n)
 * Dependencies:
 *   - lib/api-client (apiFetch, parseApiError, ApiClientError)
 * Public Exports:
 *   - listChatSessions, createChatSession, listChatMessages
 *   - sendChatMessageStream, type ChatStreamHandlers
 * Database/Table: N/A (talks to chat_sessions / chat_messages via API)
 * Related Modules: hooks/useChatSessions, useChatMessages, useChatStream
 * Important Notes:
 *   - SSE event order is fixed server-side: token* -> citations -> generation
 *     -> done, or a single error frame. Do not assume any other order.
 *   - Must pass Accept: text/event-stream explicitly — apiFetch defaults to
 *     application/json when the caller does not set an Accept header.
 *   - Uses TextDecoder({stream:true}) so multi-byte UTF-8 (Vietnamese) text
 *     split across network chunks decodes correctly.
 * =============================================================================
 */

import { apiFetch, ApiClientError, parseApiError } from "@/lib/api-client";
import type { ChatMessage, ChatSession, MessageGeneration } from "@/types/chat";
import type { Citation } from "@/types/citations";

export async function listChatSessions(
  workspaceId: string,
  page = 1,
  pageSize = 20,
): Promise<ChatSession[]> {
  const response = await apiFetch(
    `/workspaces/${workspaceId}/chat/sessions?page=${page}&page_size=${pageSize}`,
  );
  if (!response.ok) throw await parseApiError(response);
  return (await response.json()) as ChatSession[];
}

export async function createChatSession(
  workspaceId: string,
  title?: string | null,
): Promise<ChatSession> {
  const response = await apiFetch(`/workspaces/${workspaceId}/chat/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(title ? { title } : {}),
  });
  if (!response.ok) throw await parseApiError(response);
  return (await response.json()) as ChatSession;
}

export async function listChatMessages(
  workspaceId: string,
  sessionId: string,
  page = 1,
  pageSize = 100,
): Promise<ChatMessage[]> {
  const response = await apiFetch(
    `/workspaces/${workspaceId}/chat/sessions/${sessionId}/messages?page=${page}&page_size=${pageSize}`,
  );
  if (!response.ok) throw await parseApiError(response);
  return (await response.json()) as ChatMessage[];
}

// ---------------------------------------------------------------------------
// Streaming — POST .../messages (SSE)
// ---------------------------------------------------------------------------

export type ChatStreamHandlers = {
  onToken?: (text: string) => void;
  onCitations?: (citations: Citation[]) => void;
  onGeneration?: (generation: MessageGeneration | null, message: ChatMessage) => void;
  onDone?: () => void;
  /** Server-reported error frame (ChatServiceError) — history is left intact. */
  onError?: (message: string, code?: string) => void;
};

type SseFramePayload =
  | { type: "token"; text: string }
  | { type: "citations"; citations: Citation[] }
  | { type: "generation"; generation: MessageGeneration | null; message: ChatMessage }
  | { type: "done" }
  | { type: "error"; code: string; message: string; status_code?: number };

function dispatchFrame(frame: string, handlers: ChatStreamHandlers): void {
  const dataLine = frame
    .split("\n")
    .find((line) => line.startsWith("data:"));
  if (!dataLine) return;

  const jsonText = dataLine.slice("data:".length).trim();
  if (!jsonText) return;

  let payload: SseFramePayload;
  try {
    payload = JSON.parse(jsonText) as SseFramePayload;
  } catch {
    return;
  }

  switch (payload.type) {
    case "token":
      handlers.onToken?.(payload.text ?? "");
      break;
    case "citations":
      handlers.onCitations?.(payload.citations ?? []);
      break;
    case "generation":
      if (payload.message) {
        handlers.onGeneration?.(payload.generation ?? null, payload.message);
      }
      break;
    case "done":
      handlers.onDone?.();
      break;
    case "error":
      handlers.onError?.(payload.message, payload.code);
      break;
    default:
      break;
  }
}

/**
 * POST a user message and stream the assistant answer via SSE.
 * Resolves once the stream ends (done/error frame or network close/abort).
 * Throws only on transport-level failures the SSE frames cannot describe
 * (e.g. non-2xx before any frame, or AbortError when `signal` is aborted).
 */
export async function sendChatMessageStream(
  workspaceId: string,
  sessionId: string,
  content: string,
  handlers: ChatStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await apiFetch(
    `/workspaces/${workspaceId}/chat/sessions/${sessionId}/messages`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify({ content }),
      signal,
    },
  );

  const contentType = response.headers.get("Content-Type") ?? "";
  if (!contentType.toLowerCase().includes("text/event-stream") || !response.body) {
    // Proxy/backend returned a JSON error (e.g. 401/404/422) instead of SSE.
    if (!response.ok) {
      throw await parseApiError(response);
    }
    // Defensive: JSON success body without streaming — surface as a single
    // error frame equivalent so the caller can still show something sane.
    handlers.onError?.("Không nhận được phản hồi streaming từ máy chủ.");
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let separatorIndex = buffer.indexOf("\n\n");
      while (separatorIndex !== -1) {
        const frame = buffer.slice(0, separatorIndex);
        buffer = buffer.slice(separatorIndex + 2);
        dispatchFrame(frame, handlers);
        separatorIndex = buffer.indexOf("\n\n");
      }
    }
    // Flush any trailing bytes/frame without a final separator.
    buffer += decoder.decode();
    if (buffer.trim()) dispatchFrame(buffer, handlers);
  } catch (err) {
    if (signal?.aborted) {
      const abortError = new Error("Stream aborted by user");
      abortError.name = "AbortError";
      throw abortError;
    }
    throw err instanceof ApiClientError
      ? err
      : new ApiClientError(0, "network_error", "Mất kết nối trong khi nhận câu trả lời.");
  } finally {
    reader.cancel().catch(() => undefined);
  }
}
