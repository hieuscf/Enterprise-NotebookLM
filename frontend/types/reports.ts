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
 *     Report, ReportCreateRequest, ReportPreview*
 * Database/Table: reports, report_items
 * Related Modules: lib/reports.api, features/reports/*
 * Important Notes: Do not invent fields; keep {source_type, source_id, order_index}.
 *   preview is GET-detail only (CMP-25). Never treat export binary as preview.
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

/** CMP-24 structured comparison payload attached on GET detail. */
export type ReportPreviewDocument = {
  side?: string | null;
  title?: string | null;
  document_id?: string | null;
  document_version_id?: string | null;
};

export type ReportPreviewClauseSummary = {
  clause_id?: string | null;
  display_id?: string | null;
  status?: string | null;
  risk_level?: string | null;
  risk_category?: string | null;
  change?: string | null;
};

export type ReportPreviewExactDifference = {
  label?: string | null;
  old?: string | null;
  new?: string | null;
  delta?: string | null;
  percent?: string | null;
  context?: string | null;
};

export type ReportPreviewEvidence = {
  side?: string | null;
  document_title?: string | null;
  document_id?: string | null;
  document_version_id?: string | null;
  clause_id?: string | null;
  page_number?: number | null;
  chunk_id?: string | null;
  display_text?: string | null;
  source_type?: string | null;
  role?: string | null;
  verification_state?: string | null;
};

export type ReportPreviewDetailedClause = {
  clause_id?: string | null;
  display_id?: string | null;
  status?: string | null;
  risk_level?: string | null;
  risk_category?: string | null;
  v1_text?: string | null;
  v2_text?: string | null;
  exact_differences?: ReportPreviewExactDifference[];
  explanation?: string | null;
  recommendation?: string | null;
  verification_status?: string | null;
  verification_message?: string | null;
  absence_status?: string | null;
  absence_note?: string | null;
  evidence?: ReportPreviewEvidence[];
};

export type ReportPreviewRiskItem = {
  clause_id?: string | null;
  status?: string | null;
  risk_level?: string | null;
  risk_category?: string | null;
  reason?: string | null;
  explanation?: string | null;
  recommendation?: string | null;
};

export type ReportPreviewComparison = {
  metadata?: {
    title?: string | null;
    comparison_id?: string | null;
    workspace_id?: string | null;
    generated_at?: string | null;
    status?: string | null;
    quality_status?: string | null;
  } | null;
  executive_summary?: Record<string, unknown> | null;
  documents?: ReportPreviewDocument[];
  overall_statistics?: Record<string, unknown> | null;
  risk_summary?: {
    by_level?: Array<{ level?: string; count?: number }>;
    by_category?: Array<{ category?: string; count?: number }>;
    items?: ReportPreviewRiskItem[];
  } | null;
  changed_clauses?: ReportPreviewClauseSummary[];
  added_clauses?: ReportPreviewClauseSummary[];
  removed_clauses?: ReportPreviewClauseSummary[];
  unchanged_clauses?: {
    count?: number;
    clause_ids?: Array<string | null>;
  } | null;
  detailed_clause_comparisons?: ReportPreviewDetailedClause[];
  generation_metadata?: Record<string, unknown> | null;
};

export type ReportPreview = {
  similarities?: string[];
  differences?: string[];
  has_contract_report?: boolean;
  comparison_id?: string | null;
  comparison_ready?: boolean;
  comparison_report?: ReportPreviewComparison | null;
};

export type Report = {
  id: string;
  workspace_id: string;
  title: string;
  export_format: ReportExportFormat;
  status: ReportStatus;
  file_url: string | null;
  created_at: string;
  items?: ReportItemInput[];
  preview?: ReportPreview | null;
};

export type ReportCreateRequest = {
  title: string;
  export_format: ReportExportFormat;
  items: ReportItemInput[];
};
