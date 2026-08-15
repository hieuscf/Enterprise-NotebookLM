/**
 * =============================================================================
 * File: comparison-filter.ts
 * Module/Service: Comparison Service (Web App)
 * Layer: UI
 * Purpose: Pure query helpers for TASK-CMP-21 Comparison Filtering & Advanced Search.
 * Responsibilities:
 *   - Combine status, risk, review, evidence, category, and keyword with AND
 *   - Present facet counts and active-filter chips without mutating the report
 * Dependencies:
 *   - comparison-summary, comparison-review, types/comparisons
 * Public Exports:
 *   - applyComparisonQuery, matchesComparisonQuery, EMPTY_COMPARISON_QUERY,
 *     isQueryActive, activeQueryChips, queryScopeLabel, facetCounts, …
 * Database/Table: N/A
 * Related Modules: ComparisonFilterBar, ComparisonSummaryView, ClauseComparisonView
 * Important Notes: Presentation/query layer only. Do not change comparison
 *   results, mapping, diffs, risk, evidence, citations, or review decisions.
 *   Evidence filter uses backend verification.status — never infer from page/text.
 * =============================================================================
 */

import {
  reviewDecision,
  reviewState,
  reviewStateLabel,
  type ReviewFilter,
  type ReviewMap,
} from "@/features/comparisons/comparison-review";
import {
  clauseRiskLevel,
  displayClauseId,
  evidenceState,
  evidenceStateLabel,
  explanationText,
  formatExactDifference,
  riskLevelLabel,
  type ClauseFilter,
  type EvidenceUiState,
} from "@/features/comparisons/comparison-summary";
import {
  commentBodiesForSearch,
} from "@/features/comparisons/comparison-comments";
import type { ComparisonComment, ContractClauseResult } from "@/types/comparisons";

export type EvidenceFilter = "all" | EvidenceUiState;

export type ComparisonQuery = {
  status: ClauseFilter;
  risk: string | null;
  review: ReviewFilter;
  evidence: EvidenceFilter;
  category: string | null;
  query: string;
};

export const EMPTY_COMPARISON_QUERY: ComparisonQuery = {
  status: "all",
  risk: null,
  review: "all",
  evidence: "all",
  category: null,
  query: "",
};

const STATUS_FILTERS: ClauseFilter[] = [
  "all",
  "changed",
  "modified",
  "added",
  "removed",
  "unchanged",
];

const REVIEW_FILTERS: ReviewFilter[] = [
  "all",
  "open",
  "reviewed",
  "needs_attention",
  "acknowledged",
];

const EVIDENCE_FILTERS: EvidenceFilter[] = [
  "all",
  "verified",
  "partial",
  "unverified",
  "unavailable",
];

const RISK_LEVELS = ["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const;

function asFilter<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  const key = String(value ?? "").trim().toLowerCase();
  return (allowed as readonly string[]).includes(key) ? (key as T) : fallback;
}

export function normalizeComparisonQuery(
  raw: Partial<ComparisonQuery> | null | undefined,
): ComparisonQuery {
  const status = asFilter(raw?.status, STATUS_FILTERS, "all");
  const review = asFilter(raw?.review, REVIEW_FILTERS, "all");
  const evidence = asFilter(raw?.evidence, EVIDENCE_FILTERS, "all");
  const riskRaw = String(raw?.risk ?? "").trim().toUpperCase();
  const risk = (RISK_LEVELS as readonly string[]).includes(riskRaw) ? riskRaw : null;
  const category = String(raw?.category ?? "").trim() || null;
  const query = String(raw?.query ?? "");
  return { status, risk, review, evidence, category, query };
}

export function isQueryActive(query: ComparisonQuery): boolean {
  const q = normalizeComparisonQuery(query);
  return (
    q.status !== "all" ||
    q.risk != null ||
    q.review !== "all" ||
    q.evidence !== "all" ||
    q.category != null ||
    q.query.trim() !== ""
  );
}

export function statusFilterLabel(filter: ClauseFilter): string {
  switch (filter) {
    case "changed":
      return "Có thay đổi";
    case "modified":
      return "Đã sửa";
    case "added":
      return "Thêm mới";
    case "removed":
      return "Đã xoá";
    case "unchanged":
      return "Không đổi";
    default:
      return "Tất cả";
  }
}

export function reviewFilterLabel(filter: ReviewFilter): string {
  switch (filter) {
    case "open":
      return "Chưa rà soát";
    case "reviewed":
      return "Đã rà soát";
    case "needs_attention":
      return "Cần chú ý";
    case "acknowledged":
      return "Đã ghi nhận";
    default:
      return "Mọi rà soát";
  }
}

export function evidenceFilterLabel(filter: EvidenceFilter): string {
  if (filter === "all") return "Mọi bằng chứng";
  return evidenceStateLabel(filter);
}

export function matchesStatusFilter(clause: ContractClauseResult, filter: ClauseFilter): boolean {
  if (filter === "all") return true;
  const status = String(clause.status).toUpperCase();
  if (filter === "changed") {
    return status === "MODIFIED" || status === "ADDED" || status === "REMOVED";
  }
  if (filter === "modified") return status === "MODIFIED";
  if (filter === "added") return status === "ADDED";
  if (filter === "removed") return status === "REMOVED";
  if (filter === "unchanged") return status === "UNCHANGED";
  return true;
}

export function matchesRiskFilter(clause: ContractClauseResult, risk: string | null): boolean {
  if (!risk) return true;
  return clauseRiskLevel(clause) === risk.toUpperCase();
}

export function matchesReviewFilter(
  clause: ContractClauseResult,
  review: ReviewMap | null | undefined,
  filter: ReviewFilter,
): boolean {
  if (filter === "all") return true;
  const wanted =
    filter === "open"
      ? "OPEN"
      : filter === "reviewed"
        ? "REVIEWED"
        : filter === "needs_attention"
          ? "NEEDS_ATTENTION"
          : "ACKNOWLEDGED";
  return reviewState(review, clause.clause_id) === wanted;
}

export function matchesEvidenceFilter(
  clause: ContractClauseResult,
  filter: EvidenceFilter,
): boolean {
  if (filter === "all") return true;
  return evidenceState(clause) === filter;
}

export function matchesCategoryFilter(
  clause: ContractClauseResult,
  category: string | null,
): boolean {
  if (!category) return true;
  const actual = String(clause.risk?.risk_category ?? "").trim();
  if (!actual) return false;
  return actual.toLowerCase() === category.trim().toLowerCase();
}

function searchHaystack(
  clause: ContractClauseResult,
  review: ReviewMap | null | undefined,
  comments?: ComparisonComment[] | null,
): string {
  const diffs = (clause.exact_differences ?? []).map((row) => {
    const formatted = formatExactDifference(row);
    return [formatted.label, formatted.oldDisplay, formatted.newDisplay, formatted.delta].join(" ");
  });
  const decision = reviewDecision(review, clause.clause_id);
  return [
    clause.clause_id,
    clause.v1_clause_id,
    clause.v2_clause_id,
    displayClauseId(clause.clause_id),
    clause.v1_text,
    clause.v2_text,
    clause.risk?.risk_category,
    clause.risk?.reason,
    explanationText(clause),
    reviewStateLabel(reviewState(review, clause.clause_id)),
    decision?.reviewer_name,
    commentBodiesForSearch(comments, clause.clause_id),
    ...diffs,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

export function matchesKeyword(
  clause: ContractClauseResult,
  review: ReviewMap | null | undefined,
  query: string,
  comments?: ComparisonComment[] | null,
): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return searchHaystack(clause, review, comments).includes(q);
}

export function matchesComparisonQuery(
  clause: ContractClauseResult,
  review: ReviewMap | null | undefined,
  rawQuery: Partial<ComparisonQuery> | ComparisonQuery,
  comments?: ComparisonComment[] | null,
): boolean {
  const q = normalizeComparisonQuery(rawQuery);
  return (
    matchesStatusFilter(clause, q.status) &&
    matchesRiskFilter(clause, q.risk) &&
    matchesReviewFilter(clause, review, q.review) &&
    matchesEvidenceFilter(clause, q.evidence) &&
    matchesCategoryFilter(clause, q.category) &&
    matchesKeyword(clause, review, q.query, comments)
  );
}

export function applyComparisonQuery(
  clauses: ContractClauseResult[],
  review: ReviewMap | null | undefined,
  rawQuery: Partial<ComparisonQuery> | ComparisonQuery,
  comments?: ComparisonComment[] | null,
): ContractClauseResult[] {
  const q = normalizeComparisonQuery(rawQuery);
  return clauses.filter((clause) => matchesComparisonQuery(clause, review, q, comments));
}

export function clauseCategories(clauses: ContractClauseResult[]): string[] {
  const seen = new Set<string>();
  const rows: string[] = [];
  for (const clause of clauses) {
    const category = String(clause.risk?.risk_category ?? "").trim();
    if (!category) continue;
    const key = category.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    rows.push(category);
  }
  return rows.sort((a, b) => a.localeCompare(b, "vi"));
}

export type QueryChip = { id: keyof ComparisonQuery; label: string };

export function activeQueryChips(query: ComparisonQuery): QueryChip[] {
  const q = normalizeComparisonQuery(query);
  const chips: QueryChip[] = [];
  if (q.status !== "all") chips.push({ id: "status", label: statusFilterLabel(q.status) });
  if (q.risk) chips.push({ id: "risk", label: riskLevelLabel(q.risk) || q.risk });
  if (q.review !== "all") chips.push({ id: "review", label: reviewFilterLabel(q.review) });
  if (q.evidence !== "all") chips.push({ id: "evidence", label: evidenceFilterLabel(q.evidence) });
  if (q.category) chips.push({ id: "category", label: q.category });
  const keyword = q.query.trim();
  if (keyword) chips.push({ id: "query", label: `“${keyword}”` });
  return chips;
}

export function clearQueryDimension(
  query: ComparisonQuery,
  id: keyof ComparisonQuery,
): ComparisonQuery {
  const next = { ...normalizeComparisonQuery(query) };
  if (id === "status") next.status = "all";
  else if (id === "risk") next.risk = null;
  else if (id === "review") next.review = "all";
  else if (id === "evidence") next.evidence = "all";
  else if (id === "category") next.category = null;
  else if (id === "query") next.query = "";
  return next;
}

export function queryScopeLabel(query: ComparisonQuery): string {
  const chips = activeQueryChips(query);
  if (chips.length === 0) return "Tất cả";
  return chips.map((chip) => chip.label).join(" · ");
}

export function queryResultCaption(
  visible: number,
  total: number,
  query: ComparisonQuery,
): string {
  if (!isQueryActive(query)) return `${total} điều khoản`;
  return `${visible} / ${total} điều khoản khớp bộ lọc`;
}

export type QueryFacetCounts = {
  status: Record<ClauseFilter, number>;
  risk: Record<string, number>;
  review: Record<ReviewFilter, number>;
  evidence: Record<EvidenceFilter, number>;
};

function countWithOverride(
  clauses: ContractClauseResult[],
  review: ReviewMap | null | undefined,
  query: ComparisonQuery,
  override: Partial<ComparisonQuery>,
  comments?: ComparisonComment[] | null,
): number {
  return applyComparisonQuery(clauses, review, { ...query, ...override }, comments).length;
}

export function facetCounts(
  clauses: ContractClauseResult[],
  review: ReviewMap | null | undefined,
  rawQuery: ComparisonQuery,
  comments?: ComparisonComment[] | null,
): QueryFacetCounts {
  const query = normalizeComparisonQuery(rawQuery);
  const status = {} as Record<ClauseFilter, number>;
  for (const id of STATUS_FILTERS) {
    status[id] = countWithOverride(clauses, review, query, { status: id }, comments);
  }
  const risk: Record<string, number> = {
    "": countWithOverride(clauses, review, query, { risk: null }, comments),
  };
  for (const level of RISK_LEVELS) {
    risk[level] = countWithOverride(clauses, review, query, { risk: level }, comments);
  }
  const reviewCounts = {} as Record<ReviewFilter, number>;
  for (const id of REVIEW_FILTERS) {
    reviewCounts[id] = countWithOverride(clauses, review, query, { review: id }, comments);
  }
  const evidence = {} as Record<EvidenceFilter, number>;
  for (const id of EVIDENCE_FILTERS) {
    evidence[id] = countWithOverride(clauses, review, query, { evidence: id }, comments);
  }
  return { status, risk, review: reviewCounts, evidence };
}
