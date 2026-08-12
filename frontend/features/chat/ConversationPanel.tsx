/**
 * =============================================================================
 * File: ConversationPanel.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Scrollable research conversation — history, streaming, auto-scroll.
 * Responsibilities:
 *   - Render messages; thinking indicator; stream error + retry; auto-scroll
 * Dependencies:
 *   - hooks/useAutoScroll, ChatMessageItem, ThinkingIndicator
 * Public Exports:
 *   - ConversationPanel
 * Database/Table: N/A
 * Related Modules: features/chat/ChatLayout, hooks/useChatStream
 * Important Notes: Reading surface — no heavy card chrome around answers.
 * =============================================================================
 */

"use client";

import { AlertCircle, ArrowDown } from "lucide-react";

import { ChatMessageItem } from "@/features/chat/ChatMessageItem";
import type { DocumentMetaLookup } from "@/features/chat/citation/citation-mapper";
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
  docsById: Map<string, DocumentMetaLookup>;
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
  docsById,
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
      <div
        className="flex flex-1 flex-col gap-4 overflow-y-auto px-4 py-6 sm:px-6"
        aria-busy
        aria-label="Đang tải hội thoại"
      >
        {Array.from({ length: 3 }).map((_, i) => (
          <div
            key={i}
            className={i % 2 === 0 ? "flex justify-end" : "flex justify-start gap-3"}
          >
            {i % 2 !== 0 ? (
              <div className="h-7 w-7 shrink-0 animate-pulse rounded-full bg-elevated/60" />
            ) : null}
            <div className="h-16 w-2/3 max-w-xl animate-pulse rounded-2xl bg-elevated/60" />
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
        className="flex h-full flex-col gap-5 overflow-y-auto px-4 py-5 sm:px-6 sm:py-6"
      >
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-5">
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
                docsById={docsById}
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
                  className="mt-1 cursor-pointer font-medium underline decoration-danger/50 hover:decoration-danger"
                >
                  Thử lại
                </button>
              </div>
            </div>
          ) : null}
        </div>
      </div>

      {hasNewContent ? (
        <button
          type="button"
          onClick={() => scrollToBottom("smooth")}
          className="absolute bottom-4 left-1/2 flex -translate-x-1/2 cursor-pointer items-center gap-1.5 rounded-full bg-accent-primary px-3 py-1.5 text-caption font-medium text-white shadow-md hover:bg-accent-primary-hover"
        >
          <ArrowDown className="h-3.5 w-3.5" aria-hidden />
          Nội dung mới
        </button>
      ) : null}
    </div>
  );
}
