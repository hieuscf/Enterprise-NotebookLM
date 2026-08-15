/**
 * =============================================================================
 * File: comparison-audit.ts
 * Module/Service: Comparison Service (Web App)
 * Layer: UI
 * Purpose: Pure helpers for TASK-CMP-23 comparison audit trail display.
 * Responsibilities:
 *   - Label actions and summarize before/after without inventing analysis
 *   - Filter trail by clause; newest-first for scanning
 * Dependencies:
 *   - types/comparisons, comparison-review labels
 * Public Exports:
 *   - auditActionLabel, auditChangeText, eventsForClause, newestFirst
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
    default:
      return String(action);
  }
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
  return null;
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
