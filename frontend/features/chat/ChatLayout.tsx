/**
 * =============================================================================
 * File: ChatLayout.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Pure layout — SessionSidebar + ConversationPanel + MessageInput
 *          (FR4 page structure). No data fetching / business logic here.
 * Responsibilities:
 *   - Compose the three chat regions; own only the mobile session-drawer flag
 *   - Own the local session title header (mobile "Sessions" toggle button —
 *     distinct from the app shell's own hamburger, which opens the *global*
 *     nav sidebar, not this chat-specific one)
 * Dependencies:
 *   - features/chat/SessionSidebar, ConversationPanel, MessageInput, EmptyChatState
 * Public Exports:
 *   - ChatLayout
 * Database/Table: N/A
 * Related Modules: features/chat/ChatPage
 * Important Notes: All data/callbacks are passed in as props — keeps this
 *   component trivially reusable/extensible (Agent Timeline, Suggested
 *   Prompt, etc. can be slotted in later without touching data hooks).
 * =============================================================================
 */

"use client";

import { PanelLeft } from "lucide-react";
import { useState } from "react";

import { ConversationPanel } from "@/features/chat/ConversationPanel";
import { EmptyChatState } from "@/features/chat/EmptyChatState";
import { MessageInput } from "@/features/chat/MessageInput";
import { SessionSidebar } from "@/features/chat/SessionSidebar";
import { sessionTitleLabel } from "@/features/chat/chat-format";
import type { ChatMessage, ChatSession } from "@/types/chat";

type Props = {
  workspaceId: string;
  sessions: ChatSession[];
  sessionsLoading: boolean;
  sessionsError: string | null;
  creatingSession: boolean;
  activeSessionId: string | null;
  activeSession: ChatSession | null;
  onSelectSession: (sessionId: string) => void;
  onNewChat: () => void;

  messages: ChatMessage[];
  messagesLoading: boolean;
  messagesError: string | null;

  isStreaming: boolean;
  streamError: string | null;
  stoppedMessageId: string | null;
  onSend: (content: string) => void;
  onStop: () => void;
  onRegenerate: () => void;
};

export function ChatLayout({
  workspaceId,
  sessions,
  sessionsLoading,
  sessionsError,
  creatingSession,
  activeSessionId,
  activeSession,
  onSelectSession,
  onNewChat,
  messages,
  messagesLoading,
  messagesError,
  isStreaming,
  streamError,
  stoppedMessageId,
  onSend,
  onStop,
  onRegenerate,
}: Props) {
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  return (
    <div className="flex h-[calc(100vh-4rem)] min-h-0">
      <SessionSidebar
        sessions={sessions}
        loading={sessionsLoading}
        error={sessionsError}
        activeSessionId={activeSessionId}
        creating={creatingSession}
        onSelectSession={onSelectSession}
        onNewChat={onNewChat}
        mobileOpen={mobileSidebarOpen}
        onClose={() => setMobileSidebarOpen(false)}
      />

      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex shrink-0 items-center gap-2 border-b border-border-default px-4 py-3 lg:hidden">
          <button
            type="button"
            onClick={() => setMobileSidebarOpen(true)}
            aria-label="Mở danh sách phiên chat"
            className="flex h-8 w-8 items-center justify-center rounded-md text-secondary hover:bg-elevated"
          >
            <PanelLeft className="h-4 w-4" aria-hidden />
          </button>
          <p className="truncate text-body-sm font-medium text-primary">
            {activeSession ? sessionTitleLabel(activeSession) : "Chat"}
          </p>
        </div>

        {activeSessionId ? (
          <>
            <ConversationPanel
              workspaceId={workspaceId}
              messages={messages}
              loading={messagesLoading}
              error={messagesError}
              isStreaming={isStreaming}
              streamError={streamError}
              stoppedMessageId={stoppedMessageId}
              onRegenerate={onRegenerate}
            />
            <MessageInput
              isStreaming={isStreaming}
              onSend={onSend}
              onStop={onStop}
            />
          </>
        ) : (
          <EmptyChatState variant="no-session" onNewChat={onNewChat} creating={creatingSession} />
        )}
      </div>
    </div>
  );
}
