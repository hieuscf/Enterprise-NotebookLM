/**
 * =============================================================================
 * File: AnswerContent.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Markdown answer with interactive inline citation chips.
 * Responsibilities:
 *   - Render GFM markdown; inject CitationChip for known [n] markers
 *   - Strip leaked UUID markers; streaming caret support
 * Dependencies:
 *   - react-markdown, remark-gfm, injectCitationNodes, chat-format
 * Public Exports:
 *   - AnswerContent
 * Database/Table: N/A
 * Related Modules: AssistantMessage / AssistantBubble
 * Important Notes: Citations may arrive after tokens — chips appear when mapped.
 * =============================================================================
 */

"use client";

import { useMemo, type ReactNode } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { stripLeakedCitationUuids } from "@/features/chat/chat-format";
import type { CitationViewModel } from "@/features/chat/citation/citation-types";
import { injectCitationNodes } from "@/features/chat/citation/injectCitationNodes";
import { cn } from "@/lib/utils";

type Props = {
  workspaceId: string;
  content: string;
  citations: CitationViewModel[];
  isStreaming?: boolean;
  className?: string;
};

export function AnswerContent({
  workspaceId,
  content,
  citations,
  isStreaming = false,
  className,
}: Props) {
  const byDisplayIndex = useMemo(() => {
    const map = new Map<number, CitationViewModel>();
    for (const c of citations) map.set(c.displayIndex, c);
    return map;
  }, [citations]);

  const components = useMemo(() => {
    const wrap =
      (Tag: "p" | "li" | "td" | "th" | "blockquote") =>
      ({ children }: { children?: ReactNode }) => {
        const Comp = Tag;
        return (
          <Comp>{injectCitationNodes(children, workspaceId, byDisplayIndex)}</Comp>
        );
      };

    return {
      p: wrap("p"),
      li: wrap("li"),
      td: wrap("td"),
      th: wrap("th"),
      blockquote: wrap("blockquote"),
    };
  }, [workspaceId, byDisplayIndex]);

  return (
    <div
      className={cn(
        "prose-chat text-body-sm text-primary",
        isStreaming && "chat-streaming-caret",
        className,
      )}
    >
      <Markdown remarkPlugins={[remarkGfm]} components={components}>
        {stripLeakedCitationUuids(content)}
      </Markdown>
    </div>
  );
}
