/**
 * =============================================================================
 * File: SummaryHistory.tsx
 * Module/Service: Summary Service (Web App)
 * Layer: UI
 * Purpose: List every Summary generation for a document (all styles/versions).
 * Responsibilities:
 *   - Show style, status, time, old-version badge; select history item
 * Dependencies:
 *   - summary-format helpers
 * Public Exports:
 *   - SummaryHistory
 * Database/Table: N/A
 * Related Modules: SummarySection
 * Important Notes: Backend returns created_at DESC — preserve that order.
 * =============================================================================
 */

"use client";

import {
  formatSummaryDateTime,
  isOldVersion,
  statusLabel,
  styleLabel,
} from "@/features/summaries/summary-format";
import { cn } from "@/lib/utils";
import type { Summary } from "@/types/summaries";

type Props = {
  summaries: Summary[];
  currentVersionId: string | null;
  selectedId: string | null;
  onSelect: (summary: Summary) => void;
};

export function SummaryHistory({
  summaries,
  currentVersionId,
  selectedId,
  onSelect,
}: Props) {
  if (summaries.length === 0) {
    return (
      <p className="text-body-sm text-tertiary">Chưa có lịch sử tóm tắt.</p>
    );
  }

  return (
    <ul className="flex flex-col gap-1.5" aria-label="Lịch sử tóm tắt">
      {summaries.map((item) => {
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
                  {styleLabel(item.style)}
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
                {formatSummaryDateTime(item.created_at)}
                <span className="sr-only">
                  {old
                    ? ", tóm tắt dựa trên phiên bản tài liệu cũ"
                    : ", tóm tắt của phiên bản hiện tại"}
                </span>
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
