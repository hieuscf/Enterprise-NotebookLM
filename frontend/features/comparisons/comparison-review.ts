/**
 * =============================================================================
 * File: comparison-review.ts
 * Module/Service: Comparison Service (Web App)
 * Layer: UI
 * Purpose: Pure helpers for TASK-CMP-20 reviewer decisions.
 * Responsibilities:
 *   - Map backend review status; never infer from risk/diff/evidence
 *   - Progress counts and review-state filtering
 * Dependencies:
 *   - types/comparisons
 * Public Exports:
 *   - reviewState, reviewStateLabel, reviewProgress, filterByReview, …
 * Database/Table: N/A
 * Related Modules: ComparisonReviewActions, ComparisonSummaryView
 * Important Notes: Comparison analysis is immutable. Review is separate metadata.
 * =============================================================================
 */

import type {
  ComparisonReviewDecision,
  ComparisonReviewStatus,
  ContractClauseResult,
} from "@/types/comparisons";

export type ReviewFilter = "all" | "open" | "reviewed" | "needs_attention" | "acknowledged";

export type ReviewMap = Record<string, ComparisonReviewDecision>;

const PERSISTED: ComparisonReviewStatus[] = [
  "REVIEWED",
  "NEEDS_ATTENTION",
  "ACKNOWLEDGED",
];

export function normalizeReviewMap(raw: ReviewMap | null | undefined): ReviewMap {
  if (!raw || typeof raw !== "object") return {};
  const out: ReviewMap = {};
  for (const [key, value] of Object.entries(raw)) {
    const status = String(value?.status ?? "").toUpperCase();
    if (!PERSISTED.includes(status)) continue;
    out[key] = {
      status,
      reviewer_id: value.reviewer_id ?? null,
      reviewer_name: value.reviewer_name ?? null,
      reviewed_at: value.reviewed_at ?? null,
    };
  }
  return out;
}

export function reviewState(
  review: ReviewMap | null | undefined,
  clauseId: string,
): ComparisonReviewStatus {
  const status = String(normalizeReviewMap(review)[clauseId]?.status ?? "").toUpperCase();
  if (status === "REVIEWED") return "REVIEWED";
  if (status === "NEEDS_ATTENTION") return "NEEDS_ATTENTION";
  if (status === "ACKNOWLEDGED") return "ACKNOWLEDGED";
  return "OPEN";
}

export function reviewStateLabel(status: ComparisonReviewStatus): string {
  switch (String(status).toUpperCase()) {
    case "REVIEWED":
      return "Đã rà soát";
    case "NEEDS_ATTENTION":
      return "Cần chú ý";
    case "ACKNOWLEDGED":
      return "Đã ghi nhận";
    default:
      return "Chưa rà soát";
  }
}

export function reviewDecision(
  review: ReviewMap | null | undefined,
  clauseId: string,
): ComparisonReviewDecision | null {
  return normalizeReviewMap(review)[clauseId] ?? null;
}

export function reviewProgress(
  clauseIds: string[],
  review: ReviewMap | null | undefined,
): { total: number; reviewed: number; needsAttention: number; open: number; acknowledged: number } {
  const map = normalizeReviewMap(review);
  let reviewed = 0;
  let needsAttention = 0;
  let acknowledged = 0;
  for (const id of clauseIds) {
    const status = reviewState(map, id);
    if (status === "REVIEWED") reviewed += 1;
    else if (status === "NEEDS_ATTENTION") needsAttention += 1;
    else if (status === "ACKNOWLEDGED") acknowledged += 1;
  }
  const total = clauseIds.length;
  return {
    total,
    reviewed,
    needsAttention,
    acknowledged,
    open: total - reviewed - needsAttention - acknowledged,
  };
}

export function filterByReview(
  clauses: ContractClauseResult[],
  review: ReviewMap | null | undefined,
  filter: ReviewFilter,
): ContractClauseResult[] {
  if (filter === "all") return clauses;
  const wanted =
    filter === "open"
      ? "OPEN"
      : filter === "reviewed"
        ? "REVIEWED"
        : filter === "needs_attention"
          ? "NEEDS_ATTENTION"
          : "ACKNOWLEDGED";
  return clauses.filter((clause) => reviewState(review, clause.clause_id) === wanted);
}

export function formatReviewerLine(decision: ComparisonReviewDecision | null): string | null {
  if (!decision) return null;
  const name = (decision.reviewer_name ?? "").trim();
  const at = decision.reviewed_at ? formatReviewTime(decision.reviewed_at) : null;
  if (name && at) return `${name} · ${at}`;
  if (name) return name;
  if (at) return at;
  return null;
}

function formatReviewTime(iso: string): string | null {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString("vi-VN", {
    dateStyle: "short",
    timeStyle: "short",
  });
}
