/**
 * =============================================================================
 * File: AdminUsageByModel.tsx
 * Module/Service: Observability / Usage Console (Web App) — FR13
 * Layer: UI
 * Purpose: Cost-by-model ranked list with proportional bars.
 * Responsibilities:
 *   - Render by_model sorted by cost_usd with share + calls
 * Dependencies:
 *   - features/admin/admin-usage, AdminCard
 * Public Exports:
 *   - AdminUsageByModel
 * Database/Table: message_generations (via CostSummary.by_model)
 * Related Modules: AdminUsageView
 * Important Notes: Shares use backend total_cost_usd — never re-sum for total.
 * =============================================================================
 */

"use client";

import {
  formatCostExact,
  formatCostUsd,
  formatCount,
  formatPercent,
  normalizeModelBreakdown,
} from "@/features/admin/admin-usage";
import { AdminCard } from "@/features/admin/AdminCard";
import type { CostSummary } from "@/types/admin";

type Props = {
  summary: CostSummary | null;
  loading: boolean;
};

export function AdminUsageByModel({ summary, loading }: Props) {
  const rows = summary
    ? normalizeModelBreakdown(summary.by_model, summary.total_cost_usd)
    : [];
  const maxCost = rows.reduce((max, r) => Math.max(max, r.cost_usd), 0);

  return (
    <AdminCard
      headingId="usage-by-model-heading"
      title="Cost by Model"
      description="LLM spend ranked by model_used."
    >
      {loading ? (
        <div className="flex flex-col gap-3" role="status" aria-label="Loading model costs">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-12 animate-pulse rounded-md bg-elevated" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <p className="text-body-sm text-tertiary">No model cost data for this period.</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {rows.map((row) => {
            const barPct =
              maxCost > 0 ? Math.max((row.cost_usd / maxCost) * 100, row.cost_usd > 0 ? 2 : 0) : 0;
            return (
              <li key={row.model_used || row.displayName}>
                <div className="mb-1 flex items-baseline justify-between gap-2">
                  <span
                    className="truncate font-mono text-body-sm font-medium text-primary"
                    title={row.displayName}
                  >
                    {row.displayName}
                  </span>
                  <span
                    className="shrink-0 font-mono text-body-sm text-primary"
                    title={formatCostExact(row.cost_usd)}
                  >
                    {formatCostUsd(row.cost_usd)}
                  </span>
                </div>
                <div
                  className="h-2 overflow-hidden rounded-sm bg-elevated"
                  role="presentation"
                >
                  <div
                    className="h-full rounded-sm bg-accent-primary"
                    style={{ width: `${barPct}%` }}
                  />
                </div>
                <p className="mt-1 flex flex-wrap gap-x-3 font-mono text-caption text-tertiary">
                  <span>{formatCount(row.calls)} calls</span>
                  <span>
                    Share{" "}
                    {row.share === null ? "—" : formatPercent(row.share, 1)}
                  </span>
                  <span>
                    Avg{" "}
                    {row.costPerCall === null
                      ? "—"
                      : formatCostUsd(row.costPerCall)}
                  </span>
                  <span>{formatCount(row.total_tokens)} tokens</span>
                </p>
              </li>
            );
          })}
        </ul>
      )}
    </AdminCard>
  );
}
