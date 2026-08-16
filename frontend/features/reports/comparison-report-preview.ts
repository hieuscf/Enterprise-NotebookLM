/**
 * =============================================================================
 * File: comparison-report-preview.ts
 * Module/Service: Report Service (Web App)
 * Layer: UI
 * Purpose: Pure helpers for TASK-CMP-25 Comparison Report Preview.
 * Responsibilities:
 *   - Project GET-detail preview without recounting comparison results
 *   - Filter/search structured report rows; exact source-navigation policy
 *   - Map HTTP / report status to honest UI states
 * Dependencies:
 *   - types/reports, comparison-summary display labels
 * Public Exports:
 *   - unwrapComparisonReport, executiveCounts, reportNavSections,
 *     filterReportClauses, evidenceRowKey, exactSourceHref, exportEnabled, …
 * Database/Table: N/A
 * Related Modules: ComparisonReportPreview, useReportPreview
 * Important Notes: Presentation only. Do not remap, rescore, or infer
 *   ADDED/REMOVED. Do not open page 1 when exact location is missing.
 *   Keep pure for node smoke tests (no React). Zero LLM calls.
 * =============================================================================
 */

import { displayClauseId } from "@/features/comparisons/comparison-summary";
import type {
  Report,
  ReportItemInput,
  ReportPreview,
  ReportPreviewClauseSummary,
  ReportPreviewComparison,
  ReportPreviewDetailedClause,
  ReportPreviewDocument,
  ReportPreviewEvidence,
  ReportStatus,
} from "@/types/reports";

export type ReportStatusFilter =
  | "all"
  | "modified"
  | "added"
  | "removed"
  | "unchanged";

export type ReportRiskFilter = "all" | "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";

export type ReportPreviewFilters = {
  status: ReportStatusFilter;
  risk: ReportRiskFilter;
  query: string;
};

export const EMPTY_REPORT_FILTERS: ReportPreviewFilters = {
  status: "all",
  risk: "all",
  query: "",
};

export type ReportNavSection = {
  id: string;
  label: string;
};

export type ExecutiveCounts = {
  total: number;
  unchanged: number;
  modified: number;
  added: number;
  removed: number;
  unresolved: number;
  risk_total: number;
  high_risks: number;
  critical_risks: number;
  verified_evidence_count: number;
  risk_counts: Record<string, number>;
};

const RISK_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const;

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function asString(value: unknown): string | null {
  if (value == null) return null;
  const text = String(value).trim();
  return text ? text : null;
}

function asInt(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) return Math.trunc(value);
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return Math.trunc(parsed);
  }
  return fallback;
}

export function unwrapComparisonReport(
  preview: ReportPreview | null | undefined,
): ReportPreviewComparison | null {
  if (!preview || typeof preview !== "object") return null;
  const report = preview.comparison_report;
  if (!report || typeof report !== "object") return null;
  return report;
}

export function comparisonIdFromReport(report: Report | null | undefined): string | null {
  if (!report) return null;
  const fromPreview = asString(report.preview?.comparison_id);
  if (fromPreview) return fromPreview;
  const fromMeta = asString(report.preview?.comparison_report?.metadata?.comparison_id);
  if (fromMeta) return fromMeta;
  const item = (report.items ?? []).find((row) => row.source_type === "comparison");
  return item?.source_id ?? null;
}

export function comparisonHref(workspaceId: string, comparisonId: string | null): string | null {
  if (!workspaceId || !comparisonId) return null;
  return `/workspaces/${workspaceId}/comparisons?comparison=${encodeURIComponent(comparisonId)}`;
}

export function reportPreviewHref(workspaceId: string, reportId: string, clause?: string | null): string {
  const base = `/workspaces/${workspaceId}/reports/${reportId}`;
  const token = asString(clause);
  if (!token) return base;
  return `${base}?clause=${encodeURIComponent(token)}`;
}

export function executiveCounts(
  report: ReportPreviewComparison | null | undefined,
): ExecutiveCounts {
  const exec = asRecord(report?.executive_summary) ?? {};
  const rawCounts = asRecord(exec.risk_counts) ?? {};
  const risk_counts: Record<string, number> = {};
  for (const level of RISK_ORDER) {
    risk_counts[level] = asInt(rawCounts[level]);
  }
  return {
    total: asInt(exec.total_clauses),
    unchanged: asInt(exec.unchanged),
    modified: asInt(exec.modified),
    added: asInt(exec.added),
    removed: asInt(exec.removed),
    unresolved: asInt(exec.unresolved),
    risk_total: asInt(exec.risk_total),
    high_risks: asInt(exec.high_risks),
    critical_risks: asInt(exec.critical_risks),
    verified_evidence_count: asInt(exec.verified_evidence_count),
    risk_counts,
  };
}

export function documentNames(report: ReportPreviewComparison | null | undefined): string[] {
  const rows = Array.isArray(report?.documents) ? report.documents : [];
  return rows
    .map((item) => asString(item.title))
    .filter((title): title is string => Boolean(title));
}

export function reportNavSections(
  report: ReportPreviewComparison | null | undefined,
): ReportNavSection[] {
  if (!report) return [];
  const sections: ReportNavSection[] = [{ id: "overview", label: "Tổng quan" }];
  if ((report.documents ?? []).some((item) => item.title || item.document_id)) {
    sections.push({ id: "documents", label: "Tài liệu" });
  }
  sections.push({ id: "statistics", label: "Thống kê" });
  const riskItems = report.risk_summary?.items ?? [];
  const riskLevels = report.risk_summary?.by_level ?? [];
  if (riskItems.length > 0 || riskLevels.some((row) => asInt(row.count) > 0)) {
    sections.push({ id: "risks", label: "Rủi ro" });
  }
  if ((report.changed_clauses ?? []).length > 0) {
    sections.push({ id: "changed", label: "Điều khoản đã sửa" });
  }
  if ((report.added_clauses ?? []).length > 0) {
    sections.push({ id: "added", label: "Điều khoản thêm mới" });
  }
  if ((report.removed_clauses ?? []).length > 0) {
    sections.push({ id: "removed", label: "Điều khoản đã xoá" });
  }
  const unchangedCount = asInt(report.unchanged_clauses?.count);
  if (unchangedCount > 0 || (report.unchanged_clauses?.clause_ids ?? []).length > 0) {
    sections.push({ id: "unchanged", label: "Không đổi" });
  }
  const evidenceCount = (report.detailed_clause_comparisons ?? []).reduce(
    (sum, clause) => sum + (clause.evidence?.length ?? 0),
    0,
  );
  if (evidenceCount > 0) {
    sections.push({ id: "evidence", label: "Bằng chứng" });
  }
  return sections;
}

export function clauseStatusKey(status: string | null | undefined): string {
  return String(status ?? "").toUpperCase();
}

export function isExplicitStatus(
  status: string | null | undefined,
  expected: "MODIFIED" | "ADDED" | "REMOVED" | "UNCHANGED",
): boolean {
  return clauseStatusKey(status) === expected;
}

export function collectReportClauses(
  report: ReportPreviewComparison | null | undefined,
): ReportPreviewClauseSummary[] {
  if (!report) return [];
  return [
    ...(report.changed_clauses ?? []),
    ...(report.added_clauses ?? []),
    ...(report.removed_clauses ?? []),
  ].filter((row) => asString(row.clause_id) || asString(row.display_id));
}

function clauseHaystack(
  clause: ReportPreviewClauseSummary,
  documents: ReportPreviewDocument[],
): string {
  const names = documents
    .map((item) => asString(item.title))
    .filter(Boolean)
    .join(" ");
  return [
    clause.clause_id,
    clause.display_id,
    displayClauseId(clause.clause_id),
    clause.status,
    clause.risk_level,
    clause.risk_category,
    clause.change,
    names,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

export function clauseMatchesQuery(
  clause: ReportPreviewClauseSummary,
  query: string,
  documents: ReportPreviewDocument[] = [],
): boolean {
  const token = query.trim().toLowerCase();
  if (!token) return true;
  return clauseHaystack(clause, documents).includes(token);
}

export function filterReportClauses(
  clauses: ReportPreviewClauseSummary[],
  filters: ReportPreviewFilters,
  documents: ReportPreviewDocument[] = [],
): ReportPreviewClauseSummary[] {
  const status = filters.status;
  const risk = filters.risk;
  return clauses.filter((clause) => {
    const key = clauseStatusKey(clause.status);
    if (status === "modified" && key !== "MODIFIED") return false;
    if (status === "added" && key !== "ADDED") return false;
    if (status === "removed" && key !== "REMOVED") return false;
    if (status === "unchanged" && key !== "UNCHANGED") return false;
    if (risk !== "all" && String(clause.risk_level ?? "").toUpperCase() !== risk) {
      return false;
    }
    return clauseMatchesQuery(clause, filters.query, documents);
  });
}

export function findClauseId(
  clauses: Array<Pick<ReportPreviewClauseSummary, "clause_id" | "display_id">>,
  param: string | null | undefined,
): string | null {
  const raw = asString(param);
  if (!raw) return null;
  const upper = raw.toUpperCase();
  const stripped = displayClauseId(raw).toUpperCase();
  for (const clause of clauses) {
    const id = asString(clause.clause_id);
    const display = asString(clause.display_id) ?? (id ? displayClauseId(id) : null);
    const candidates = [id, display].filter(Boolean).map((value) => String(value));
    if (candidates.some((value) => value === raw || value.toUpperCase() === upper)) {
      return id ?? display;
    }
    if (display && display.toUpperCase() === stripped) return id ?? display;
  }
  return null;
}

export function findDetailedClause(
  report: ReportPreviewComparison | null | undefined,
  clauseId: string | null | undefined,
): ReportPreviewDetailedClause | null {
  const target = findClauseId(report?.detailed_clause_comparisons ?? [], clauseId);
  if (!target) return null;
  return (
    (report?.detailed_clause_comparisons ?? []).find((row) => {
      const id = asString(row.clause_id);
      const display = asString(row.display_id);
      return id === target || display === target || displayClauseId(id) === displayClauseId(target);
    }) ?? null
  );
}

export function exportEnabled(status: ReportStatus | string | null | undefined): boolean {
  return String(status ?? "").toLowerCase() === "ready";
}

export function isPendingStatus(status: ReportStatus | string | null | undefined): boolean {
  const key = String(status ?? "").toLowerCase();
  return key === "pending" || key === "generating";
}

export function isFailedStatus(status: ReportStatus | string | null | undefined): boolean {
  return String(status ?? "").toLowerCase() === "failed";
}

export function isReadyStatus(status: ReportStatus | string | null | undefined): boolean {
  return String(status ?? "").toLowerCase() === "ready";
}

export function retryPayload(report: Report): {
  title: string;
  export_format: Report["export_format"];
  items: ReportItemInput[];
} | null {
  const items = report.items ?? [];
  if (!items.length) return null;
  return {
    title: report.title,
    export_format: report.export_format,
    items,
  };
}

export function exactSourceHref(
  workspaceId: string,
  evidence: ReportPreviewEvidence,
): string | null {
  const documentId = asString(evidence.document_id);
  if (!workspaceId || !documentId) return null;
  const page = evidence.page_number;
  const hasPage = typeof page === "number" && Number.isFinite(page) && page > 0;
  const chunkId = asString(evidence.chunk_id);
  if (!hasPage && !chunkId) return null;
  const params = new URLSearchParams();
  params.set("view", "original");
  if (hasPage) params.set("page", String(Math.trunc(page)));
  if (chunkId) params.set("chunk", chunkId);
  const versionId = asString(evidence.document_version_id);
  if (versionId) params.set("version", versionId);
  return `/workspaces/${workspaceId}/documents/${documentId}?${params.toString()}`;
}

export function evidenceVerificationLabel(state: string | null | undefined): string {
  switch (String(state ?? "").toLowerCase()) {
    case "verified":
      return "Bằng chứng đã xác minh";
    case "partial":
      return "Bằng chứng xác minh một phần";
    case "unavailable":
      return "Không có bằng chứng";
    default:
      return "Bằng chứng cần xác minh";
  }
}

export function isVerifiedEvidence(state: string | null | undefined): boolean {
  return String(state ?? "").toLowerCase() === "verified";
}

export function reportHttpMessage(status: number, rawMessage?: string | null): string {
  if (status === 403) return "Bạn không có quyền xem báo cáo này.";
  if (status === 404) return "Không tìm thấy báo cáo.";
  if (status === 409) return "Báo cáo chưa sẵn sàng.";
  if (status === 422) return "Dữ liệu báo cáo không hợp lệ.";
  if (status >= 500) return "Không tải được báo cáo. Vui lòng thử lại.";
  const text = asString(rawMessage);
  if (text && !isUnsafeErrorMessage(text)) return text;
  return "Không tải được báo cáo.";
}

export function isUnsafeErrorMessage(message: string): boolean {
  const text = message.toLowerCase();
  return (
    text.includes("traceback") ||
    text.includes("psycopg") ||
    text.includes("sqlalchemy") ||
    text.includes("operationalerror") ||
    text.includes("exception") ||
    text.includes("stack") ||
    /\.py\b/.test(text)
  );
}

export function emptyClauseMessage(
  kind: "changed" | "added" | "removed" | "risks" | "search" | "evidence",
): string {
  switch (kind) {
    case "changed":
      return "Không có điều khoản đã sửa trong báo cáo này.";
    case "added":
      return "Không có điều khoản được đánh dấu thêm mới.";
    case "removed":
      return "Không có điều khoản được đánh dấu đã xoá.";
    case "risks":
      return "Không phát hiện thay đổi rủi ro cao.";
    case "search":
      return "Không có kết quả khớp bộ lọc hoặc từ khoá.";
    default:
      return "Không có bằng chứng được đính kèm.";
  }
}

export function evidenceRowKey(
  item: Pick<
    ReportPreviewEvidence,
    | "evidence_id"
    | "document_id"
    | "document_version_id"
    | "clause_id"
    | "side"
    | "chunk_id"
    | "page_number"
    | "role"
  >,
  index: number,
): string {
  const evidenceId = asString(item.evidence_id);
  if (evidenceId) return evidenceId;
  return [
    item.document_id ?? "ev",
    item.document_version_id ?? "ver",
    item.side ?? "side",
    item.clause_id ?? "clause",
    item.chunk_id ?? "chunk",
    item.page_number ?? "page",
    item.role ?? "role",
    index,
  ].join("-");
}

export function allEvidenceRows(
  report: ReportPreviewComparison | null | undefined,
): Array<ReportPreviewEvidence & { clause_id?: string | null; display_id?: string | null }> {
  const rows: Array<ReportPreviewEvidence & { clause_id?: string | null; display_id?: string | null }> =
    [];
  for (const clause of report?.detailed_clause_comparisons ?? []) {
    for (const item of clause.evidence ?? []) {
      rows.push({
        ...item,
        clause_id: item.clause_id ?? clause.clause_id,
        display_id: clause.display_id,
      });
    }
  }
  return rows;
}

export function sourceLocationLabel(evidence: ReportPreviewEvidence): string {
  const parts: string[] = [];
  const side = asString(evidence.side);
  if (side) parts.push(side);
  const title = asString(evidence.document_title);
  if (title) parts.push(title);
  const page = evidence.page_number;
  if (typeof page === "number" && page > 0) parts.push(`Trang ${page}`);
  const clause = asString(evidence.clause_id);
  if (clause) parts.push(`Điều ${displayClauseId(clause)}`);
  return parts.join(" · ");
}
