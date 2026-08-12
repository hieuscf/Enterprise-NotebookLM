/**
 * =============================================================================
 * File: MessageInput.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Sticky research-workspace composer — document context + send/stop.
 * Responsibilities:
 *   - Auto-resize textarea; Enter=send, Shift+Enter=newline
 *   - DocumentContextBar above input; floating composer chrome
 * Dependencies:
 *   - DocumentContextBar, lucide-react
 * Public Exports:
 *   - MessageInput
 * Database/Table: N/A
 * Related Modules: features/chat/ChatLayout, hooks/useChatStream
 * Important Notes: Business logic (send/stop) lives in the caller.
 * =============================================================================
 */

"use client";

import { Loader2, Send, Square } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  DocumentContextBar,
  type ContextDocument,
} from "@/features/chat/DocumentContextBar";
import { cn } from "@/lib/utils";
import type { Document } from "@/types/documents";

const MAX_HEIGHT_PX = 160;

type Props = {
  workspaceId: string;
  disabled?: boolean;
  isStreaming: boolean;
  onSend: (content: string) => void;
  onStop: () => void;
  usedDocuments?: ContextDocument[];
  workspaceDocuments?: Document[];
};

export function MessageInput({
  workspaceId,
  disabled,
  isStreaming,
  onSend,
  onStop,
  usedDocuments = [],
  workspaceDocuments = [],
}: Props) {
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
    <div className="sticky bottom-0 z-10 border-t border-border-default/80 bg-base/95 px-3 py-3 backdrop-blur-sm sm:px-4">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-2">
        <DocumentContextBar
          workspaceId={workspaceId}
          usedDocuments={usedDocuments}
          workspaceDocuments={workspaceDocuments}
        />

        <div
          className={cn(
            "flex items-end gap-2 rounded-xl border border-border-default bg-surface p-2 shadow-sm",
            "focus-within:border-accent-primary/40 focus-within:ring-2 focus-within:ring-accent-primary/15",
          )}
        >
          <textarea
            ref={textareaRef}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            rows={1}
            aria-label="Nhập câu hỏi"
            placeholder="Đặt câu hỏi về tài liệu trong workspace..."
            className={cn(
              "min-h-[44px] flex-1 resize-none bg-transparent px-2 py-2",
              "text-body-sm text-primary placeholder:text-tertiary",
              "focus:outline-none",
              "disabled:cursor-not-allowed disabled:opacity-60",
            )}
          />

          {isStreaming ? (
            <button
              type="button"
              onClick={onStop}
              aria-label="Dừng tạo câu trả lời"
              className="flex h-10 w-10 shrink-0 cursor-pointer items-center justify-center rounded-lg bg-elevated text-secondary transition-colors hover:bg-danger-soft hover:text-danger"
            >
              <Square className="h-4 w-4" aria-hidden />
            </button>
          ) : (
            <button
              type="button"
              onClick={handleSend}
              disabled={!canSend}
              aria-label="Gửi câu hỏi"
              className={cn(
                "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-white transition-colors",
                canSend
                  ? "cursor-pointer bg-accent-primary hover:bg-accent-primary-hover"
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

        <p className="px-1 text-[11px] text-tertiary">
          Enter để gửi · Shift+Enter để xuống dòng
        </p>
      </div>
    </div>
  );
}
