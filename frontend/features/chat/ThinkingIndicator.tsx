/**
 * =============================================================================
 * File: ThinkingIndicator.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: "Đang chờ token đầu tiên" loading state (FR4 §8.A).
 * Responsibilities:
 *   - Animated dots inside an assistant-shaped skeleton bubble
 *   - Screen-reader label via aria-live (spec §15 accessibility)
 * Dependencies:
 *   - None
 * Public Exports:
 *   - ThinkingIndicator
 * Database/Table: N/A
 * Related Modules: features/chat/ConversationPanel
 * Important Notes: Only shown before the first token arrives — once a token
 *   is received, the spinner disappears and streaming text takes over (§8.B).
 * =============================================================================
 */

export function ThinkingIndicator() {
  return (
    <div className="flex justify-start" aria-live="polite" aria-label="Đang soạn câu trả lời">
      <div className="flex items-center gap-1.5 rounded-lg border border-border-default bg-surface px-4 py-3 shadow-sm">
        <span className="sr-only">Đang soạn câu trả lời…</span>
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-tertiary [animation-delay:-0.3s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-tertiary [animation-delay:-0.15s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-tertiary" />
      </div>
    </div>
  );
}
