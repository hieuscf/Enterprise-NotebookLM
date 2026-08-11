/**
 * =============================================================================
 * File: CitationSection.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Render the citation list below an assistant message (FR5 reuse).
 * Responsibilities:
 *   - List citations in order_index order with verified state + snippet
 *   - Reuse CitationLocationLabel (FR5) — no new citation UI is introduced
 *   - Deep-link to the source document (document-level; Chat's Citation has
 *     no chunk_id/location, unlike Search results)
 * Dependencies:
 *   - features/citation/CitationLocationLabel, features/chat/chat-format
 * Public Exports:
 *   - CitationSection
 * Database/Table: N/A
 * Related Modules: features/chat/AssistantBubble
 * Important Notes: Never blocks the answer — only rendered once citations
 *   have arrived (after the "citations" SSE frame or from message history).
 * =============================================================================
 */

import { FileText, ShieldCheck, ShieldQuestion } from "lucide-react";
import Link from "next/link";

import { buildChatCitationHref, citationDisplayIndex } from "@/features/chat/chat-format";
import { CitationLocationLabel } from "@/features/citation/CitationLocationLabel";
import { cn } from "@/lib/utils";
import type { Citation } from "@/types/citations";

type Props = {
  workspaceId: string;
  citations: Citation[];
};

export function CitationSection({ workspaceId, citations }: Props) {
  if (citations.length === 0) return null;

  const sorted = [...citations].sort((a, b) => a.order_index - b.order_index);

  return (
    <div className="mt-3 border-t border-border-default pt-2">
      <p className="text-caption font-semibold uppercase tracking-wide text-tertiary">
        Nguồn trích dẫn
      </p>
      <ul className="mt-1.5 flex flex-col gap-1.5">
        {sorted.map((citation) => {
          const href = buildChatCitationHref(workspaceId, citation);
          const displayIndex = citationDisplayIndex(citation);
          const content = (
            <>
              <span
                className={cn(
                  "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold",
                  citation.verified
                    ? "bg-success/10 text-success"
                    : "bg-elevated text-tertiary",
                )}
                title={citation.verified ? "Đã xác thực" : "Chưa xác thực"}
              >
                {citation.verified ? (
                  <ShieldCheck className="h-3 w-3" aria-hidden />
                ) : (
                  <ShieldQuestion className="h-3 w-3" aria-hidden />
                )}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-caption font-medium text-secondary">
                  <FileText className="mr-1 inline h-3 w-3 text-tertiary" aria-hidden />
                  [{displayIndex}] Trích dẫn {displayIndex}
                  <CitationLocationLabel
                    location={citation.location}
                    className="ml-1 text-caption text-citation"
                  />
                </span>
                <span className="block text-body-sm text-secondary">
                  “{citation.text_snippet}”
                </span>
              </span>
            </>
          );

          return (
            <li key={citation.id} className="flex items-start gap-2 rounded-md px-2 py-1.5 hover:bg-elevated/60">
              {href ? (
                <Link href={href} className="flex flex-1 items-start gap-2">
                  {content}
                </Link>
              ) : (
                <div className="flex flex-1 items-start gap-2">{content}</div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
