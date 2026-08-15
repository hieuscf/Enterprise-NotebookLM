/**
 * =============================================================================
 * File: ComparisonFilterBar.tsx
 * Module/Service: Comparison Service (Web App)
 * Layer: UI
 * Purpose: Combined filter/search bar for TASK-CMP-21 Comparison Filtering.
 * Responsibilities:
 *   - Let reviewers AND status, risk, review, evidence, category, and keyword
 *   - Show facet counts, active chips, and a clear action
 * Dependencies:
 *   - comparison-filter helpers, design tokens
 * Public Exports:
 *   - ComparisonFilterBar
 * Database/Table: N/A
 * Related Modules: ComparisonSummaryView, comparison-filter.ts
 * Important Notes: Query layer only — does not write comparison or review data.
 * =============================================================================
 */

"use client";

import { Search, X } from "lucide-react";

import {
  EMPTY_COMPARISON_QUERY,
  activeQueryChips,
  clearQueryDimension,
  isQueryActive,
  queryResultCaption,
  type ComparisonQuery,
  type EvidenceFilter,
  type QueryFacetCounts,
} from "@/features/comparisons/comparison-filter";
import { riskToneClass } from "@/features/comparisons/comparison-badges";
import { riskLevelLabel, type ClauseFilter } from "@/features/comparisons/comparison-summary";
import { cn } from "@/lib/utils";
import type { ReviewFilter } from "@/features/comparisons/comparison-review";

const STATUS_FILTERS: { id: ClauseFilter; label: string }[] = [
  { id: "all", label: "Tất cả" },
  { id: "changed", label: "Có thay đổi" },
  { id: "modified", label: "Đã sửa" },
  { id: "added", label: "Thêm mới" },
  { id: "removed", label: "Đã xoá" },
  { id: "unchanged", label: "Không đổi" },
];

const RISK_FILTERS = ["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const;

const REVIEW_FILTERS: { id: ReviewFilter; label: string }[] = [
  { id: "all", label: "Mọi rà soát" },
  { id: "open", label: "Chưa rà soát" },
  { id: "reviewed", label: "Đã rà soát" },
  { id: "needs_attention", label: "Cần chú ý" },
  { id: "acknowledged", label: "Đã ghi nhận" },
];

const EVIDENCE_FILTERS: { id: EvidenceFilter; label: string }[] = [
  { id: "all", label: "Mọi bằng chứng" },
  { id: "verified", label: "Đã xác minh" },
  { id: "partial", label: "Xác minh một phần" },
  { id: "unverified", label: "Chưa xác minh" },
  { id: "unavailable", label: "Không có bằng chứng" },
];

type Props = {
  query: ComparisonQuery;
  total: number;
  visible: number;
  facets: QueryFacetCounts;
  categories: string[];
  showRiskFilters?: boolean;
  onChange: (next: ComparisonQuery) => void;
};

const chipClass =
  "rounded-md border px-2.5 py-1 text-caption font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40";

export function ComparisonFilterBar({
  query,
  total,
  visible,
  facets,
  categories,
  showRiskFilters = true,
  onChange,
}: Props) {
  const active = isQueryActive(query);
  const chips = activeQueryChips(query);

  function patch(partial: Partial<ComparisonQuery>) {
    onChange({ ...query, ...partial });
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-caption text-tertiary" aria-live="polite">
          {queryResultCaption(visible, total, query)}
        </p>
        {active ? (
          <button
            type="button"
            onClick={() => onChange({ ...EMPTY_COMPARISON_QUERY })}
            className="text-caption font-medium text-accent-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40"
          >
            Xóa bộ lọc
          </button>
        ) : null}
      </div>

      <div role="tablist" aria-label="Lọc theo trạng thái điều khoản" className="flex flex-wrap gap-1.5">
        {STATUS_FILTERS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={query.status === item.id}
            onClick={() => patch({ status: item.id })}
            className={cn(
              chipClass,
              query.status === item.id
                ? "border-accent-primary/40 bg-accent-primary/10 text-primary"
                : "border-border-default text-secondary hover:bg-elevated",
            )}
          >
            {item.label}
            <span className="ml-1 tabular-nums text-tertiary">{facets.status[item.id] ?? 0}</span>
          </button>
        ))}
      </div>

      {showRiskFilters ? (
        <div role="group" aria-label="Lọc theo mức rủi ro" className="flex flex-wrap gap-1.5">
          {RISK_FILTERS.map((level) => (
            <button
              key={level}
              type="button"
              aria-pressed={query.risk === level}
              onClick={() => patch({ risk: query.risk === level ? null : level })}
              className={cn(
                chipClass,
                query.risk === level ? riskToneClass(level) : "border-border-default text-secondary hover:bg-elevated",
              )}
            >
              {riskLevelLabel(level)}
              <span className="ml-1 tabular-nums opacity-80">{facets.risk[level] ?? 0}</span>
            </button>
          ))}
        </div>
      ) : null}

      <div role="group" aria-label="Lọc theo quyết định rà soát" className="flex flex-wrap gap-1.5">
        {REVIEW_FILTERS.map((item) => (
          <button
            key={item.id}
            type="button"
            aria-pressed={query.review === item.id}
            onClick={() => patch({ review: item.id })}
            className={cn(
              chipClass,
              query.review === item.id
                ? "border-accent-primary/40 bg-accent-primary/10 text-primary"
                : "border-border-default text-secondary hover:bg-elevated",
            )}
          >
            {item.label}
            <span className="ml-1 tabular-nums text-tertiary">{facets.review[item.id] ?? 0}</span>
          </button>
        ))}
      </div>

      <div role="group" aria-label="Lọc theo trạng thái bằng chứng" className="flex flex-wrap gap-1.5">
        {EVIDENCE_FILTERS.map((item) => (
          <button
            key={item.id}
            type="button"
            aria-pressed={query.evidence === item.id}
            onClick={() => patch({ evidence: item.id })}
            className={cn(
              chipClass,
              query.evidence === item.id
                ? "border-accent-primary/40 bg-accent-primary/10 text-primary"
                : "border-border-default text-secondary hover:bg-elevated",
            )}
          >
            {item.label}
            <span className="ml-1 tabular-nums text-tertiary">{facets.evidence[item.id] ?? 0}</span>
          </button>
        ))}
      </div>

      <div className="flex flex-col gap-2 sm:flex-row">
        {categories.length > 0 ? (
          <label className="flex min-w-[12rem] flex-col gap-1">
            <span className="sr-only">Lọc theo danh mục rủi ro</span>
            <select
              value={query.category ?? ""}
              onChange={(event) => patch({ category: event.target.value || null })}
              aria-label="Lọc theo danh mục rủi ro"
              className={cn(
                "h-9 cursor-pointer rounded-md border border-border-default bg-surface px-2.5",
                "text-body-sm text-primary outline-none",
                "focus-visible:border-accent-primary focus-visible:ring-2 focus-visible:ring-accent-primary/40",
              )}
            >
              <option value="">Mọi danh mục</option>
              {categories.map((category) => (
                <option key={category} value={category}>
                  {category}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <label className="relative block min-w-0 flex-1">
          <span className="sr-only">Tìm điều khoản</span>
          <Search
            className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-tertiary"
            aria-hidden
          />
          <input
            type="search"
            value={query.query}
            onChange={(event) => patch({ query: event.target.value })}
            placeholder="Tìm số điều, nội dung, danh mục hoặc người rà soát…"
            className="h-9 w-full rounded-md border border-border-default bg-surface pl-8 pr-3 text-body-sm text-primary placeholder:text-tertiary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40"
          />
        </label>
      </div>

      {chips.length > 0 ? (
        <ul className="flex flex-wrap gap-1.5" aria-label="Bộ lọc đang áp dụng">
          {chips.map((chip) => (
            <li key={chip.id}>
              <button
                type="button"
                onClick={() => onChange(clearQueryDimension(query, chip.id))}
                className={cn(
                  "inline-flex items-center gap-1 rounded-full border border-border-default bg-elevated px-2 py-0.5",
                  "text-caption text-secondary hover:bg-surface",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40",
                )}
                aria-label={`Gỡ bộ lọc ${chip.label}`}
              >
                {chip.label}
                <X className="h-3 w-3" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
