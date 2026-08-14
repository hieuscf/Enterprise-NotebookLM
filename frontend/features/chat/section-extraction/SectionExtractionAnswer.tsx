/**
 * =============================================================================
 * File: SectionExtractionAnswer.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Structured document-outline renderer for route_type=section_extraction.
 * Responsibilities:
 *   - Adapt answer text + citations into a heading tree
 *   - Render SectionItem tree instead of a single Markdown pass
 * Dependencies:
 *   - section-extraction-adapter, SectionItem, AnswerContent (fallback)
 * Public Exports:
 *   - SectionExtractionAnswer
 * Database/Table: N/A
 * Related Modules: AssistantBubble
 * Important Notes:
 *   - Other routes must keep using AnswerContent.
 *   - Fallback to markdown only when the adapter finds no outline.
 * =============================================================================
 */

"use client";

import { useMemo } from "react";

import { AnswerContent } from "@/features/chat/citation/AnswerContent";
import type { CitationViewModel } from "@/features/chat/citation/citation-types";
import {
  buildSectionExtractionModel,
  modelHasRenderableSections,
} from "@/features/chat/section-extraction/section-extraction-adapter";
import { SectionItem } from "@/features/chat/section-extraction/SectionItem";
import { cn } from "@/lib/utils";

type Props = {
  workspaceId: string;
  content: string;
  citations: CitationViewModel[];
  isStreaming?: boolean;
  className?: string;
};

export function SectionExtractionAnswer({
  workspaceId,
  content,
  citations,
  isStreaming = false,
  className,
}: Props) {
  const model = useMemo(
    () => buildSectionExtractionModel({ content, citations }),
    [content, citations],
  );

  if (!modelHasRenderableSections(model)) {
    return (
      <AnswerContent
        workspaceId={workspaceId}
        content={content}
        citations={citations}
        isStreaming={isStreaming}
        className={className}
      />
    );
  }

  return (
    <article
      className={cn(
        "section-extraction-answer space-y-4 text-primary",
        isStreaming && "chat-streaming-caret",
        className,
      )}
      data-renderer="section-extraction"
    >
      {model.nodes.map((node) => (
        <SectionItem key={node.key} workspaceId={workspaceId} node={node} level={1} />
      ))}
    </article>
  );
}
