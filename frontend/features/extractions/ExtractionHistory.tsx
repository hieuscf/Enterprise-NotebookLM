/**
 * =============================================================================
 * File: ExtractionHistory.tsx
 * Module/Service: Extraction Service (Web App)
 * Layer: UI
 * Purpose: List every Extraction generation (all types/formats/versions).
 * Responsibilities:
 *   - Show type, format, status, time, old-version badge; select history item
 * Dependencies:
 *   - extraction-format helpers
 * Public Exports:
 *   - ExtractionHistory
 * Database/Table: N/A
 * Related Modules: ExtractionSection
 * Important Notes: Backend returns created_at DESC — preserve that order.
 * =============================================================================
 */

"use client";

import {
  formatExtractionDateTime,
  formatLabel,
  isOldVersion,
  statusLabel,
  typeLabel,
} from "@/features/extractions/extraction-format";
import { cn } from "@/lib/utils";
import type { Extraction } from "@/types/extractions";

type Props = {
  extractions: Extraction[];
  currentVersionId: string | null;
  selectedId: string | null;
  onSelect: (extraction: Extraction) => void;
};

export function ExtractionHistory({
  extractions,
  currentVersionId,
  selectedId,
  onSelect,
}: Props) {
  if (extractions.length === 0) {
    return (
      <p className="text-body-sm text-tertiary">Chưa có lịch sử trích xuất.</p>
    );
  }

  return (
    <ul className="flex flex-col gap-1.5" aria-label="Lịch sử trích xuất">
      {extractions.map((item) => {
        const old = isOldVersion(item, currentVersionId);
        const selected = item.id === selectedId;
        return (
          <li key={item.id}>
            <button
              type="button"
              onClick={() => onSelect(item)}
              className={cn(
                "flex w-full flex-col gap-0.5 rounded-md border px-3 py-2 text-left transition-colors",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40",
                selected
                  ? "border-accent-primary/40 bg-accent-primary/5"
                  : "border-border-default hover:bg-elevated",
              )}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-body-sm font-medium text-primary">
                  {typeLabel(item.extraction_type)} · {formatLabel(item.output_format)}
                </span>
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 text-caption font-semibold",
                    item.status === "completed" && "bg-success/10 text-success",
                    item.status === "processing" && "bg-warning/10 text-warning",
                    item.status === "failed" && "bg-danger-soft text-danger",
                  )}
                >
                  {statusLabel(item.status)}
                </span>
                {old ? (
                  <span className="rounded-full bg-elevated px-2 py-0.5 text-caption text-secondary">
                    Dựa trên phiên bản cũ
                  </span>
                ) : (
                  <span className="rounded-full bg-accent-primary/10 px-2 py-0.5 text-caption font-medium text-accent-primary">
                    Phiên bản hiện tại
                  </span>
                )}
              </div>
              <span className="text-caption text-tertiary">
                {formatExtractionDateTime(item.created_at)}
                <span className="sr-only">
                  {old
                    ? ", trích xuất dựa trên phiên bản tài liệu cũ"
                    : ", trích xuất của phiên bản hiện tại"}
                </span>
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
