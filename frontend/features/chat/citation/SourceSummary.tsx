/**
 * =============================================================================
 * File: SourceSummary.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Compact answer footer — sources grouped by document (not raw list).
 * Responsibilities:
 *   - Show "Sources · N" and per-document citation counts
 *   - Open source panel on click
 * Dependencies:
 *   - groupCitationsByDocument, ChatCitationContext
 * Public Exports:
 *   - SourceSummary
 * Database/Table: N/A
 * Related Modules: AssistantBubble
 * Important Notes: Replaces the old "NGUỒN TRÍCH DẪN" list under the answer.
 * =============================================================================
 */

"use client";

import { FileText } from "lucide-react";

import { useChatCitationUiOptional } from "@/features/chat/ChatCitationContext";
import { groupCitationsByDocument } from "@/features/chat/citation/citation-mapper";
import type { CitationViewModel } from "@/features/chat/citation/citation-types";
import { cn } from "@/lib/utils";

type Props = {
  citations: CitationViewModel[];
  emptyHint?: boolean;
};

export function SourceSummary({ citations, emptyHint = false }: Props) {
  const ui = useChatCitationUiOptional();
  const groups = groupCitationsByDocument(citations);

  if (citations.length === 0) {
    if (!emptyHint) return null;
    return (
      <p className="mt-3 text-caption text-tertiary">
        Không tìm thấy nguồn xác thực trong tài liệu.
      </p>
    );
  }

  return (
    <div className="mt-3 border-t border-border-default/80 pt-2.5">
      <button
        type="button"
        onClick={() => {
          ui?.setPanelCitations(citations);
          ui?.setSourcePanelOpen(true);
          ui?.setSourcePanelMobileOpen(true);
        }}
        className="text-caption font-semibold uppercase tracking-wide text-tertiary hover:text-secondary"
        aria-label={`Mở bảng nguồn, ${citations.length} nguồn`}
      >
        Sources · {citations.length}
      </button>

      <ul className="mt-1.5 flex flex-wrap gap-1.5">
        {groups.map((group) => (
          <li key={group.documentId || group.documentTitle}>
            <button
              type="button"
              onClick={() => {
                ui?.setPanelCitations(citations);
                const first = group.citations[0];
                if (first) ui?.activateCitation(first, { openPanel: true });
                else {
                  ui?.setSourcePanelOpen(true);
                  ui?.setSourcePanelMobileOpen(true);
                }
              }}
              className={cn(
                "inline-flex max-w-full items-center gap-1.5 rounded-md border border-border-default",
                "bg-elevated/40 px-2 py-1 text-caption text-secondary transition-colors",
                "hover:border-accent-primary/30 hover:bg-accent-primary-soft hover:text-accent-primary",
              )}
              aria-label={`${group.documentTitle}, ${group.citations.length} trích dẫn`}
            >
              <FileText className="h-3 w-3 shrink-0" aria-hidden />
              <span className="truncate">{group.documentTitle}</span>
              <span className="shrink-0 text-tertiary">
                · {group.citations.length}{" "}
                {group.citations.length === 1 ? "citation" : "citations"}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
