/**
 * =============================================================================
 * File: ReportPreviewExportMenu.tsx
 * Module/Service: Report Service (Web App)
 * Layer: UI
 * Purpose: Export control for a generated report (CMP-25).
 * Responsibilities:
 *   - Offer the single backend export_format chosen at create time
 *   - Disable export unless the report is ready
 * Dependencies:
 *   - report-format, lucide-react
 * Public Exports:
 *   - ReportPreviewExportMenu
 * Database/Table: N/A
 * Related Modules: ReportPreviewHeader
 * Important Notes: Do not convert formats in the browser. One format per report.
 * =============================================================================
 */

"use client";

import { Download, Loader2 } from "lucide-react";

import { reportFormatLabel } from "@/features/reports/report-format";
import { cn } from "@/lib/utils";
import type { ReportExportFormat } from "@/types/reports";

type Props = {
  format: ReportExportFormat;
  enabled: boolean;
  exporting: boolean;
  onExport: () => void;
};

export function ReportPreviewExportMenu({
  format,
  enabled,
  exporting,
  onExport,
}: Props) {
  return (
    <button
      type="button"
      disabled={!enabled || exporting}
      onClick={onExport}
      aria-label={`Xuất ${reportFormatLabel(format)}`}
      title={
        enabled
          ? `Tải file ${reportFormatLabel(format)} do hệ thống tạo`
          : "Chỉ xuất được khi báo cáo sẵn sàng"
      }
      className={cn(
        "inline-flex h-10 items-center gap-2 rounded-md border border-border-default px-3",
        "text-body-sm font-medium text-secondary hover:bg-elevated",
        "disabled:cursor-not-allowed disabled:opacity-40",
      )}
    >
      {exporting ? (
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
      ) : (
        <Download className="h-4 w-4" aria-hidden />
      )}
      {exporting ? "Đang chuẩn bị tải…" : `Xuất ${reportFormatLabel(format)}`}
    </button>
  );
}
