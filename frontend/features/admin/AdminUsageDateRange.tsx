/**
 * =============================================================================
 * File: AdminUsageDateRange.tsx
 * Module/Service: Observability / Usage Console (Web App) — FR13
 * Layer: UI
 * Purpose: Date-range controls for CostSummary from/to query params.
 * Responsibilities:
 *   - Preset selector + custom from/to + Apply
 *   - Workspace selector for multi-tenant scope
 * Dependencies:
 *   - features/admin/admin-usage, hooks/useAdminEligibleWorkspaces
 * Public Exports:
 *   - AdminUsageDateRange
 * Database/Table: N/A
 * Related Modules: AdminUsageView
 * Important Notes: Sends YYYY-MM-DD only. Custom dates apply on Apply click.
 * =============================================================================
 */

"use client";

import {
  formatDateRangeLabel,
  USAGE_DATE_PRESETS,
  type UsageDatePreset,
} from "@/features/admin/admin-usage";
import type { AdminWorkspaceOption } from "@/hooks/useAdminEligibleWorkspaces";
import { cn } from "@/lib/utils";

type Props = {
  workspaceId: string;
  workspaceOptions: AdminWorkspaceOption[];
  preset: UsageDatePreset;
  from: string;
  to: string;
  customFrom: string;
  customTo: string;
  loading: boolean;
  onWorkspaceChange: (id: string) => void;
  onPresetChange: (preset: UsageDatePreset) => void;
  onCustomFromChange: (value: string) => void;
  onCustomToChange: (value: string) => void;
  onApplyCustom: () => void;
};

export function AdminUsageDateRange({
  workspaceId,
  workspaceOptions,
  preset,
  from,
  to,
  customFrom,
  customTo,
  loading,
  onWorkspaceChange,
  onPresetChange,
  onCustomFromChange,
  onCustomToChange,
  onApplyCustom,
}: Props) {
  return (
    <section
      aria-labelledby="usage-date-range-heading"
      className="rounded-lg border border-border-default bg-surface p-4 sm:p-5"
    >
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="usage-date-range-heading" className="text-h3 text-primary">
          Date Range
        </h2>
        <p className="text-caption text-tertiary" aria-live="polite">
          {formatDateRangeLabel(from, to)}
        </p>
      </div>

      <div className="flex flex-col gap-3 lg:flex-row lg:flex-wrap lg:items-end">
        <label className="flex min-w-[10rem] flex-col gap-1">
          <span className="text-caption font-medium text-tertiary">Workspace</span>
          <select
            aria-label="Workspace"
            value={workspaceId}
            onChange={(e) => onWorkspaceChange(e.target.value)}
            className={cn(
              "h-10 rounded-md border border-border-default bg-base px-2.5",
              "text-body-sm text-primary outline-none",
              "focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20",
            )}
          >
            {workspaceOptions.map((ws) => (
              <option key={ws.id} value={ws.id}>
                {ws.name}
              </option>
            ))}
          </select>
        </label>

        <label className="flex min-w-[12rem] flex-col gap-1">
          <span className="text-caption font-medium text-tertiary">Preset</span>
          <select
            aria-label="Date range preset"
            value={preset}
            onChange={(e) => onPresetChange(e.target.value as UsageDatePreset)}
            className={cn(
              "h-10 rounded-md border border-border-default bg-base px-2.5",
              "text-body-sm text-primary outline-none",
              "focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20",
            )}
          >
            {USAGE_DATE_PRESETS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>

        {preset === "custom" ? (
          <>
            <label className="flex flex-col gap-1">
              <span className="text-caption font-medium text-tertiary">From</span>
              <input
                type="date"
                value={customFrom}
                onChange={(e) => onCustomFromChange(e.target.value)}
                aria-label="From date"
                className={cn(
                  "h-10 rounded-md border border-border-default bg-base px-2.5",
                  "text-body-sm text-primary outline-none",
                  "focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20",
                )}
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-caption font-medium text-tertiary">To</span>
              <input
                type="date"
                value={customTo}
                onChange={(e) => onCustomToChange(e.target.value)}
                aria-label="To date"
                className={cn(
                  "h-10 rounded-md border border-border-default bg-base px-2.5",
                  "text-body-sm text-primary outline-none",
                  "focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20",
                )}
              />
            </label>
            <button
              type="button"
              onClick={onApplyCustom}
              disabled={loading || !customFrom || !customTo}
              className={cn(
                "inline-flex h-10 items-center justify-center rounded-md border border-border-default bg-base px-4",
                "text-body-sm font-medium text-primary hover:bg-elevated",
                "disabled:opacity-50",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/30",
              )}
            >
              Apply
            </button>
          </>
        ) : null}
      </div>
    </section>
  );
}
