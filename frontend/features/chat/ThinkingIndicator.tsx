/**
 * =============================================================================
 * File: ThinkingIndicator.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Lightweight stream-wait indicator before the first token (FR4 §8.A).
 * Responsibilities:
 *   - Animated dots + "AI đang trả lời…" label; aria-live for screen readers
 * Dependencies:
 *   - lucide-react
 * Public Exports:
 *   - ThinkingIndicator
 * Database/Table: N/A
 * Related Modules: features/chat/ConversationPanel
 * Important Notes: Hidden once tokens flow — AnswerContent streaming caret takes over.
 * =============================================================================
 */

import { Bot } from "lucide-react";

export function ThinkingIndicator() {
  return (
    <div
      className="flex justify-start gap-3"
      aria-live="polite"
      aria-label="AI đang trả lời"
    >
      <span className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent-primary-soft text-accent-primary">
        <Bot className="h-3.5 w-3.5" aria-hidden />
      </span>
      <div className="flex items-center gap-2 py-1.5">
        <span className="text-body-sm text-secondary">AI đang trả lời…</span>
        <span className="flex items-center gap-1" aria-hidden>
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-tertiary [animation-delay:-0.3s]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-tertiary [animation-delay:-0.15s]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-tertiary" />
        </span>
      </div>
    </div>
  );
}
