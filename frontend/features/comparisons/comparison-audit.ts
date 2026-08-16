/**
 * =============================================================================
 * File: comparison-audit.ts
 * Module/Service: Comparison Service (Web App)
 * Layer: UI
 * Purpose: Pure helpers for TASK-CMP-23/27 comparison audit trail display.
 * Responsibilities:
 *   - Label actions and summarize before/after/metadata without inventing analysis
 *   - Filter trail by clause; newest-first for scanning
 * Dependencies:
 *   - types/comparisons, comparison-review labels
 * Public Exports:
 *   - auditActionLabel, auditActorLabel, auditChangeText, eventsForClause, newestFirst
 * Database/Table: N/A
 * Related Modules: ComparisonAuditTrail
 * Important Notes: Display-only. The trail is an audit log, not a chat feed.
 * =============================================================================
 */

import { reviewStateLabel } from "@/features/comparisons/comparison-review";
import type {
  ComparisonAuditAction,
  ComparisonAuditEvent,
  ComparisonReviewStatus,
} from "@/types/comparisons";

export function auditActionLabel(action: ComparisonAuditAction): string {
  switch (String(action).toUpperCase()) {
    case "CLAUSE_OPENED":
      return "Mở điều khoản";
    case "REVIEW_STATUS_CHANGED":
      return "Đổi trạng thái rà soát";
    case "COMMENT_ADDED":
      return "Thêm ghi chú";
    case "COMMENT_EDITED":
      return "Sửa ghi chú";
    case "COMMENT_DELETED":
      return "Xoá ghi chú";
    case "COMPARISON_CREATED":
      return "Tạo so sánh";
    case "COMPARISON_STARTED":
      return "Bắt đầu xử lý";
    case "STRUCTURE_EXTRACTION_COMPLETED":
      return "Hoàn tất trích xuất cấu trúc";
    case "CLAUSE_NORMALIZATION_COMPLETED":
      return "Hoàn tất chuẩn hoá điều khoản";
    case "CLAUSE_MAPPING_COMPLETED":
      return "Hoàn tất ánh xạ điều khoản";
    case "DIFF_COMPLETED":
      return "Hoàn tất so sánh khác biệt";
    case "RISK_DETECTION_COMPLETED":
      return "Hoàn tất phát hiện rủi ro";
    case "LLM_EXPLANATION_COMPLETED":
      return "Hoàn tất giải thích LLM";
    case "CITATION_VERIFICATION_COMPLETED":
      return "Hoàn tất xác minh trích dẫn";
    case "COMPARISON_COMPLETED":
      return "Hoàn tất so sánh";
    case "COMPARISON_FAILED":
      return "So sánh thất bại";
    case "COMPARISON_CANCELLED":
      return "Đã huỷ so sánh";
    case "COMPARISON_REPORT_CREATED":
      return "Tạo báo cáo so sánh";
    case "COMPARISON_EXPORTED":
      return "Xuất báo cáo so sánh";
    default:
      return String(action);
  }
}

export function auditActorLabel(event: ComparisonAuditEvent): string {
  const name = String(event.actor_name ?? "").trim();
  if (name && name.toLowerCase() !== "system") return name;
  if (event.actor_id) return "Người dùng";
  return "Hệ thống";
}

function asStatus(value: unknown): ComparisonReviewStatus {
  return String(value ?? "OPEN").toUpperCase();
}

function excerpt(value: unknown, limit = 80): string {
  const text = String(value ?? "").trim();
  if (!text) return "";
  if (text.length <= limit) return text;
  return `${text.slice(0, limit)}…`;
}

function snapshotField(
  snapshot: Record<string, unknown> | null | undefined,
  key: string,
): unknown {
  if (!snapshot || typeof snapshot !== "object") return null;
  return snapshot[key];
}

export function auditChangeText(event: ComparisonAuditEvent): string | null {
  const action = String(event.action ?? "").toUpperCase();
  if (action === "REVIEW_STATUS_CHANGED") {
    const from = reviewStateLabel(asStatus(snapshotField(event.before, "status")));
    const to = reviewStateLabel(asStatus(snapshotField(event.after, "status")));
    return `${from} → ${to}`;
  }
  if (action === "COMMENT_ADDED") {
    const body = excerpt(snapshotField(event.after, "body"));
    return body || null;
  }
  if (action === "COMMENT_EDITED") {
    const before = excerpt(snapshotField(event.before, "body"));
    const after = excerpt(snapshotField(event.after, "body"));
    if (before && after) return `${before} → ${after}`;
    return after || before || null;
  }
  if (action === "COMMENT_DELETED") {
    const body = excerpt(snapshotField(event.before, "body"));
    return body || null;
  }
  return metadataSummary(event.metadata);
}

function metadataSummary(
  metadata: Record<string, unknown> | null | undefined,
): string | null {
  if (!metadata || typeof metadata !== "object") return null;
  const parts: string[] = [];
  const stage = metadata.stage;
  const errorCode = metadata.error_code;
  if (stage) parts.push(`Giai đoạn: ${String(stage)}`);
  if (errorCode) parts.push(`Mã: ${String(errorCode)}`);
  const counts: Array<[string, string]> = [
    ["document_count", "tài liệu"],
    ["clause_count", "điều khoản"],
    ["modified_count", "sửa"],
    ["added_count", "thêm"],
    ["removed_count", "xoá"],
    ["unchanged_count", "không đổi"],
    ["risk_count", "rủi ro"],
    ["critical_count", "critical"],
    ["high_count", "high"],
    ["total_citations", "trích dẫn"],
    ["verified", "đã xác minh"],
    ["unverified", "chưa xác minh"],
    ["llm_calls", "lần gọi LLM"],
  ];
  for (const [key, label] of counts) {
    const value = metadata[key];
    if (typeof value === "number") parts.push(`${label} ${value}`);
  }
  if (metadata.has_contract_report === false) {
    parts.push("Không có báo cáo điều khoản");
  }
  return parts.length ? parts.join(" · ") : null;
}

export function eventsForClause(
  events: ComparisonAuditEvent[] | null | undefined,
  clauseId: string | null,
): ComparisonAuditEvent[] {
  const rows = Array.isArray(events) ? events : [];
  if (!clauseId) return rows;
  return rows.filter((item) => String(item.clause_id ?? "") === clauseId);
}

export function newestFirst(
  events: ComparisonAuditEvent[] | null | undefined,
): ComparisonAuditEvent[] {
  const rows = Array.isArray(events) ? [...events] : [];
  return rows.reverse();
}

export function formatAuditTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("vi-VN", {
    dateStyle: "short",
    timeStyle: "short",
  });
}
