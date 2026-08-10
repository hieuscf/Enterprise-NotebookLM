/**
 * =============================================================================
 * File: AdminQueryLogsOverview.tsx
 * Module/Service: Observability / Query Logs Console (Web App) — FR13
 * Layer: UI
 * Purpose: KPI strip + route distribution for `/admin/query-logs`.
 * Responsibilities:
 *   - Render Total Queries / Cache Hit / LLM Calls / Avg Latency
 *   - Render horizontal route distribution bars (4 route types only)
 * Dependencies:
 *   - features/admin/admin-query-logs
 * Public Exports:
 *   - AdminQueryLogsOverview
 * Database/Table: query_logs (sample-derived)
 * Related Modules: AdminQueryLogsView
 * Important Notes: Stats are derived from a bounded recent sample — never
 *   presented as a full-workspace aggregate when capped. No fake totals.
 * =============================================================================
 */

"use client";

import {
  deriveQueryLogsOverview,
  formatCount,
  formatLatency,
  formatPercent,
  ROUTE_DOT_CLASS,
  ROUTE_LABEL,
  ROUTE_MARKER,
  type QueryLogsOverviewStats,
} from "@/features/admin/admin-query-logs";
import { cn } from "@/lib/utils";
import type { QueryLogItem } from "@/types/admin";
import type { RouteType } from "@/types/chat";

type Props = {
  logs: QueryLogItem[];
  sampleCapped: boolean;
  loading: boolean;
  activeRoute: RouteType | "all";
  onRouteChange: (route: RouteType | "all") => void;
};

function StatCard({
  label,
  value,
  hint,
  loading,
}: {
  label: string;
  value: string;
  hint: string;
  loading: boolean;
}) {
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-border-default bg-surface px-4 py-3 text-left">
      <p className="text-caption font-semibold uppercase tracking-wider text-tertiary">
        {label}
      </p>
      {loading ? (
        <div className="h-7 w-16 animate-pulse rounded bg-elevated" />
      ) : (
        <p className="font-mono text-h2 font-semibold text-primary">{value}</p>
      )}
      <p className="text-caption text-tertiary">{hint}</p>
    </div>
  );
}

function statsHint(stats: QueryLogsOverviewStats): string {
  if (stats.total === 0) return "No recent sample";
  return stats.sampleCapped
    ? `From latest ${formatCount(stats.total)} queries (sample)`
    : `From latest ${formatCount(stats.total)} queries`;
}

export function AdminQueryLogsOverview({
  logs,
  sampleCapped,
  loading,
  activeRoute,
  onRouteChange,
}: Props) {
  const stats = deriveQueryLogsOverview(logs, sampleCapped);
  const hint = statsHint(stats);
  const cacheHitLabel =
    stats.cacheHitRate === null ? "—" : formatPercent(stats.cacheHitRate, 1);
  const avgLabel =
    stats.avgLatencyMs === null ? "—" : formatLatency(stats.avgLatencyMs);

  return (
    <div className="flex flex-col gap-4">
      <section aria-labelledby="query-logs-overview-heading">
        <div className="mb-2 flex items-baseline justify-between gap-3">
          <h2 id="query-logs-overview-heading" className="text-h3 text-primary">
            Overview
          </h2>
          <p className="text-caption text-tertiary">{loading ? "Updating…" : hint}</p>
        </div>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard
            label="Total Queries"
            value={formatCount(stats.total)}
            hint="In current sample"
            loading={loading}
          />
          <StatCard
            label="Cache Hit"
            value={cacheHitLabel}
            hint="cache_hit / total"
            loading={loading}
          />
          <StatCard
            label="LLM Calls"
            value={formatCount(stats.totalLlmCalls)}
            hint="sum(llm_calls_count)"
            loading={loading}
          />
          <StatCard
            label="Avg Latency"
            value={avgLabel}
            hint="average(latency_ms)"
            loading={loading}
          />
        </div>
      </section>

      <section
        aria-labelledby="route-distribution-heading"
        className="rounded-lg border border-border-default bg-surface p-4 sm:p-5"
      >
        <div className="mb-3 flex items-baseline justify-between gap-3">
          <h2 id="route-distribution-heading" className="text-h3 text-primary">
            Route Distribution
          </h2>
          <p className="text-caption text-tertiary">
            How often Query Router avoids LLM calls
          </p>
        </div>

        {loading && logs.length === 0 ? (
          <div className="flex flex-col gap-3" role="status" aria-label="Loading route distribution">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-8 animate-pulse rounded bg-elevated" />
            ))}
          </div>
        ) : stats.total === 0 ? (
          <p className="text-body-sm text-tertiary">No routing data in sample yet.</p>
        ) : (
          <ul className="flex flex-col gap-2.5">
            {stats.distribution.map((row) => {
              const selected = activeRoute === row.route;
              const pct = formatPercent(row.ratio, 1);
              return (
                <li key={row.route}>
                  <button
                    type="button"
                    onClick={() =>
                      onRouteChange(selected ? "all" : row.route)
                    }
                    aria-pressed={selected}
                    className={cn(
                      "grid w-full grid-cols-[7.5rem_1fr_auto] items-center gap-3 rounded-md px-2 py-1.5 text-left",
                      "transition-colors hover:bg-elevated/60",
                      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/30",
                      selected && "bg-accent-primary-soft/50 ring-1 ring-accent-primary/20",
                    )}
                  >
                    <span className="flex items-center gap-1.5 text-body-sm font-medium text-primary">
                      <span
                        className={cn("h-2 w-2 shrink-0 rounded-sm", ROUTE_DOT_CLASS[row.route])}
                        aria-hidden
                      />
                      <span aria-hidden className="text-caption text-tertiary">
                        {ROUTE_MARKER[row.route]}
                      </span>
                      {ROUTE_LABEL[row.route]}
                    </span>
                    <span
                      className="h-2 overflow-hidden rounded-sm bg-elevated"
                      role="presentation"
                    >
                      <span
                        className={cn("block h-full rounded-sm", ROUTE_DOT_CLASS[row.route])}
                        style={{ width: `${Math.max(row.ratio * 100, row.count > 0 ? 2 : 0)}%` }}
                      />
                    </span>
                    <span className="flex min-w-[5.5rem] items-baseline justify-end gap-2 font-mono text-caption text-secondary">
                      <span>{pct}</span>
                      <span className="text-tertiary">{formatCount(row.count)}</span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
