/**
 * =============================================================================
 * File: EmptyChatState.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Empty states — no session yet, or a session with no messages.
 * Responsibilities:
 *   - Zero-sessions: "New Chat" call to action
 *   - Zero-messages (existing empty session): prompt to start typing
 * Dependencies:
 *   - lucide-react
 * Public Exports:
 *   - EmptyChatState
 * Database/Table: N/A
 * Related Modules: features/chat/ChatPage, ConversationPanel
 * Important Notes: N/A
 * =============================================================================
 */

import { MessageSquarePlus, Sparkles } from "lucide-react";

type Props =
  | { variant: "no-session"; onNewChat: () => void; creating?: boolean }
  | { variant: "empty-session" };

export function EmptyChatState(props: Props) {
  if (props.variant === "no-session") {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 px-6 text-center">
        <span className="flex h-14 w-14 items-center justify-center rounded-full bg-accent-primary-soft">
          <Sparkles className="h-6 w-6 text-accent-primary" aria-hidden />
        </span>
        <div>
          <p className="text-h3 font-semibold text-primary">Bắt đầu một cuộc trò chuyện</p>
          <p className="mt-1 text-body-sm text-secondary">
            Đặt câu hỏi về tài liệu trong workspace và nhận câu trả lời có trích dẫn nguồn.
          </p>
        </div>
        <button
          type="button"
          onClick={props.onNewChat}
          disabled={props.creating}
          className="inline-flex items-center gap-2 rounded-md bg-accent-primary px-4 py-2 text-body-sm font-medium text-white transition-colors hover:bg-accent-primary-hover disabled:cursor-not-allowed disabled:opacity-60"
        >
          <MessageSquarePlus className="h-4 w-4" aria-hidden />
          Bắt đầu chat mới
        </button>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
      <Sparkles className="h-6 w-6 text-tertiary" aria-hidden />
      <p className="text-body-sm text-secondary">
        Nhập câu hỏi bên dưới để bắt đầu cuộc trò chuyện này.
      </p>
    </div>
  );
}
