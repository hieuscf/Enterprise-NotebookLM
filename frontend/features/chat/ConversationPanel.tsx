/**
 * =============================================================================
 * File: ConversationPanel.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Scrollable message list — history, streaming, loading, error,
 *          auto-scroll (FR4 §3/§8/§9/§10).
 * Responsibilities:
 *   - Render messages in backend order (never reversed)
 *   - Show ThinkingIndicator before the first token; hide once tokens flow
 *   - Show an inline, non-destructive error banner on stream failure + retry
 *   - Auto-scroll to bottom only while the user is already at the bottom;
 *     otherwise show a "Nội dung mới" button
 * Dependencies:
 *   - hooks/useAutoScroll, features/chat/ChatMessageItem, ThinkingIndicator
 * Public Exports:
 *   - ConversationPanel
 * Database/Table: N/A
 * Related Modules: features/chat/ChatLayout, hooks/useChatStream
 * Important Notes: Only the last message in the array can ever be "currently
 *   streaming" or "regenerate-able" — sendMessage always appends at the end.
 * =============================================================================
 */

"use client";

import { AlertCircle, ArrowDown } from "lucide-react";

import { ChatMessageItem } from "@/features/chat/ChatMessageItem";
import { EmptyChatState } from "@/features/chat/EmptyChatState";
import { ThinkingIndicator } from "@/features/chat/ThinkingIndicator";
import { useAutoScroll } from "@/hooks/useAutoScroll";
import type { ChatMessage } from "@/types/chat";

type Props = {
  workspaceId: string;
  messages: ChatMessage[];
  loading: boolean;
  error: string | null;
  isStreaming: boolean;
  streamError: string | null;
  stoppedMessageId: string | null;
  onRegenerate: () => void;
};

export function ConversationPanel({
  workspaceId,
  messages,
  loading,
  error,
  isStreaming,
  streamError,
  stoppedMessageId,
  onRegenerate,
}: Props) {
  const lastMessage = messages[messages.length - 1];
  const waitingForFirstToken =
    isStreaming &&
    lastMessage?.role === "assistant" &&
    lastMessage.content.length === 0 &&
    (lastMessage.status === "pending" || lastMessage.status === "streaming" || !lastMessage.status);

  const { containerRef, handleScroll, hasNewContent, scrollToBottom } = useAutoScroll(
    `${messages.length}:${lastMessage?.content.length ?? 0}`,
  );

  if (loading) {
    return (
      <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-4 sm:p-6" aria-busy aria-label="Đang tải hội thoại">
        {Array.from({ length: 3 }).map((_, i) => (
          <div
            key={i}
            className={i % 2 === 0 ? "flex justify-end" : "flex justify-start"}
          >
            <div className="h-14 w-2/3 animate-pulse rounded-lg border border-border-default bg-elevated/60" />
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-1 items-center justify-center p-6">
        <div
          role="alert"
          className="flex max-w-md items-start gap-3 rounded-lg border border-danger/30 bg-danger/5 px-4 py-3 text-body-sm text-danger"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          <p>{error}</p>
        </div>
      </div>
    );
  }

  if (messages.length === 0) {
    return (
      <div className="flex-1 overflow-y-auto">
        <EmptyChatState variant="empty-session" />
      </div>
    );
  }

  return (
    <div className="relative flex-1 overflow-hidden">
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex h-full flex-col gap-3 overflow-y-auto p-4 sm:p-6"
      >
        {messages.map((message, index) => {
          const isLast = index === messages.length - 1;
          const isStreamingThis = isStreaming && isLast && message.role === "assistant";
          const canRegenerate =
            !isStreaming &&
            !streamError &&
            isLast &&
            message.role === "assistant" &&
            message.content.length > 0;

          return (
            <ChatMessageItem
              key={message.id}
              workspaceId={workspaceId}
              message={message}
              isStreamingThis={isStreamingThis}
              isStopped={stoppedMessageId === message.id}
              canRegenerate={canRegenerate}
              onRegenerate={onRegenerate}
            />
          );
        })}

        {waitingForFirstToken ? <ThinkingIndicator /> : null}

        {streamError ? (
          <div
            role="alert"
            className="flex items-start gap-3 rounded-lg border border-danger/30 bg-danger/5 px-4 py-3 text-body-sm text-danger"
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <div className="flex-1">
              <p>{streamError}</p>
              <button
                type="button"
                onClick={onRegenerate}
                className="mt-1 font-medium underline decoration-danger/50 hover:decoration-danger"
              >
                Thử lại
              </button>
            </div>
          </div>
        ) : null}
      </div>

      {hasNewContent ? (
        <button
          type="button"
          onClick={() => scrollToBottom("smooth")}
          className="absolute bottom-4 left-1/2 flex -translate-x-1/2 items-center gap-1.5 rounded-full bg-accent-primary px-3 py-1.5 text-caption font-medium text-white shadow-md hover:bg-accent-primary-hover"
        >
          <ArrowDown className="h-3.5 w-3.5" aria-hidden />
          Nội dung mới
        </button>
      ) : null}
    </div>
  );
}
