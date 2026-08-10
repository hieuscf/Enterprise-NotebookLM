/**
 * =============================================================================
 * File: AdminUsageOverview.tsx
 * Module/Service: Observability / Usage Console (Web App) — FR13
 * Layer: UI
 * Purpose: Aggregate cost overview + deterministic insights (no fake series).
 * Responsibilities:
 *   - Show period total spend when no daily_cost time-series exists
 *   - Surface most expensive model / highest usage route / zero-LLM routes
 * Dependencies:
 *   - features/admin/admin-usage
 * Public Exports:
 *   - AdminUsageOverview
 * Database/Table: message_generations (via CostSummary)
 * Related Modules: AdminUsageView
 * Important Notes: Do not invent daily trend charts from a single aggregate.
 * =============================================================================
 */

"use client";

import {
  deriveUsageInsights,
  formatCostExact,
  formatCostUsd,
  formatCount,
  isEmptyUsage,
} from "@/features/admin/admin-usage";
import { AdminCard } from "@/features/admin/AdminCard";
import type { CostSummary } from "@/types/admin";

type Props = {
  summary: CostSummary | null;
  loading: boolean;
  periodLabel: string;
};

export function AdminUsageOverview({ summary, loading, periodLabel }: Props) {
  const insights = deriveUsageInsights(summary);
  const empty = isEmptyUsage(summary);

  return (
    <AdminCard
      headingId="usage-cost-overview-heading"
      title="Cost Overview"
      description="Total spend for the selected period. Daily trend requires a time-series API (not available)."
    >
      {loading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-20 animate-pulse rounded-md bg-elevated" />
          ))}
        </div>
      ) : empty ? (
        <div className="rounded-md border border-dashed border-border-default px-4 py-8 text-center">
          <p className="text-body-sm font-medium text-secondary">No LLM usage</p>
          <p className="mt-1 text-caption text-tertiary">
            There was no recorded LLM usage during the selected period.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <div className="rounded-lg border border-border-default bg-elevated/30 px-4 py-5">
            <p className="text-caption font-semibold uppercase tracking-wider text-tertiary">
              Total spend · {periodLabel}
            </p>
            <p
              className="mt-1 font-mono text-h1 font-semibold text-primary"
              title={
                summary ? formatCostExact(summary.total_cost_usd) : undefined
              }
            >
              {summary ? formatCostUsd(summary.total_cost_usd) : "—"}
            </p>
            <p className="mt-1 text-caption text-tertiary">
              {summary ? formatCount(summary.total_llm_calls) : "0"} LLM calls
              {summary && typeof summary.total_tokens === "number"
                ? ` · ${formatCount(summary.total_tokens)} tokens`
                : ""}
            </p>
          </div>

          <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div className="rounded-md border border-border-default px-3 py-3">
              <dt className="text-caption font-semibold uppercase tracking-wider text-tertiary">
                Most expensive model
              </dt>
              <dd className="mt-1">
                <p className="truncate font-mono text-body-sm font-medium text-primary">
                  {insights.mostExpensiveModel?.displayName ?? "—"}
                </p>
                <p className="font-mono text-caption text-secondary">
                  {insights.mostExpensiveModel
                    ? formatCostUsd(insights.mostExpensiveModel.cost_usd)
                    : "—"}
                </p>
              </dd>
            </div>
            <div className="rounded-md border border-border-default px-3 py-3">
              <dt className="text-caption font-semibold uppercase tracking-wider text-tertiary">
                Highest usage route
              </dt>
              <dd className="mt-1">
                <p className="text-body-sm font-medium text-primary">
                  {insights.highestUsageRoute?.label ?? "—"}
                </p>
                <p className="font-mono text-caption text-secondary">
                  {insights.highestUsageRoute
                    ? `${formatCount(insights.highestUsageRoute.count)} requests`
                    : "—"}
                </p>
              </dd>
            </div>
            <div className="rounded-md border border-border-default px-3 py-3 sm:col-span-2 lg:col-span-1">
              <dt className="text-caption font-semibold uppercase tracking-wider text-tertiary">
                Zero-LLM routes (design)
              </dt>
              <dd className="mt-1 text-body-sm text-secondary">
                {insights.zeroCostRouteLabels.join(" / ")}
              </dd>
              <p className="mt-1 text-caption text-tertiary">
                Cache Hit, Metadata, and Factoid are designed for 0 LLM calls.
                Route cost is not in CostSummary — only request counts.
              </p>
            </div>
          </dl>
        </div>
      )}
    </AdminCard>
  );
}
