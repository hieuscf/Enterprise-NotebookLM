/**
 * =============================================================================
 * File: useChatStream.ts
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Streaming lifecycle for one chat session — SSE token append,
 *          abort, and regenerate (FR4 §5/§6/§9 + low-cost UX additions).
 * Responsibilities:
 *   - sendMessage(): optimistic user+assistant bubbles -> token-by-token
 *     append -> citations -> final authoritative message -> done
 *   - stopStreaming(): abort the in-flight fetch, freeze partial content
 *   - regenerate(): resend the last user content (no dedicated "regenerate"
 *     endpoint exists in the API contract — this creates a new user+
 *     assistant exchange, same as a manual retry)
 * Dependencies:
 *   - lib/chat.api (sendChatMessageStream), lib/api-client (ApiClientError)
 * Public Exports:
 *   - useChatStream
 * Database/Table: N/A
 * Related Modules: hooks/useChatMessages (setMessages), features/chat/*
 * Important Notes:
 *   - Core state is only { isStreaming, streamError } — the "current
 *     assistant message" lives directly in the messages array (via
 *     setMessages), not as a second duplicated object.
 *   - Session list refresh is the caller's responsibility via onSettled —
 *     never called per-token, only once the stream finishes (done/error).
 *   - Aborting only stops the client from reading further chunks; the
 *     backend has already computed+persisted the full answer by the time
 *     streaming starts (see message_service.stream_answer_events), so the
 *     partial text is intentionally left as-is rather than silently
 *     replaced with the full answer.
 *   - On a genuine failure (SSE error frame or network drop) before any
 *     token arrived, the empty optimistic assistant placeholder is removed
 *     so the UI shows only the error banner + retry, never a confusing
 *     "no content" bubble next to it.
 *   - Updates target the SAME assistant row via message_id (temp → real);
 *     generation's final `message` always wins for content.
 * =============================================================================
 */

"use client";

import { useCallback, useRef, useState } from "react";

import { ApiClientError } from "@/lib/api-client";
import { sendChatMessageStream } from "@/lib/chat.api";
import type { ChatMessage } from "@/types/chat";

type SetMessages = React.Dispatch<React.SetStateAction<ChatMessage[]>>;

function makeTempId(prefix: string): string {
  return `temp-${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

/** Locate the in-flight assistant bubble (by id, else last assistant row). */
function patchAssistant(
  prev: ChatMessage[],
  assistantId: string | null,
  patch: (current: ChatMessage) => ChatMessage,
): ChatMessage[] {
  const byId = assistantId ? prev.findIndex((m) => m.id === assistantId) : -1;
  if (byId >= 0) {
    const next = [...prev];
    next[byId] = patch(prev[byId]);
    return next;
  }
  for (let i = prev.length - 1; i >= 0; i -= 1) {
    if (prev[i].role === "assistant") {
      const next = [...prev];
      next[i] = patch(prev[i]);
      return next;
    }
  }
  return prev;
}

/** Drop the assistant placeholder only if it never received any token. */
function dropEmptyAssistantPlaceholder(setMessages: SetMessages, assistantId: string | null) {
  if (!assistantId) return;
  setMessages((prev) =>
    prev.filter((m) => !(m.id === assistantId && m.role === "assistant" && m.content.length === 0)),
  );
}

export function useChatStream(
  workspaceId: string,
  sessionId: string | null,
  setMessages: SetMessages,
  onSettled?: () => void,
) {
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [stoppedMessageId, setStoppedMessageId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const assistantIdRef = useRef<string | null>(null);
  const lastUserContentRef = useRef<string>("");

  const sendMessage = useCallback(
    async (content: string) => {
      const trimmed = content.trim();
      if (!trimmed || !sessionId || isStreaming) return;

      lastUserContentRef.current = trimmed;
      setStreamError(null);
      setStoppedMessageId(null);

      const nowIso = new Date().toISOString();
      const tempUserId = makeTempId("user");
      const tempAssistantId = makeTempId("assistant");
      assistantIdRef.current = tempAssistantId;

      setMessages((prev) => [
        ...prev,
        {
          id: tempUserId,
          session_id: sessionId,
          role: "user",
          content: trimmed,
          generation: null,
          citations: [],
          created_at: nowIso,
          status: "completed",
        },
        {
          id: tempAssistantId,
          session_id: sessionId,
          role: "assistant",
          content: "",
          generation: null,
          citations: [],
          created_at: nowIso,
          status: "pending",
        },
      ]);

      setIsStreaming(true);
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        await sendChatMessageStream(
          workspaceId,
          sessionId,
          trimmed,
          {
            onToken: (text) => {
              setMessages((prev) =>
                patchAssistant(prev, assistantIdRef.current, (m) => ({
                  ...m,
                  content: m.content + text,
                  status: "streaming",
                })),
              );
            },
            onCitations: (citations) => {
              setMessages((prev) =>
                patchAssistant(prev, assistantIdRef.current, (m) => ({
                  ...m,
                  citations,
                  status: m.status === "pending" ? "streaming" : m.status,
                })),
              );
            },
            onGeneration: (_generation, message) => {
              // Final authoritative message wins (real id + persisted content).
              setMessages((prev) =>
                patchAssistant(prev, assistantIdRef.current, () => ({
                  ...message,
                  status: "completed" as const,
                })),
              );
              if (message?.id) {
                assistantIdRef.current = message.id;
              }
            },
            onDone: () => {
              setMessages((prev) =>
                patchAssistant(prev, assistantIdRef.current, (m) =>
                  m.status === "completed" || m.status === "failed"
                    ? m
                    : { ...m, status: "completed" },
                ),
              );
              setIsStreaming(false);
              onSettled?.();
            },
            onError: (message) => {
              setStreamError(message);
              setMessages((prev) =>
                patchAssistant(prev, assistantIdRef.current, (m) => ({
                  ...m,
                  status: "failed",
                })),
              );
              setIsStreaming(false);
              dropEmptyAssistantPlaceholder(setMessages, assistantIdRef.current);
            },
          },
          controller.signal,
        );
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") {
          setStoppedMessageId(assistantIdRef.current);
          setMessages((prev) =>
            patchAssistant(prev, assistantIdRef.current, (m) => ({
              ...m,
              status: m.content.trim() ? "completed" : "failed",
            })),
          );
        } else {
          setStreamError(
            err instanceof ApiClientError
              ? err.message
              : "Mất kết nối trong khi nhận câu trả lời.",
          );
          setMessages((prev) =>
            patchAssistant(prev, assistantIdRef.current, (m) => ({
              ...m,
              status: "failed",
            })),
          );
          dropEmptyAssistantPlaceholder(setMessages, assistantIdRef.current);
        }
        setIsStreaming(false);
      } finally {
        abortRef.current = null;
      }
    },
    [workspaceId, sessionId, isStreaming, setMessages, onSettled],
  );

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const regenerate = useCallback(
    (userContent?: string) => {
      const content = userContent ?? lastUserContentRef.current;
      if (content) void sendMessage(content);
    },
    [sendMessage],
  );

  return {
    isStreaming,
    streamError,
    stoppedMessageId,
    sendMessage,
    stopStreaming,
    regenerate,
  };
}
