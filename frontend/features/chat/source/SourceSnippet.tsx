/**
 * =============================================================================
 * File: SourceSnippet.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Preview panel for the active citation snippet.
 * Responsibilities:
 *   - Show document meta, snippet, verification, open-document CTA
 * Dependencies:
 *   - CitationViewModel, content-location
 * Public Exports:
 *   - SourceSnippet
 * Database/Table: N/A
 * Related Modules: SourcePanel
 * Important Notes: N/A
 * =============================================================================
 */

"use client";

import { AlertCircle, CheckCircle2, ExternalLink, FileText } from "lucide-react";

import type { CitationViewModel } from "@/features/chat/citation/citation-types";
import { formatContentLocationLabel } from "@/lib/content-location";
import { cn } from "@/lib/utils";

type Props = {
  citation: CitationViewModel | null;
  onOpenDocument: (citation: CitationViewModel) => void;
  className?: string;
};

export function SourceSnippet({ citation, onOpenDocument, className }: Props) {
  if (!citation) {
    return (
      <div className={cn("rounded-lg border border-dashed border-border-default p-4", className)}>
        <p className="text-caption text-tertiary">
          Hover hoặc chọn một citation để xem đoạn nguồn.
        </p>
      </div>
    );
  }

  const locationLabel = formatContentLocationLabel(citation.location);

  return (
    <div
      className={cn(
        "flex flex-col gap-3 rounded-lg border border-border-default bg-elevated/30 p-3",
        className,
      )}
    >
      <div className="flex items-start gap-2">
        <FileText className="mt-0.5 h-4 w-4 shrink-0 text-accent-primary" aria-hidden />
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-tertiary">
            Source [{citation.displayIndex}]
          </p>
          <p className="truncate text-body-sm font-medium text-primary">
            {citation.documentMissing
              ? "Tài liệu không còn khả dụng"
              : citation.documentTitle}
          </p>
          <p className="text-caption text-secondary">
            {citation.fileType ? String(citation.fileType).toUpperCase() : "DOC"}
            {locationLabel ? ` · ${locationLabel}` : " · Không xác định được trang nguồn"}
          </p>
        </div>
      </div>

      <div className="max-h-48 overflow-y-auto rounded-md bg-surface px-3 py-2 shadow-xs">
        {citation.textSnippet ? (
          <p className="text-body-sm leading-relaxed text-secondary">
            “{citation.textSnippet}”
          </p>
        ) : (
          <p className="text-body-sm italic text-tertiary">Không có đoạn trích.</p>
        )}
      </div>

      <div className="flex items-center gap-1.5 text-caption">
        {citation.verified ? (
          <>
            <CheckCircle2 className="h-3.5 w-3.5 text-success" aria-hidden />
            <span className="text-success">Citation verified</span>
          </>
        ) : (
          <>
            <AlertCircle className="h-3.5 w-3.5 text-warning" aria-hidden />
            <span className="text-warning">Không thể xác minh nguồn này.</span>
          </>
        )}
      </div>

      <button
        type="button"
        onClick={() => onOpenDocument(citation)}
        disabled={citation.documentMissing || !citation.documentId}
        className={cn(
          "inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-2",
          "text-caption font-medium transition-colors",
          citation.documentMissing || !citation.documentId
            ? "cursor-not-allowed bg-elevated text-tertiary"
            : "bg-accent-primary text-white hover:bg-accent-primary-hover",
        )}
        aria-label={`Xem citation ${citation.displayIndex} trong tài liệu`}
      >
        <ExternalLink className="h-3.5 w-3.5" aria-hidden />
        Xem trong tài liệu
      </button>
    </div>
  );
}
