/**
 * =============================================================================
 * File: ComparisonHistory.tsx
 * Module/Service: Comparison Service (Web App)
 * Layer: UI
 * Purpose: Workspace comparison history list with select + delete actions.
 * Responsibilities:
 *   - Render GET list items; highlight selected; confirm-ready delete callback
 * Dependencies:
 *   - comparison-format, lucide-react
 * Public Exports:
 *   - ComparisonHistory
 * Database/Table: N/A
 * Related Modules: ComparisonsView
 * Important Notes: Backend returns newest first — preserve order.
 * =============================================================================
 */

"use client";

import { Loader2, Trash2 } from "lucide-react";

import {
  formatComparisonDateTime,
  statusLabel,
} from "@/features/comparisons/comparison-format";
import { cn } from "@/lib/utils";
import type { Comparison } from "@/types/comparisons";

type Props = {
  comparisons: Comparison[];
  selectedId: string | null;
  canDelete: boolean;
  deletingId: string | null;
  documentTitles?: Record<string, string>;
  onSelect: (comparison: Comparison) => void;
  onDelete: (comparison: Comparison) => void;
};

export function ComparisonHistory({
  comparisons,
  selectedId,
  canDelete,
  deletingId,
  documentTitles = {},
  onSelect,
  onDelete,
}: Props) {
  if (comparisons.length === 0) {
    return (
      <p className="text-body-sm text-tertiary">Chưa có lịch sử so sánh.</p>
    );
  }

  return (
    <ul className="flex flex-col gap-1.5" aria-label="Lịch sử so sánh">
      {comparisons.map((item) => {
        const selected = item.id === selectedId;
        const titles = item.document_ids
          .map((id) => documentTitles[id] ?? id.slice(0, 8))
          .slice(0, 3)
          .join(" · ");
        const more =
          item.document_ids.length > 3
            ? ` (+${item.document_ids.length - 3})`
            : "";
        const deleting = deletingId === item.id;

        return (
          <li key={item.id} className="flex items-stretch gap-1.5">
            <button
              type="button"
              onClick={() => onSelect(item)}
              className={cn(
                "flex min-w-0 flex-1 flex-col gap-0.5 rounded-md border px-3 py-2 text-left transition-colors",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40",
                selected
                  ? "border-accent-primary/40 bg-accent-primary/5"
                  : "border-border-default hover:bg-elevated",
              )}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="truncate text-body-sm font-medium text-primary">
                  {titles}
                  {more}
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
              </div>
              <span className="text-caption text-tertiary">
                {formatComparisonDateTime(item.created_at)} ·{" "}
                {item.document_ids.length} tài liệu
              </span>
            </button>
            {canDelete ? (
              <button
                type="button"
                onClick={() => onDelete(item)}
                disabled={deleting}
                aria-label="Xoá so sánh"
                title="Xoá so sánh"
                className={cn(
                  "flex h-auto w-10 shrink-0 items-center justify-center rounded-md border border-border-default",
                  "text-tertiary transition-colors hover:border-danger/40 hover:bg-danger-soft hover:text-danger",
                  "disabled:opacity-50",
                )}
              >
                {deleting ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                ) : (
                  <Trash2 className="h-4 w-4" aria-hidden />
                )}
              </button>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
