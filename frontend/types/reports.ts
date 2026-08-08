/**
 * =============================================================================
 * File: reports.ts
 * Module/Service: Report Service (Web App)
 * Layer: UI
 * Purpose: TypeScript types for Reports API matching OpenAPI (FR9 / UC8).
 * Responsibilities:
 *   - Align Report / ReportItemInput / export_format with backend schema
 * Dependencies:
 *   - docs/Enterprise_notebooklm_openapi.yaml Report / ReportItemInput
 * Public Exports:
 *   - ReportStatus, ReportExportFormat, ReportSourceType, ReportItemInput,
 *     Report, ReportCreateRequest
 * Database/Table: reports, report_items
 * Related Modules: lib/reports.api, features/reports/*
 * Important Notes: Do not invent fields; keep {source_type, source_id, order_index}.
 * =============================================================================
 */

export type ReportStatus = "pending" | "ready" | "failed";

export type ReportExportFormat = "pdf" | "docx" | "markdown";

export type ReportSourceType =
  | "summary"
  | "extraction"
  | "comparison"
  | "chat_session";

/** OpenAPI ReportItemInput — do not reshape. */
export type ReportItemInput = {
  source_type: ReportSourceType;
  source_id: string;
  order_index: number;
};

export type Report = {
  id: string;
  workspace_id: string;
  title: string;
  export_format: ReportExportFormat;
  status: ReportStatus;
  file_url: string | null;
  created_at: string;
};

export type ReportCreateRequest = {
  title: string;
  export_format: ReportExportFormat;
  items: ReportItemInput[];
};
