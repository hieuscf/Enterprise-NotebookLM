/**
 * =============================================================================
 * File: SourceDocumentCard.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: One document group in the Source Panel with nested citation rows.
 * Responsibilities:
 *   - Show title, file type, pages, citation count; select citation on click
 * Dependencies:
 *   - SourceDocumentGroup, content-location
 * Public Exports:
 *   - SourceDocumentCard
 * Database/Table: N/A
 * Related Modules: SourcePanel
 * Important Notes: Citations are grouped by document — never a flat [1][2][3] list.
 * =============================================================================
 */

"use client";

import { FileText } from "lucide-react";

import type {
  CitationViewModel,
  SourceDocumentGroup,
} from "@/features/chat/citation/citation-types";
import { formatContentLocationLabel } from "@/lib/content-location";
import { cn } from "@/lib/utils";

type Props = {
  group: SourceDocumentGroup;
  activeCitationId: string | null;
  highlightedCitationId: string | null;
  onSelectCitation: (citation: CitationViewModel) => void;
  onHoverCitation: (citationId: string | null) => void;
};

export function SourceDocumentCard({
  group,
  activeCitationId,
  highlightedCitationId,
  onSelectCitation,
  onHoverCitation,
}: Props) {
  const pageSummary =
    group.pages.length > 0
      ? `Trang ${group.pages.join(", ")}`
      : group.citations.some((c) => c.sectionIndex != null)
        ? "Theo mục"
        : "Trang không xác định";

  const isGroupActive = group.citations.some(
    (c) => c.id === activeCitationId || c.id === highlightedCitationId,
  );

  return (
    <article
      className={cn(
        "rounded-lg border transition-colors",
        isGroupActive
          ? "border-accent-primary/40 bg-accent-primary-soft/40"
          : "border-border-default bg-surface hover:border-border-strong",
      )}
    >
      <header className="flex items-start gap-2 px-3 py-2.5">
        <FileText className="mt-0.5 h-4 w-4 shrink-0 text-accent-primary" aria-hidden />
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <p className="truncate text-body-sm font-medium text-primary">
              {group.documentMissing ? "Tài liệu không còn khả dụng" : group.documentTitle}
            </p>
            <span className="shrink-0 rounded-full bg-elevated px-1.5 py-0.5 text-[10px] font-semibold text-secondary">
              {group.citations.length}
            </span>
          </div>
          <p className="text-caption text-secondary">
            {group.fileType ? String(group.fileType).toUpperCase() : "DOC"} · {pageSummary}
          </p>
        </div>
      </header>

      <ul className="border-t border-border-default/80 px-1.5 py-1.5">
        {group.citations.map((citation) => {
          const loc = formatContentLocationLabel(citation.location) ?? "Không rõ trang";
          const active =
            citation.id === activeCitationId || citation.id === highlightedCitationId;
          return (
            <li key={citation.id}>
              <button
                type="button"
                onClick={() => onSelectCitation(citation)}
                onMouseEnter={() => onHoverCitation(citation.id)}
                onMouseLeave={() => onHoverCitation(null)}
                aria-label={`Nguồn ${citation.displayIndex}, ${group.documentTitle}, ${loc}`}
                aria-current={citation.id === activeCitationId ? "true" : undefined}
                className={cn(
                  "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors",
                  active
                    ? "bg-accent-primary-soft text-accent-primary"
                    : "text-secondary hover:bg-elevated hover:text-primary",
                )}
              >
                <span
                  className={cn(
                    "flex h-5 min-w-5 items-center justify-center rounded px-1 text-[11px] font-semibold",
                    citation.verified
                      ? "bg-citation-soft text-citation"
                      : "bg-elevated text-tertiary",
                  )}
                >
                  [{citation.displayIndex}]
                </span>
                <span className="truncate text-caption">{loc}</span>
                {citation.verified ? (
                  <span className="ml-auto text-[10px] text-success" aria-hidden>
                    ✓
                  </span>
                ) : null}
              </button>
            </li>
          );
        })}
      </ul>
    </article>
  );
}
