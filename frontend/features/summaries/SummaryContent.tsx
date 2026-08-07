/**
 * =============================================================================
 * File: SummaryContent.tsx
 * Module/Service: Summary Service (Web App)
 * Layer: UI
 * Purpose: Render completed Summary by style (short/detailed/bullets/topics).
 * Responsibilities:
 *   - Paragraph / markdown / list / topic-section presentation
 * Dependencies:
 *   - react-markdown, remark-gfm (same as Chat AssistantBubble)
 * Public Exports:
 *   - SummaryContent
 * Database/Table: N/A
 * Related Modules: SummarySection
 * Important Notes: by_topic uses backend sections only — no FE topic clustering.
 *   bullet_points uses GFM markdown lists from content (contract: markdown list).
 * =============================================================================
 */

"use client";

import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";
import type { Summary } from "@/types/summaries";

type Props = {
  summary: Summary;
  className?: string;
};

export function SummaryContent({ summary, className }: Props) {
  if (summary.style === "by_topic") {
    const sections = summary.sections ?? [];
    if (sections.length === 0) {
      return (
        <p className="text-body-sm italic text-tertiary">
          Không có nhóm chủ đề để hiển thị.
        </p>
      );
    }
    return (
      <div className={cn("flex flex-col gap-4", className)}>
        {sections.map((section, idx) => (
          <article key={`${section.topic_id ?? "t"}-${idx}`} className="flex flex-col gap-1.5">
            <h4 className="text-body-sm font-semibold text-primary">{section.title}</h4>
            <div className="prose-chat text-body-sm text-primary">
              <Markdown remarkPlugins={[remarkGfm]}>{section.content}</Markdown>
            </div>
          </article>
        ))}
      </div>
    );
  }

  const text = (summary.content ?? "").trim();
  if (!text) {
    return <p className="text-body-sm italic text-tertiary">Không có nội dung tóm tắt.</p>;
  }

  return (
    <div
      className={cn(
        "prose-chat text-body-sm leading-relaxed text-primary",
        className,
      )}
    >
      <Markdown remarkPlugins={[remarkGfm]}>{text}</Markdown>
    </div>
  );
}
