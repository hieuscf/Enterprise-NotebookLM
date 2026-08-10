/**
 * =============================================================================
 * File: AdminUsageByRoute.tsx
 * Module/Service: Observability / Usage Console (Web App) — FR13
 * Layer: UI
 * Purpose: Usage-by-route breakdown highlighting Query Router efficiency.
 * Responsibilities:
 *   - Show all 4 routes with counts (including zeros)
 *   - Explain expected LLM behavior; do not invent route cost_usd
 * Dependencies:
 *   - features/admin/admin-usage, AdminCard
 * Public Exports:
 *   - AdminUsageByRoute
 * Database/Table: message_generations (via CostSummary.by_route_type)
 * Related Modules: AdminUsageView
 * Important Notes: OpenAPI by_route_type has count only — no cost_usd field.
 * =============================================================================
 */

"use client";

import {
  formatCount,
  formatPercent,
  normalizeRouteBreakdown,
  ROUTE_BADGE_CLASS,
  ROUTE_DOT_CLASS,
} from "@/features/admin/admin-usage";
import { AdminCard } from "@/features/admin/AdminCard";
import { cn } from "@/lib/utils";
import type { CostSummary } from "@/types/admin";

type Props = {
  summary: CostSummary | null;
  loading: boolean;
};

export function AdminUsageByRoute({ summary, loading }: Props) {
  const rows = normalizeRouteBreakdown(summary?.by_route_type ?? []);
  const maxCount = rows.reduce((max, r) => Math.max(max, r.count), 0);
  const hasAny = rows.some((r) => r.count > 0);

  return (
    <AdminCard
      headingId="usage-by-route-heading"
      title="Usage by Route"
      description="Query Router distribution — zero-LLM routes stay visible."
    >
      {loading ? (
        <div className="flex flex-col gap-3" role="status" aria-label="Loading route usage">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-12 animate-pulse rounded-md bg-elevated" />
          ))}
        </div>
      ) : !hasAny ? (
        <div>
          <p className="mb-3 text-body-sm text-tertiary">
            No route usage recorded for this period.
          </p>
          <RouteList rows={rows} maxCount={0} />
        </div>
      ) : (
        <>
          <RouteList rows={rows} maxCount={maxCount} />
          <p className="mt-3 text-caption text-tertiary">
            Cost per route is not returned by CostSummary (count only). Model
            spend above is the cost source of truth.
          </p>
        </>
      )}
    </AdminCard>
  );
}

function RouteList({
  rows,
  maxCount,
}: {
  rows: ReturnType<typeof normalizeRouteBreakdown>;
  maxCount: number;
}) {
  return (
    <ul className="flex flex-col gap-3">
      {rows.map((row) => {
        const barPct =
          maxCount > 0
            ? Math.max((row.count / maxCount) * 100, row.count > 0 ? 2 : 0)
            : 0;
        return (
          <li key={row.route}>
            <div className="mb-1 flex items-center justify-between gap-2">
              <span
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-caption font-semibold",
                  ROUTE_BADGE_CLASS[row.route],
                )}
              >
                <span
                  className={cn("h-1.5 w-1.5 rounded-sm", ROUTE_DOT_CLASS[row.route])}
                  aria-hidden
                />
                {row.label}
              </span>
              <span className="font-mono text-caption text-tertiary">
                {row.expectedLlm}
              </span>
            </div>
            <div
              className="h-2 overflow-hidden rounded-sm bg-elevated"
              role="presentation"
            >
              <div
                className={cn("h-full rounded-sm", ROUTE_DOT_CLASS[row.route])}
                style={{ width: `${barPct}%` }}
              />
            </div>
            <p className="mt-1 flex flex-wrap gap-x-3 font-mono text-caption text-secondary">
              <span>{formatCount(row.count)} queries</span>
              <span>
                Share {row.share === null ? "—" : formatPercent(row.share, 1)}
              </span>
            </p>
          </li>
        );
      })}
    </ul>
  );
}
