/**
 * =============================================================================
 * File: ChatMessageItem.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Dispatch one ChatMessage to UserBubble or AssistantBubble (FR4 §11).
 * Responsibilities:
 *   - Keep the role branch small — no large condition trees in ConversationPanel
 * Dependencies:
 *   - features/chat/UserBubble, AssistantBubble
 * Public Exports:
 *   - ChatMessageItem
 * Database/Table: N/A
 * Related Modules: features/chat/ConversationPanel
 * Important Notes: N/A
 * =============================================================================
 */

import { AssistantBubble } from "@/features/chat/AssistantBubble";
import { UserBubble } from "@/features/chat/UserBubble";
import type { ChatMessage } from "@/types/chat";

type Props = {
  workspaceId: string;
  message: ChatMessage;
  isStreamingThis: boolean;
  isStopped: boolean;
  canRegenerate: boolean;
  onRegenerate?: () => void;
};

export function ChatMessageItem({
  workspaceId,
  message,
  isStreamingThis,
  isStopped,
  canRegenerate,
  onRegenerate,
}: Props) {
  if (message.role === "user") {
    return <UserBubble message={message} />;
  }
  return (
    <AssistantBubble
      workspaceId={workspaceId}
      message={message}
      isStreamingThis={isStreamingThis}
      isStopped={isStopped}
      canRegenerate={canRegenerate}
      onRegenerate={onRegenerate}
    />
  );
}
