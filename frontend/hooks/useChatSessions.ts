/**
 * =============================================================================
 * File: useChatSessions.ts
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Client hook for the chat session list + create action (FR4/FR10).
 * Responsibilities:
 *   - Load GET .../chat/sessions (backend-sorted; never re-sorted here)
 *   - Expose createSession() for the "New Chat" button
 * Dependencies:
 *   - lib/chat.api, lib/api-client
 * Public Exports:
 *   - useChatSessions
 * Database/Table: N/A
 * Related Modules: features/chat/ChatPage, SessionSidebar
 * Important Notes: Local component state only — mirrors useSearch.ts /
 *   useDocuments.ts convention (no React Query in this codebase).
 * =============================================================================
 */

"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiClientError } from "@/lib/api-client";
import { createChatSession, listChatSessions } from "@/lib/chat.api";
import type { ChatSession } from "@/types/chat";

export function useChatSessions(workspaceId: string) {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listChatSessions(workspaceId);
      setSessions(data);
    } catch (err) {
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Không tải được danh sách phiên chat.",
      );
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const createSession = useCallback(
    async (title?: string | null): Promise<ChatSession | null> => {
      setCreating(true);
      try {
        const session = await createChatSession(workspaceId, title ?? null);
        // Optimistic prepend; next reload() (e.g. after first message) will
        // reconcile true backend order (updated_at DESC).
        setSessions((prev) => [session, ...prev]);
        return session;
      } catch (err) {
        setError(
          err instanceof ApiClientError
            ? err.message
            : "Không tạo được phiên chat mới.",
        );
        return null;
      } finally {
        setCreating(false);
      }
    },
    [workspaceId],
  );

  return { sessions, loading, error, creating, reload, createSession };
}
