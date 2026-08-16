/**
 * =============================================================================
 * File: ReportPreviewFilters.tsx
 * Module/Service: Report Service (Web App)
 * Layer: UI
 * Purpose: Client-side status/risk/search filters for CMP-25 preview.
 * Responsibilities:
 *   - Filter structured backend clause rows; no independent classification
 * Dependencies:
 *   - comparison-report-preview, lucide-react
 * Public Exports:
 *   - ReportPreviewFilters
 * Database/Table: N/A
 * Related Modules: ComparisonReportPreview
 * Important Notes: Search is local. Do not call the API or an LLM.
 * =============================================================================
 */

"use client";

import { Search, X } from "lucide-react";

import {
  EMPTY_REPORT_FILTERS,
  type ReportPreviewFilters as Filters,
  type ReportRiskFilter,
  type ReportStatusFilter,
} from "@/features/reports/comparison-report-preview";
import { cn } from "@/lib/utils";

const STATUS_OPTIONS: { id: ReportStatusFilter; label: string }[] = [
  { id: "all", label: "Tất cả" },
  { id: "modified", label: "Đã sửa" },
  { id: "added", label: "Thêm mới" },
  { id: "removed", label: "Đã xoá" },
  { id: "unchanged", label: "Không đổi" },
];

const RISK_OPTIONS: { id: ReportRiskFilter; label: string }[] = [
  { id: "all", label: "Mọi rủi ro" },
  { id: "CRITICAL", label: "Nghiêm trọng" },
  { id: "HIGH", label: "Cao" },
  { id: "MEDIUM", label: "Trung bình" },
  { id: "LOW", label: "Thấp" },
];

type Props = {
  filters: Filters;
  onChange: (next: Filters) => void;
};

export function ReportPreviewFilters({ filters, onChange }: Props) {
  const active =
    filters.status !== "all" || filters.risk !== "all" || filters.query.trim() !== "";

  return (
    <div className="flex flex-col gap-3">
      <label className="relative block">
        <span className="sr-only">Tìm trong báo cáo</span>
        <Search
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-tertiary"
          aria-hidden
        />
        <input
          type="search"
          value={filters.query}
          onChange={(event) =>
            onChange({ ...filters, query: event.target.value })
          }
          placeholder="Tìm số điều, tiêu đề, rủi ro, tóm tắt…"
          className="h-10 w-full rounded-md border border-border-default bg-base pl-9 pr-3 text-body-sm text-primary placeholder:text-tertiary"
        />
      </label>
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Lọc trạng thái">
        {STATUS_OPTIONS.map((option) => (
          <button
            key={option.id}
            type="button"
            onClick={() => onChange({ ...filters, status: option.id })}
            aria-pressed={filters.status === option.id}
            className={cn(
              "rounded-full border px-2.5 py-1 text-caption font-medium",
              filters.status === option.id
                ? "border-accent-primary/40 bg-elevated text-primary"
                : "border-border-default text-secondary hover:bg-elevated",
            )}
          >
            {option.label}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Lọc mức rủi ro">
        {RISK_OPTIONS.map((option) => (
          <button
            key={option.id}
            type="button"
            onClick={() => onChange({ ...filters, risk: option.id })}
            aria-pressed={filters.risk === option.id}
            className={cn(
              "rounded-full border px-2.5 py-1 text-caption font-medium",
              filters.risk === option.id
                ? "border-accent-primary/40 bg-elevated text-primary"
                : "border-border-default text-secondary hover:bg-elevated",
            )}
          >
            {option.label}
          </button>
        ))}
      </div>
      {active ? (
        <button
          type="button"
          onClick={() => onChange(EMPTY_REPORT_FILTERS)}
          className="inline-flex items-center gap-1 self-start text-caption text-secondary hover:text-primary"
        >
          <X className="h-3.5 w-3.5" aria-hidden />
          Xoá bộ lọc
        </button>
      ) : null}
    </div>
  );
}
