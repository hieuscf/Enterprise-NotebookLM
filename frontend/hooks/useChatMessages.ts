/**
 * =============================================================================
 * File: useChatMessages.ts
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Client hook for one session's message history (Conversation Memory).
 * Responsibilities:
 *   - Load GET .../sessions/{id}/messages (oldest→newest; never reversed)
 *   - Expose setMessages so useChatStream can patch state in place while
 *     streaming, without a second parallel copy of the conversation
 * Dependencies:
 *   - lib/chat.api, lib/api-client
 * Public Exports:
 *   - useChatMessages
 * Database/Table: N/A
 * Related Modules: features/chat/ChatPage, ConversationPanel, useChatStream
 * Important Notes: Resets to [] when sessionId is null/changes — switching
 *   sessions must not leak the previous session's messages.
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiClientError } from "@/lib/api-client";
import { listChatMessages } from "@/lib/chat.api";
import type { ChatMessage } from "@/types/chat";

export function useChatMessages(workspaceId: string, sessionId: string | null) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!sessionId) {
      setMessages([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await listChatMessages(workspaceId, sessionId);
      setMessages(data);
    } catch (err) {
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Không tải được lịch sử hội thoại.",
      );
    } finally {
      setLoading(false);
    }
  }, [workspaceId, sessionId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { messages, setMessages, loading, error, reload };
}
