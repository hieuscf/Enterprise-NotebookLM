/**
 * =============================================================================
 * File: AssistantBubble.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Render one assistant chat message — markdown answer, agent badge,
 *          citations, and regenerate/stopped affordances (FR4 §6/§7/§11).
 * Responsibilities:
 *   - Markdown-render `content` (GFM) — never raw HTML (react-markdown default
 *     AST rendering, no dangerouslySetInnerHTML, so this stays XSS-safe)
 *   - Show AgentBadge when generation.agent_triggered
 *   - Show CitationSection once citations have arrived
 *   - Show a streaming caret while this specific message is still streaming
 *   - Offer "Tạo lại câu trả lời" on the latest completed assistant message
 * Dependencies:
 *   - react-markdown, remark-gfm, features/chat/AgentBadge, CitationSection
 * Public Exports:
 *   - AssistantBubble
 * Database/Table: N/A
 * Related Modules: features/chat/ChatMessageItem, hooks/useChatStream
 * Important Notes: Never renders tokens/cost/latency/confidence — those are
 *   Admin Dashboard data only (spec §18).
 * =============================================================================
 */

import { RotateCcw } from "lucide-react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { AgentBadge } from "@/features/chat/AgentBadge";
import { CitationSection } from "@/features/chat/CitationSection";
import { stripLeakedCitationUuids } from "@/features/chat/chat-format";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/types/chat";

type Props = {
  workspaceId: string;
  message: ChatMessage;
  isStreamingThis: boolean;
  isStopped: boolean;
  canRegenerate: boolean;
  onRegenerate?: () => void;
};

export function AssistantBubble({
  workspaceId,
  message,
  isStreamingThis,
  isStopped,
  canRegenerate,
  onRegenerate,
}: Props) {
  // History rows have no status → treat as completed. Never show the empty
  // state while pending/streaming/failed (failed uses the stream error banner).
  const status = message.status ?? "completed";
  const isEmpty = message.content.trim().length === 0;
  const showEmptyState = status === "completed" && isEmpty;

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] rounded-lg border border-border-default bg-surface px-4 py-2.5 shadow-sm sm:max-w-[75%]">
        {showEmptyState ? (
          <p className="text-body-sm italic text-tertiary">Không có nội dung trả lời.</p>
        ) : (
          <div
            className={cn(
              "prose-chat text-body-sm text-primary",
              (isStreamingThis || status === "streaming" || status === "pending") &&
                "chat-streaming-caret",
            )}
          >
            <Markdown remarkPlugins={[remarkGfm]}>
              {stripLeakedCitationUuids(message.content)}
            </Markdown>
          </div>
        )}

        {isStopped ? (
          <p className="mt-1 text-caption italic text-tertiary">Đã dừng tạo câu trả lời.</p>
        ) : null}

        {message.generation?.agent_triggered ? (
          <div className="mt-2">
            <AgentBadge visible />
          </div>
        ) : null}

        <CitationSection workspaceId={workspaceId} citations={message.citations} />

        {canRegenerate && !isStreamingThis ? (
          <button
            type="button"
            onClick={onRegenerate}
            className="mt-2 inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-caption font-medium text-secondary hover:bg-elevated hover:text-primary"
          >
            <RotateCcw className="h-3.5 w-3.5" aria-hidden />
            Tạo lại câu trả lời
          </button>
        ) : null}
      </div>
    </div>
  );
}
