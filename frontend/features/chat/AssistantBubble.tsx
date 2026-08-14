/**
 * =============================================================================
 * File: AssistantBubble.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Assistant answer as a reading surface — inline citations + source summary.
 * Responsibilities:
 *   - AnswerContent (factoid/complex) or SectionExtractionAnswer (section_extraction)
 *   - SourceSummary footer; copy / regenerate actions
 * Dependencies:
 *   - AnswerContent, SectionExtractionAnswer, SourceSummary, AgentBadge, citation-mapper
 * Public Exports:
 *   - AssistantBubble
 * Database/Table: N/A
 * Related Modules: ChatMessageItem, ChatCitationContext
 * Important Notes: Never renders tokens/cost/latency/confidence — Admin only.
 * =============================================================================
 */

"use client";

import { Bot, Check, Copy, RotateCcw } from "lucide-react";
import { useMemo, useState } from "react";

import { AgentBadge } from "@/features/chat/AgentBadge";
import { useChatCitationUiOptional } from "@/features/chat/ChatCitationContext";
import { AnswerContent } from "@/features/chat/citation/AnswerContent";
import {
  mapCitations,
  type DocumentMetaLookup,
} from "@/features/chat/citation/citation-mapper";
import { SourceSummary } from "@/features/chat/citation/SourceSummary";
import { SectionExtractionAnswer } from "@/features/chat/section-extraction/SectionExtractionAnswer";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/types/chat";

type Props = {
  workspaceId: string;
  message: ChatMessage;
  isStreamingThis: boolean;
  isStopped: boolean;
  canRegenerate: boolean;
  onRegenerate?: () => void;
  docsById: Map<string, DocumentMetaLookup>;
};

export function AssistantBubble({
  workspaceId,
  message,
  isStreamingThis,
  isStopped,
  canRegenerate,
  onRegenerate,
  docsById,
}: Props) {
  const ui = useChatCitationUiOptional();
  const [copied, setCopied] = useState(false);

  const status = message.status ?? "completed";
  const isEmpty = message.content.trim().length === 0;
  const showEmptyState = status === "completed" && isEmpty;
  const isSectionExtraction = message.generation?.route_type === "section_extraction";
  const citations = useMemo(
    () => mapCitations(message.citations ?? [], docsById),
    [message.citations, docsById],
  );

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="flex justify-start gap-3">
      <span
        className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent-primary-soft text-accent-primary"
        aria-hidden
      >
        <Bot className="h-3.5 w-3.5" />
      </span>

      <div className="min-w-0 max-w-[min(46rem,calc(100%-2.5rem))] flex-1">
        {showEmptyState ? (
          <p className="text-body-sm italic text-tertiary">Không có nội dung trả lời.</p>
        ) : isSectionExtraction ? (
          <SectionExtractionAnswer
            workspaceId={workspaceId}
            content={message.content}
            citations={citations}
            isStreaming={
              isStreamingThis || status === "streaming" || status === "pending"
            }
          />
        ) : (
          <AnswerContent
            workspaceId={workspaceId}
            content={message.content}
            citations={citations}
            isStreaming={
              isStreamingThis || status === "streaming" || status === "pending"
            }
          />
        )}

        {isStopped ? (
          <p className="mt-1 text-caption italic text-tertiary">Đã dừng tạo câu trả lời.</p>
        ) : null}

        {message.generation?.agent_triggered ? (
          <div className="mt-2">
            <AgentBadge visible />
          </div>
        ) : null}

        {!isStreamingThis && status === "completed" ? (
          <SourceSummary citations={citations} emptyHint={!isEmpty} />
        ) : null}

        {!isStreamingThis && status === "completed" && !isEmpty ? (
          <div className="mt-2 flex flex-wrap items-center gap-1">
            <button
              type="button"
              onClick={handleCopy}
              className="inline-flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-caption font-medium text-secondary hover:bg-elevated hover:text-primary"
              aria-label="Sao chép câu trả lời"
            >
              {copied ? (
                <Check className="h-3.5 w-3.5 text-success" aria-hidden />
              ) : (
                <Copy className="h-3.5 w-3.5" aria-hidden />
              )}
              {copied ? "Đã sao chép" : "Copy"}
            </button>

            {canRegenerate ? (
              <button
                type="button"
                onClick={onRegenerate}
                className="inline-flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-caption font-medium text-secondary hover:bg-elevated hover:text-primary"
              >
                <RotateCcw className="h-3.5 w-3.5" aria-hidden />
                Tạo lại
              </button>
            ) : null}

            <button
              type="button"
              onClick={() => {
                ui?.setPanelCitations(citations);
                ui?.setSourcePanelOpen(true);
                ui?.setSourcePanelMobileOpen(true);
              }}
              className={cn(
                "inline-flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1",
                "text-caption font-medium text-secondary hover:bg-elevated hover:text-primary",
                "xl:hidden",
              )}
            >
              Sources
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
