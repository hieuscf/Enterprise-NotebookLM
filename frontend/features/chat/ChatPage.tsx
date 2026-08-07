/**
 * =============================================================================
 * File: ChatPage.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Top-level Chat feature entry — owns AppShell + wires the chat
 *          hooks together; the only place data flows into ChatLayout (FR4).
 * Responsibilities:
 *   - useChatSessions / useChatMessages / useChatStream composition
 *   - Auto-redirect /chat -> /chat/{mostRecentSessionId} when one exists
 *   - New Chat -> create session -> navigate to it (existing POST endpoint)
 *   - Abort any in-flight stream when the active session changes/unmounts
 * Dependencies:
 *   - hooks/useChatSessions, useChatMessages, useChatStream
 *   - features/chat/ChatLayout, features/shell/AppShell
 * Public Exports:
 *   - ChatPage
 * Database/Table: N/A
 * Related Modules: app/workspaces/[id]/chat/page.tsx, [sessionId]/page.tsx
 * Important Notes: No business logic in JSX — this component only wires
 *   hooks to props; ChatLayout and its children stay presentational.
 * =============================================================================
 */

"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo } from "react";

import { useAuth } from "@/hooks/useAuth";
import { useChatMessages } from "@/hooks/useChatMessages";
import { useChatSessions } from "@/hooks/useChatSessions";
import { useChatStream } from "@/hooks/useChatStream";
import { AppShell } from "@/features/shell/AppShell";

import { ChatLayout } from "@/features/chat/ChatLayout";

type Props = {
  workspaceId: string;
  sessionId: string | null;
};

export function ChatPage({ workspaceId, sessionId }: Props) {
  const router = useRouter();
  const { user } = useAuth();

  const {
    sessions,
    loading: sessionsLoading,
    error: sessionsError,
    creating: creatingSession,
    reload: reloadSessions,
    createSession,
  } = useChatSessions(workspaceId);

  const {
    messages,
    setMessages,
    loading: messagesLoading,
    error: messagesError,
  } = useChatMessages(workspaceId, sessionId);

  const { isStreaming, streamError, stoppedMessageId, sendMessage, stopStreaming, regenerate } =
    useChatStream(workspaceId, sessionId, setMessages, () => {
      void reloadSessions();
    });

  // Abort any in-flight stream when the user switches session or leaves.
  useEffect(() => {
    return () => stopStreaming();
  }, [sessionId, stopStreaming]);

  // /chat (no sessionId yet) -> most recent session, once sessions load.
  useEffect(() => {
    if (sessionId || sessionsLoading || sessions.length === 0) return;
    router.replace(`/workspaces/${workspaceId}/chat/${sessions[0].id}`);
  }, [sessionId, sessionsLoading, sessions, router, workspaceId]);

  const activeSession = useMemo(
    () => sessions.find((s) => s.id === sessionId) ?? null,
    [sessions, sessionId],
  );

  const handleNewChat = useCallback(async () => {
    const session = await createSession();
    if (session) router.push(`/workspaces/${workspaceId}/chat/${session.id}`);
  }, [createSession, router, workspaceId]);

  const handleSelectSession = useCallback(
    (id: string) => {
      if (id === sessionId) return;
      router.push(`/workspaces/${workspaceId}/chat/${id}`);
    },
    [sessionId, router, workspaceId],
  );

  const handleRegenerate = useCallback(() => {
    regenerate();
  }, [regenerate]);

  return (
    <AppShell active="chat" user={user} workspaceId={workspaceId}>
      <ChatLayout
        workspaceId={workspaceId}
        sessions={sessions}
        sessionsLoading={sessionsLoading}
        sessionsError={sessionsError}
        creatingSession={creatingSession}
        activeSessionId={sessionId}
        activeSession={activeSession}
        onSelectSession={handleSelectSession}
        onNewChat={handleNewChat}
        messages={messages}
        messagesLoading={messagesLoading}
        messagesError={messagesError}
        isStreaming={isStreaming}
        streamError={streamError}
        stoppedMessageId={stoppedMessageId}
        onSend={sendMessage}
        onStop={stopStreaming}
        onRegenerate={handleRegenerate}
      />
    </AppShell>
  );
}
