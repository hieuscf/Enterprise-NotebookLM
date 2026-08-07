/**
 * =============================================================================
 * File: AgentBadge.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Small badge shown when a Micro Agent improved the answer (FR14 §7).
 * Responsibilities:
 *   - Render fixed copy "AI đã cải thiện truy vấn" when agent_triggered=true
 * Dependencies:
 *   - lucide-react
 * Public Exports:
 *   - AgentBadge
 * Database/Table: N/A
 * Related Modules: features/chat/AssistantBubble
 * Important Notes:
 *   - The API only exposes agent_triggered (boolean) on MessageGeneration —
 *     agent_type/trigger_reason live on a separate agent-events endpoint.
 *     Per spec, do NOT call that endpoint just to label this badge; always
 *     use the generic copy. Agent Detail is reserved for the Admin Dashboard.
 * =============================================================================
 */

import { Sparkles } from "lucide-react";

type Props = {
  visible: boolean;
};

export function AgentBadge({ visible }: Props) {
  if (!visible) return null;
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full bg-accent-tertiary-soft px-2 py-0.5 text-caption font-medium text-accent-tertiary"
      title="Câu trả lời đã được cải thiện bằng một bước xử lý bổ sung"
    >
      <Sparkles className="h-3 w-3" aria-hidden />
      AI đã cải thiện truy vấn
    </span>
  );
}
