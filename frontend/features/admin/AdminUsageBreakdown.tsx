/**
 * =============================================================================
 * File: AdminUsageBreakdown.tsx
 * Module/Service: Observability / Usage Console (Web App) — FR13
 * Layer: UI
 * Purpose: Tabbed usage breakdown tables — By Model / By Route.
 * Responsibilities:
 *   - Accessible tab switch; semantic tables with share + avg cost/call
 * Dependencies:
 *   - features/admin/admin-usage, AdminCard
 * Public Exports:
 *   - AdminUsageBreakdown
 * Database/Table: message_generations (via CostSummary)
 * Related Modules: AdminUsageView
 * Important Notes: Route tab has no Cost column from API — show Expected LLM
 *   instead of inventing cost_usd.
 * =============================================================================
 */

"use client";

import { useState } from "react";

import {
  formatCostExact,
  formatCostUsd,
  formatCount,
  formatPercent,
  normalizeModelBreakdown,
  normalizeRouteBreakdown,
} from "@/features/admin/admin-usage";
import { AdminCard } from "@/features/admin/AdminCard";
import { cn } from "@/lib/utils";
import type { CostSummary } from "@/types/admin";

type Tab = "model" | "route";

type Props = {
  summary: CostSummary | null;
  loading: boolean;
};

export function AdminUsageBreakdown({ summary, loading }: Props) {
  const [tab, setTab] = useState<Tab>("model");
  const models = summary
    ? normalizeModelBreakdown(summary.by_model, summary.total_cost_usd)
    : [];
  const routes = normalizeRouteBreakdown(summary?.by_route_type ?? []);

  return (
    <AdminCard
      headingId="usage-breakdown-heading"
      title="Usage Breakdown"
      description="Detailed tables for model spend and route request volume."
    >
      <div
        role="tablist"
        aria-label="Breakdown dimension"
        className="mb-3 flex flex-wrap gap-1 rounded-lg border border-border-default bg-base p-1"
      >
        {(
          [
            { key: "model" as const, label: "By Model" },
            { key: "route" as const, label: "By Route" },
          ] as const
        ).map((item) => {
          const selected = tab === item.key;
          return (
            <button
              key={item.key}
              type="button"
              role="tab"
              aria-selected={selected}
              id={`usage-tab-${item.key}`}
              aria-controls={`usage-panel-${item.key}`}
              onClick={() => setTab(item.key)}
              className={cn(
                "rounded-md px-3 py-1.5 text-body-sm font-medium transition-colors",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/30",
                selected
                  ? "bg-accent-primary-soft text-accent-primary"
                  : "text-secondary hover:bg-elevated hover:text-primary",
              )}
            >
              {item.label}
            </button>
          );
        })}
      </div>

      {loading ? (
        <div className="flex flex-col gap-2" role="status" aria-label="Loading breakdown">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-10 animate-pulse rounded-md bg-elevated" />
          ))}
        </div>
      ) : tab === "model" ? (
        <div
          role="tabpanel"
          id="usage-panel-model"
          aria-labelledby="usage-tab-model"
          className="-mx-1 overflow-x-auto"
        >
          {models.length === 0 ? (
            <p className="text-body-sm text-tertiary">No model rows for this period.</p>
          ) : (
            <table className="w-full min-w-[680px] border-collapse text-body-sm">
              <thead>
                <tr className="border-b border-border-default text-left text-caption uppercase tracking-wide text-tertiary">
                  <th className="px-2 py-2 font-medium">Type</th>
                  <th className="px-2 py-2 text-right font-medium">Calls</th>
                  <th className="px-2 py-2 text-right font-medium">Tokens</th>
                  <th className="px-2 py-2 text-right font-medium">Cost</th>
                  <th className="px-2 py-2 text-right font-medium">Share</th>
                  <th className="px-2 py-2 text-right font-medium">Avg / Call</th>
                </tr>
              </thead>
              <tbody>
                {models.map((row) => (
                  <tr
                    key={row.model_used || row.displayName}
                    className="border-b border-border-default last:border-0"
                  >
                    <td className="max-w-[220px] truncate px-2 py-2.5 font-mono text-primary">
                      {row.displayName}
                    </td>
                    <td className="px-2 py-2.5 text-right font-mono text-secondary">
                      {formatCount(row.calls)}
                    </td>
                    <td
                      className="px-2 py-2.5 text-right font-mono text-secondary"
                      title={`In ${formatCount(row.prompt_tokens)} · Out ${formatCount(row.completion_tokens)}`}
                    >
                      {formatCount(row.total_tokens)}
                    </td>
                    <td
                      className="px-2 py-2.5 text-right font-mono text-primary"
                      title={formatCostExact(row.cost_usd)}
                    >
                      {formatCostUsd(row.cost_usd)}
                    </td>
                    <td className="px-2 py-2.5 text-right font-mono text-secondary">
                      {row.share === null ? "—" : formatPercent(row.share, 1)}
                    </td>
                    <td className="px-2 py-2.5 text-right font-mono text-secondary">
                      {row.costPerCall === null
                        ? "—"
                        : formatCostUsd(row.costPerCall)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : (
        <div
          role="tabpanel"
          id="usage-panel-route"
          aria-labelledby="usage-tab-route"
          className="-mx-1 overflow-x-auto"
        >
          <table className="w-full min-w-[560px] border-collapse text-body-sm">
            <thead>
              <tr className="border-b border-border-default text-left text-caption uppercase tracking-wide text-tertiary">
                <th className="px-2 py-2 font-medium">Route</th>
                <th className="px-2 py-2 text-right font-medium">Calls</th>
                <th className="px-2 py-2 text-right font-medium">Share</th>
                <th className="px-2 py-2 text-right font-medium">Expected LLM</th>
                <th className="px-2 py-2 text-right font-medium">Cost</th>
              </tr>
            </thead>
            <tbody>
              {routes.map((row) => (
                <tr
                  key={row.route}
                  className="border-b border-border-default last:border-0"
                >
                  <td className="px-2 py-2.5 font-medium text-primary">{row.label}</td>
                  <td className="px-2 py-2.5 text-right font-mono text-secondary">
                    {formatCount(row.count)}
                  </td>
                  <td className="px-2 py-2.5 text-right font-mono text-secondary">
                    {row.share === null ? "—" : formatPercent(row.share, 1)}
                  </td>
                  <td className="px-2 py-2.5 text-right font-mono text-tertiary">
                    {row.expectedLlm}
                  </td>
                  <td
                    className="px-2 py-2.5 text-right font-mono text-tertiary"
                    title="CostSummary.by_route_type does not include cost_usd"
                  >
                    —
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-caption text-tertiary">
            Route cost is unavailable in the current CostSummary contract
            (count only). Model breakdown carries monetary totals.
          </p>
        </div>
      )}
    </AdminCard>
  );
}
