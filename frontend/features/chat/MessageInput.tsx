/**
 * =============================================================================
 * File: MessageInput.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Multi-line chat composer — Enter=send, Shift+Enter=newline (FR4 §4).
 * Responsibilities:
 *   - Auto-resize textarea up to a max height
 *   - Disable Send when empty or sending; show Stop while streaming (§5 UX add)
 *   - Refocus the textarea after a message is sent (spec §15 accessibility)
 * Dependencies:
 *   - lucide-react
 * Public Exports:
 *   - MessageInput
 * Database/Table: N/A
 * Related Modules: features/chat/ChatLayout, hooks/useChatStream
 * Important Notes: Business logic (send/stop) lives in the caller — this
 *   component only owns the draft text + keyboard/resize behavior.
 * =============================================================================
 */

"use client";

import { Loader2, Send, Square } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

const MAX_HEIGHT_PX = 200;

type Props = {
  disabled?: boolean;
  isStreaming: boolean;
  onSend: (content: string) => void;
  onStop: () => void;
};

export function MessageInput({ disabled, isStreaming, onSend, onStop }: Props) {
  const [draft, setDraft] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const resize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT_PX)}px`;
  }, []);

  useEffect(() => {
    resize();
  }, [draft, resize]);

  const canSend = draft.trim().length > 0 && !isStreaming && !disabled;

  const handleSend = useCallback(() => {
    const content = draft.trim();
    if (!content || isStreaming || disabled) return;
    onSend(content);
    setDraft("");
    // Refocus after the state update commits (spec §15 — keyboard friendly).
    requestAnimationFrame(() => textareaRef.current?.focus());
  }, [draft, isStreaming, disabled, onSend]);

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  return (
    <div className="flex items-end gap-2 border-t border-border-default bg-surface p-3 sm:p-4">
      <textarea
        ref={textareaRef}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        rows={1}
        aria-label="Nhập câu hỏi"
        placeholder="Đặt câu hỏi về tài liệu trong workspace… (Enter để gửi, Shift+Enter để xuống dòng)"
        className={cn(
          "min-h-[44px] flex-1 resize-none rounded-md border border-border-default bg-base px-3 py-2.5",
          "text-body-sm text-primary placeholder:text-tertiary",
          "focus:outline-none focus:ring-2 focus:ring-accent-primary/25",
          "disabled:cursor-not-allowed disabled:opacity-60",
        )}
      />

      {isStreaming ? (
        <button
          type="button"
          onClick={onStop}
          aria-label="Dừng tạo câu trả lời"
          title="Dừng tạo câu trả lời"
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-elevated text-secondary transition-colors hover:bg-danger-soft hover:text-danger"
        >
          <Square className="h-4 w-4" aria-hidden />
        </button>
      ) : (
        <button
          type="button"
          onClick={handleSend}
          disabled={!canSend}
          aria-label="Gửi câu hỏi"
          title="Gửi câu hỏi"
          className={cn(
            "flex h-10 w-10 shrink-0 items-center justify-center rounded-md text-white transition-colors",
            canSend
              ? "bg-accent-primary hover:bg-accent-primary-hover"
              : "cursor-not-allowed bg-tertiary/50",
          )}
        >
          {disabled ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          ) : (
            <Send className="h-4 w-4" aria-hidden />
          )}
        </button>
      )}
    </div>
  );
}
