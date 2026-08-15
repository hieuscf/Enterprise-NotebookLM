/**
 * =============================================================================
 * File: comparison-summary.ts
 * Module/Service: Comparison Service (Web App)
 * Layer: UI
 * Purpose: Pure helpers for TASK-CMP-17 Comparison Summary UI.
 * Responsibilities:
 *   - Normalize optional contract_comparison payload
 *   - Present summary/risk/status/evidence from backend fields only
 *   - Client-side filter/search/priority using existing API fields
 * Dependencies:
 *   - types/comparisons
 * Public Exports:
 *   - normalizeContractComparison, flattenClauses, filterClauses,
 *     priorityClauses, comparisonUiStatus, evidenceViewerHref, …
 * Database/Table: N/A
 * Related Modules: ComparisonSummaryView, ComparisonResult
 * Important Notes: Do not infer ADDED/REMOVED/risk/verification in the UI.
 *   Keep pure for node smoke tests (no React).
 * =============================================================================
 */

import type {
  ClauseComparisonStatus,
  Comparison,
  ContractClauseResult,
  ContractComparisonReport,
  ContractComparisonSummary,
  ContractDocumentRef,
  ContractEvidenceRef,
  ContractExactDifference,
  DocumentMeta,
  RiskLevelValue,
  VerificationStatusValue,
} from "@/types/comparisons";

export type ClauseFilter =
  | "all"
  | "modified"
  | "added"
  | "removed"
  | "unchanged";

export type ComparisonUiStatus =
  | "processing"
  | "failed"
  | "completed"
  | "warning";

export type EvidenceUiState = "verified" | "unverified" | "unavailable" | "partial";

const RISK_RANK: Record<string, number> = {
  CRITICAL: 0,
  HIGH: 1,
  MEDIUM: 2,
  LOW: 3,
};

export const LOADING_STEPS = [
  "Ánh xạ điều khoản",
  "Phân tích khác biệt",
  "Đối chiếu bằng chứng",
  "Chuẩn bị báo cáo",
] as const;

export function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function asString(value: unknown): string | null {
  if (value == null) return null;
  const text = String(value).trim();
  return text ? text : null;
}

function asNumber(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
}

function asClauseArray(value: unknown): ContractClauseResult[] {
  if (!Array.isArray(value)) return [];
  const rows: ContractClauseResult[] = [];
  for (const item of value) {
    const rec = asRecord(item);
    if (!rec) continue;
    const clauseId = asString(rec.clause_id);
    const status = asString(rec.status);
    if (!clauseId || !status) continue;
    rows.push(item as ContractClauseResult);
  }
  return rows;
}

export function unwrapContractComparison(
  raw: unknown,
): Record<string, unknown> | null {
  const rec = asRecord(raw);
  if (!rec) return null;
  const nested = asRecord(rec.comparison);
  if (nested && (nested.summary || nested.clauses || nested.metadata)) {
    return nested;
  }
  if (rec.summary || rec.clauses || rec.metadata) return rec;
  return null;
}

export function normalizeContractComparison(
  raw: unknown,
): ContractComparisonReport | null {
  const rec = unwrapContractComparison(raw);
  if (!rec) return null;

  const summaryRec = asRecord(rec.summary);
  const summary: ContractComparisonSummary | null = summaryRec
    ? {
        total_clauses: asNumber(summaryRec.total_clauses),
        unchanged: asNumber(summaryRec.unchanged),
        modified: asNumber(summaryRec.modified),
        added: asNumber(summaryRec.added),
        removed: asNumber(summaryRec.removed),
      }
    : null;

  const clausesRec = asRecord(rec.clauses);
  const clauses = clausesRec
    ? {
        unchanged: asClauseArray(clausesRec.unchanged),
        modified: asClauseArray(clausesRec.modified),
        added: asClauseArray(clausesRec.added),
        removed: asClauseArray(clausesRec.removed),
        unresolved: asClauseArray(clausesRec.unresolved),
      }
    : null;

  if (!summary && !clauses) return null;

  return {
    metadata: (asRecord(rec.metadata) as ContractComparisonReport["metadata"]) ?? null,
    summary,
    statistics:
      (asRecord(rec.statistics) as ContractComparisonReport["statistics"]) ?? null,
    clauses,
    risks: Array.isArray(rec.risks) ? rec.risks : [],
    citations: Array.isArray(rec.citations) ? rec.citations : [],
  };
}

export function authoritativeSummary(
  report: ContractComparisonReport | null,
): ContractComparisonSummary | null {
  if (!report?.summary) return null;
  return report.summary;
}

export function flattenClauses(
  report: ContractComparisonReport | null,
): ContractClauseResult[] {
  if (!report?.clauses) return [];
  return [
    ...(report.clauses.modified ?? []),
    ...(report.clauses.added ?? []),
    ...(report.clauses.removed ?? []),
    ...(report.clauses.unchanged ?? []),
    ...(report.clauses.unresolved ?? []),
  ];
}

export function comparisonUiStatus(
  comparison: Pick<Comparison, "status">,
  report: ContractComparisonReport | null,
): ComparisonUiStatus {
  if (comparison.status === "processing") return "processing";
  if (comparison.status === "failed") return "failed";
  const quality = String(report?.metadata?.quality_status ?? "").toUpperCase();
  const incomplete = Boolean(report?.metadata?.explanation_incomplete);
  if (quality === "FAIL" || quality === "PASS_WITH_WARNINGS" || incomplete) {
    return "warning";
  }
  return "completed";
}

export function statusBannerLabel(uiStatus: ComparisonUiStatus): string {
  switch (uiStatus) {
    case "processing":
      return "Đang so sánh tài liệu…";
    case "failed":
      return "So sánh thất bại";
    case "warning":
      return "So sánh hoàn tất kèm cảnh báo";
    default:
      return "So sánh hoàn tất";
  }
}

export function clauseStatusLabel(status: ClauseComparisonStatus): string {
  switch (String(status).toUpperCase()) {
    case "UNCHANGED":
      return "Không đổi";
    case "MODIFIED":
      return "Đã sửa";
    case "ADDED":
      return "Thêm mới";
    case "REMOVED":
      return "Đã xoá";
    case "UNRESOLVED":
      return "Chưa xác định";
    default:
      return String(status);
  }
}

export function clauseStatusCaption(status: ClauseComparisonStatus): string {
  switch (String(status).toUpperCase()) {
    case "ADDED":
      return "Thêm ở V2";
    case "REMOVED":
      return "Đã xoá khỏi V2";
    case "MODIFIED":
      return "Đã thay đổi";
    case "UNCHANGED":
      return "Không đổi trong phạm vi so sánh";
    default:
      return clauseStatusLabel(status);
  }
}

export function riskLevelLabel(level: RiskLevelValue | null | undefined): string {
  switch (String(level ?? "").toUpperCase()) {
    case "CRITICAL":
      return "Nghiêm trọng";
    case "HIGH":
      return "Cao";
    case "MEDIUM":
      return "Trung bình";
    case "LOW":
      return "Thấp";
    default:
      return "";
  }
}

export function riskLevelHelp(level: RiskLevelValue | null | undefined): string {
  switch (String(level ?? "").toUpperCase()) {
    case "CRITICAL":
      return "Cần rà soát ngay.";
    case "HIGH":
      return "Tác động hợp đồng đáng kể.";
    case "MEDIUM":
      return "Thay đổi có thể trọng yếu, cần rà soát.";
    case "LOW":
      return "Tác động nhỏ hoặc hạn chế.";
    default:
      return "";
  }
}

export function displayClauseId(id: string | null | undefined): string {
  if (!id) return "—";
  return id.replace(/^(CLAUSE|ARTICLE|APPENDIX|SECTION):/i, "");
}

export function excerpt(text: string | null | undefined, max = 220): string {
  if (!text) return "";
  const normalized = text.replace(/\s+/g, " ").trim();
  if (normalized.length <= max) return normalized;
  return `${normalized.slice(0, max).trimEnd()}…`;
}

export function riskRank(level: string | null | undefined): number {
  const key = String(level ?? "").toUpperCase();
  return RISK_RANK[key] ?? 4;
}

export function clauseRiskLevel(
  clause: ContractClauseResult,
): string | null {
  const level = asString(clause.risk?.risk_level);
  return level ? level.toUpperCase() : null;
}

export function priorityClauses(
  clauses: ContractClauseResult[],
): ContractClauseResult[] {
  const candidates = clauses.filter((clause) => {
    const status = String(clause.status).toUpperCase();
    if (status === "MODIFIED") return true;
    if (status === "ADDED" || status === "REMOVED") return true;
    return false;
  });
  return [...candidates].sort((a, b) => {
    const rankDelta = riskRank(clauseRiskLevel(a)) - riskRank(clauseRiskLevel(b));
    if (rankDelta !== 0) return rankDelta;
    return 0;
  });
}

export function filterClauses(
  clauses: ContractClauseResult[],
  filter: ClauseFilter,
  query: string,
  riskFilter: string | null = null,
): ContractClauseResult[] {
  const q = query.trim().toLowerCase();
  const risk = riskFilter ? riskFilter.toUpperCase() : null;
  return clauses.filter((clause) => {
    const status = String(clause.status).toUpperCase();
    if (filter === "modified" && status !== "MODIFIED") return false;
    if (filter === "added" && status !== "ADDED") return false;
    if (filter === "removed" && status !== "REMOVED") return false;
    if (filter === "unchanged" && status !== "UNCHANGED") return false;
    if (risk && clauseRiskLevel(clause) !== risk) return false;
    if (!q) return true;
    const haystack = [
      clause.clause_id,
      clause.v1_clause_id,
      clause.v2_clause_id,
      displayClauseId(clause.clause_id),
      clause.v1_text,
      clause.v2_text,
      clause.risk?.risk_category,
      clause.risk?.reason,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(q);
  });
}

export function hasMaterialChanges(
  summary: ContractComparisonSummary | null,
): boolean {
  if (!summary) return false;
  return summary.modified + summary.added + summary.removed > 0;
}

export function riskCountsFromReport(
  report: ContractComparisonReport | null,
): { critical: number; high: number; medium: number; low: number } {
  const raw = report?.statistics?.risk_counts ?? {};
  return {
    critical: asNumber(raw.critical),
    high: asNumber(raw.high),
    medium: asNumber(raw.medium),
    low: asNumber(raw.low),
  };
}

export function distributionPercents(
  summary: ContractComparisonSummary | null,
): { unchanged: number; modified: number; added: number; removed: number } {
  if (!summary || summary.total_clauses <= 0) {
    return { unchanged: 0, modified: 0, added: 0, removed: 0 };
  }
  const total = summary.total_clauses;
  return {
    unchanged: (summary.unchanged / total) * 100,
    modified: (summary.modified / total) * 100,
    added: (summary.added / total) * 100,
    removed: (summary.removed / total) * 100,
  };
}

export function evidenceState(
  clause: ContractClauseResult,
): EvidenceUiState {
  const status = String(clause.verification?.status ?? "").toUpperCase();
  const evidence = clause.evidence ?? [];
  if (status === "VERIFIED") return "verified";
  if (status === "PARTIALLY_VERIFIED") return "partial";
  if (status === "INSUFFICIENT_EVIDENCE" || evidence.length === 0) {
    return "unavailable";
  }
  return "unverified";
}

export function evidenceStateLabel(state: EvidenceUiState): string {
  switch (state) {
    case "verified":
      return "Đã xác minh";
    case "partial":
      return "Xác minh một phần";
    case "unavailable":
      return "Không có bằng chứng";
    default:
      return "Chưa xác minh";
  }
}

export function evidenceForSide(
  clause: ContractClauseResult,
  side: "OLD" | "NEW",
): ContractEvidenceRef[] {
  const rows = clause.citations?.length ? clause.citations : clause.evidence ?? [];
  return rows.filter((item) => String(item.side ?? "").toUpperCase() === side);
}

export function explanationText(clause: ContractClauseResult): string | null {
  const output = clause.explanation?.output?.explanation;
  const text = asString(output);
  if (!text) return null;
  if (clause.explanation?.unavailable) return text;
  return text;
}

export function formatExactDifference(row: ContractExactDifference): {
  label: string;
  oldDisplay: string;
  newDisplay: string;
  delta: string | null;
  percent: string | null;
} {
  const valueType = asString(row.value_type) ?? asString(row.change_type) ?? "Giá trị";
  const oldRaw = asString(row.old?.raw) ?? asString(row.old?.value);
  const newRaw = asString(row.new?.raw) ?? asString(row.new?.value);
  const delta = asString(row.delta);
  const percent = asString(row.relative_change_percent);
  const unit = asString(row.delta_unit);
  return {
    label: valueType,
    oldDisplay: oldRaw ?? "—",
    newDisplay: newRaw ?? "—",
    delta: delta ? `${delta}${unit ? ` ${unit}` : ""}` : null,
    percent: percent ? `${percent}%` : null,
  };
}

export function documentLabel(
  ref: ContractDocumentRef | null | undefined,
  fallbackId: string | undefined,
  meta?: DocumentMeta | null,
): { title: string; versionId: string | null; date: string | null } {
  const title =
    asString(ref?.title) ??
    asString(meta?.title) ??
    (fallbackId ? fallbackId.slice(0, 8) : "Tài liệu");
  return {
    title,
    versionId: asString(ref?.document_version_id),
    date: asString(meta?.created_at) ?? null,
  };
}

export function evidenceViewerHref(
  workspaceId: string,
  evidence: ContractEvidenceRef,
  fallbackDocumentId?: string | null,
  fallbackVersionId?: string | null,
): string | null {
  const documentId =
    asString(evidence.document_id) ?? asString(fallbackDocumentId);
  if (!documentId) return null;
  const params = new URLSearchParams();
  const page = evidence.page_number;
  if (typeof page === "number" && page > 0) {
    params.set("page", String(page));
    params.set("view", "original");
  } else {
    params.set("view", "knowledge");
  }
  const chunkId = asString(evidence.chunk_id);
  if (chunkId) params.set("chunk", chunkId);
  const versionId =
    asString(evidence.document_version_id) ?? asString(fallbackVersionId);
  if (versionId) params.set("version", versionId);
  const qs = params.toString();
  const base = `/workspaces/${workspaceId}/documents/${documentId}`;
  return qs ? `${base}?${qs}` : base;
}

export function documentViewerHref(
  workspaceId: string,
  documentId: string | null | undefined,
  versionId?: string | null,
): string | null {
  if (!documentId) return null;
  const params = new URLSearchParams();
  params.set("view", "original");
  if (versionId) params.set("version", versionId);
  return `/workspaces/${workspaceId}/documents/${documentId}?${params.toString()}`;
}

export function shortChangeSummary(clause: ContractClauseResult): string {
  const diffs = clause.exact_differences ?? [];
  if (diffs.length > 0) {
    const first = formatExactDifference(diffs[0]);
    if (first.oldDisplay !== "—" || first.newDisplay !== "—") {
      return `${first.label}: ${first.oldDisplay} → ${first.newDisplay}`;
    }
  }
  const status = String(clause.status).toUpperCase();
  if (status === "ADDED") return "Điều khoản được thêm ở phiên bản V2.";
  if (status === "REMOVED") return "Điều khoản bị xoá khỏi phiên bản V2.";
  if (status === "MODIFIED") {
    return excerpt(clause.v2_text || clause.v1_text, 120) || "Nội dung đã thay đổi.";
  }
  return "Không có thay đổi trong phạm vi so sánh.";
}

export function evidenceLine(clause: ContractClauseResult): string {
  const v1 = evidenceForSide(clause, "OLD")[0];
  const v2 = evidenceForSide(clause, "NEW")[0];
  const parts: string[] = [];
  if (v1?.page_number) parts.push(`V1 tr.${v1.page_number}`);
  if (v2?.page_number) parts.push(`V2 tr.${v2.page_number}`);
  if (parts.length) return parts.join(" · ");
  const state = evidenceState(clause);
  return evidenceStateLabel(state);
}

export function qualityWarningText(
  report: ContractComparisonReport | null,
): string | null {
  if (!report?.metadata) return null;
  const quality = String(report.metadata.quality_status ?? "").toUpperCase();
  const incomplete = Boolean(report.metadata.explanation_incomplete);
  if (quality === "FAIL") {
    return "Một số kết quả không đạt ngưỡng chất lượng. Hãy ưu tiên bằng chứng nguồn.";
  }
  if (quality === "PASS_WITH_WARNINGS" || incomplete) {
    return "Một số phát hiện chưa được xác minh đầy đủ.";
  }
  return null;
}
