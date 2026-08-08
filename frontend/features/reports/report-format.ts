/**
 * =============================================================================
 * File: report-format.ts
 * Module/Service: Report Service (Web App)
 * Layer: UI
 * Purpose: Pure display helpers for Report status / format / source labels.
 * Responsibilities:
 *   - Status & format labels (vi-VN); datetime formatting; source type labels
 * Dependencies:
 *   - types/reports
 * Public Exports:
 *   - reportStatusLabel, reportFormatLabel, reportSourceTypeLabel,
 *     formatReportDateTime, EXPORT_FORMAT_OPTIONS
 * Database/Table: N/A
 * Related Modules: features/reports/*
 * Important Notes: Keep pure for easy unit/smoke tests (no React).
 * =============================================================================
 */

import type {
  ReportExportFormat,
  ReportSourceType,
  ReportStatus,
} from "@/types/reports";

export const EXPORT_FORMAT_OPTIONS: ReadonlyArray<{
  value: ReportExportFormat;
  label: string;
}> = [
  { value: "pdf", label: "PDF" },
  { value: "docx", label: "DOCX (Word)" },
  { value: "markdown", label: "Markdown" },
];

export function reportStatusLabel(status: ReportStatus): string {
  switch (status) {
    case "pending":
      return "Đang xử lý";
    case "ready":
      return "Sẵn sàng";
    case "failed":
      return "Thất bại";
    default:
      return status;
  }
}

export function reportFormatLabel(format: ReportExportFormat): string {
  return (
    EXPORT_FORMAT_OPTIONS.find((o) => o.value === format)?.label ?? format
  );
}

export function reportSourceTypeLabel(type: ReportSourceType): string {
  switch (type) {
    case "summary":
      return "Tóm tắt";
    case "extraction":
      return "Trích xuất";
    case "comparison":
      return "So sánh";
    case "chat_session":
      return "Phiên chat";
    default:
      return type;
  }
}

export function formatReportDateTime(iso: string): string {
  try {
    return new Intl.DateTimeFormat("vi-VN", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}
