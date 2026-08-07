/**
 * =============================================================================
 * File: UserBubble.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Render one user chat message (FR4 §3/§11).
 * Responsibilities:
 *   - Plain-text bubble, right-aligned, preserving user line breaks
 * Dependencies:
 *   - lib/utils
 * Public Exports:
 *   - UserBubble
 * Database/Table: N/A
 * Related Modules: features/chat/ChatMessageItem
 * Important Notes: No markdown rendering for user input — shown verbatim.
 * =============================================================================
 */

import type { ChatMessage } from "@/types/chat";

type Props = {
  message: ChatMessage;
};

export function UserBubble({ message }: Props) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] rounded-lg bg-accent-primary px-4 py-2.5 text-body-sm text-white shadow-sm sm:max-w-[70%]">
        <p className="whitespace-pre-wrap break-words">{message.content}</p>
      </div>
    </div>
  );
}
