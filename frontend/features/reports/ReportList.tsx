/**
 * =============================================================================
 * File: ReportList.tsx
 * Module/Service: Report Service (Web App)
 * Layer: UI
 * Purpose: Workspace report history list with download / delete actions.
 * Responsibilities:
 *   - Render GET list rows: title, format, status, created_at
 *   - Trigger download when ready; delete via callback
 * Dependencies:
 *   - report-format, lucide-react
 * Public Exports:
 *   - ReportList
 * Database/Table: N/A
 * Related Modules: ReportsView
 * Important Notes: Backend returns newest first — preserve order.
 * =============================================================================
 */

"use client";

import { Download, Loader2, Trash2 } from "lucide-react";

import {
  formatReportDateTime,
  reportFormatLabel,
  reportStatusLabel,
} from "@/features/reports/report-format";
import { cn } from "@/lib/utils";
import type { Report } from "@/types/reports";

type Props = {
  reports: Report[];
  canDelete: boolean;
  deletingId: string | null;
  downloadingId: string | null;
  onDownload: (report: Report) => void;
  onDelete: (report: Report) => void;
};

export function ReportList({
  reports,
  canDelete,
  deletingId,
  downloadingId,
  onDownload,
  onDelete,
}: Props) {
  if (reports.length === 0) {
    return (
      <p className="text-body-sm text-tertiary">Chưa có báo cáo nào trong workspace.</p>
    );
  }

  return (
    <ul className="flex flex-col gap-1.5" aria-label="Danh sách báo cáo">
      {reports.map((item) => {
        const deleting = deletingId === item.id;
        const downloading = downloadingId === item.id;
        const canDownload = item.status === "ready";

        return (
          <li
            key={item.id}
            className="flex flex-col gap-2 rounded-md border border-border-default px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between"
          >
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="truncate text-body-sm font-medium text-primary">
                  {item.title}
                </span>
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 text-caption font-semibold",
                    item.status === "ready" && "bg-success/10 text-success",
                    item.status === "pending" && "bg-warning/10 text-warning",
                    item.status === "failed" && "bg-danger-soft text-danger",
                  )}
                >
                  {reportStatusLabel(item.status)}
                </span>
              </div>
              <p className="mt-0.5 text-caption text-tertiary">
                {reportFormatLabel(item.export_format)} ·{" "}
                {formatReportDateTime(item.created_at)}
              </p>
            </div>

            <div className="flex shrink-0 items-center gap-1.5">
              <button
                type="button"
                disabled={!canDownload || downloading}
                onClick={() => onDownload(item)}
                title={
                  canDownload
                    ? "Tải xuống"
                    : "Chỉ tải được khi báo cáo sẵn sàng"
                }
                className={cn(
                  "inline-flex h-8 items-center gap-1.5 rounded-md border border-border-default px-2.5",
                  "text-caption font-medium text-secondary hover:bg-elevated",
                  "disabled:cursor-not-allowed disabled:opacity-40",
                )}
              >
                {downloading ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                ) : (
                  <Download className="h-3.5 w-3.5" aria-hidden />
                )}
                Tải
              </button>
              {canDelete ? (
                <button
                  type="button"
                  disabled={deleting}
                  onClick={() => onDelete(item)}
                  aria-label={`Xoá ${item.title}`}
                  className="inline-flex h-8 w-8 items-center justify-center rounded-md text-tertiary hover:bg-elevated hover:text-danger disabled:opacity-50"
                >
                  {deleting ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                  ) : (
                    <Trash2 className="h-3.5 w-3.5" aria-hidden />
                  )}
                </button>
              ) : null}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
