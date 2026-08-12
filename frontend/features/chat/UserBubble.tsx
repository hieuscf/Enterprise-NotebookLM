/**
 * =============================================================================
 * File: UserBubble.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Render one user chat message in research-workspace style.
 * Responsibilities:
 *   - Plain-text, right-aligned question with clear visual hierarchy
 * Dependencies:
 *   - types/chat
 * Public Exports:
 *   - UserBubble
 * Database/Table: N/A
 * Related Modules: features/chat/ChatMessageItem
 * Important Notes: No markdown for user input — shown verbatim.
 * =============================================================================
 */

import type { ChatMessage } from "@/types/chat";

type Props = {
  message: ChatMessage;
};

export function UserBubble({ message }: Props) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[min(42rem,92%)] rounded-2xl rounded-br-md bg-accent-primary px-4 py-3 text-body-sm leading-relaxed text-white shadow-xs">
        <p className="whitespace-pre-wrap break-words">{message.content}</p>
      </div>
    </div>
  );
}
