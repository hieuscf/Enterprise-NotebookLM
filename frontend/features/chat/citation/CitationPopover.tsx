/**
 * =============================================================================
 * File: CitationPopover.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Hover/focus source preview for an inline citation chip.
 * Responsibilities:
 *   - Show document title, page/section, snippet, verified status, CTA
 * Dependencies:
 *   - lucide-react, CitationViewModel, content-location
 * Public Exports:
 *   - CitationPopover
 * Database/Table: N/A
 * Related Modules: CitationChip
 * Important Notes: Hand-rolled popover (no Radix); Escape closes via parent.
 * =============================================================================
 */

"use client";

import { CheckCircle2, FileText, AlertCircle } from "lucide-react";

import type { CitationViewModel } from "@/features/chat/citation/citation-types";
import { formatContentLocationLabel } from "@/lib/content-location";
import { cn } from "@/lib/utils";

type Props = {
  citation: CitationViewModel;
  onOpenDocument: () => void;
  className?: string;
};

export function CitationPopover({ citation, onOpenDocument, className }: Props) {
  const locationLabel = formatContentLocationLabel(citation.location);
  const fileLabel = citation.fileType
    ? String(citation.fileType).toUpperCase()
    : "DOC";

  return (
    <div
      role="dialog"
      aria-label={`Nguồn ${citation.displayIndex}`}
      className={cn(
        "w-[min(22rem,calc(100vw-2rem))] overflow-hidden rounded-lg border border-border-default",
        "bg-surface shadow-lg",
        className,
      )}
    >
      <div className="border-b border-border-default bg-elevated/50 px-3 py-2">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-tertiary">
          Source
        </p>
        <div className="mt-1.5 flex items-start gap-2">
          <FileText className="mt-0.5 h-4 w-4 shrink-0 text-accent-primary" aria-hidden />
          <div className="min-w-0">
            <p className="truncate text-body-sm font-medium text-primary">
              {citation.documentMissing
                ? "Tài liệu không còn khả dụng"
                : citation.documentTitle}
            </p>
            <p className="text-caption text-secondary">
              {fileLabel}
              {locationLabel ? ` · ${locationLabel}` : " · Không xác định được trang nguồn"}
            </p>
          </div>
        </div>
      </div>

      <div className="max-h-40 overflow-y-auto px-3 py-2.5">
        {citation.textSnippet ? (
          <p className="text-body-sm leading-relaxed text-secondary">
            “{citation.textSnippet}”
          </p>
        ) : (
          <p className="text-body-sm italic text-tertiary">Không có đoạn trích.</p>
        )}
      </div>

      <div className="flex flex-col gap-2 border-t border-border-default px-3 py-2.5">
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
          onClick={onOpenDocument}
          disabled={citation.documentMissing || !citation.documentId}
          className="text-left text-caption font-medium text-accent-primary hover:underline disabled:cursor-not-allowed disabled:text-tertiary disabled:no-underline"
        >
          Xem trong tài liệu →
        </button>
      </div>
    </div>
  );
}
